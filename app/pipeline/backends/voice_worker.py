"""Processo filho de voz/legendas: carrega UM modelo (Kokoro ou Whisper), atende pedidos e morre.

Rodar o modelo num processo próprio é a forma de garantir que, ao fim da etapa, a GPU *e* a RAM
voltam inteiras ao sistema (descarregar dentro do processo principal deixava ~5 GB retidos).

Protocolo: uma linha JSON por pedido em stdin; uma linha JSON por resposta em stdout
({"ok": ...} ou {"error": "..."}). Tudo o que as bibliotecas imprimirem vai para stderr.
Uso: python -m app.pipeline.backends.voice_worker tts|align
"""
import json
import os
import sys

STUB = os.getenv("MC_VOICE_STUB") == "1"  # testes locais, sem GPU nem modelos


def _models_dir():
    from ... import config

    return config.MODELS


# ------------------------------------------------------------------ Kokoro
def _load_kokoro():
    if STUB:
        return None
    from kokoro import KModel, KPipeline

    d = _models_dir() / "kokoro"
    model = KModel(repo_id="hexgrad/Kokoro-82M", config=str(d / "config.json"), model=str(d / "kokoro-v1_0.pth")).to("cuda").eval()
    pipe = KPipeline(lang_code="p", repo_id="hexgrad/Kokoro-82M", model=model)
    if os.getenv("MC_PTBR_FIX", "1") != "0":      # sons do português do Brasil (nasais, "a" final, r curto); MC_PTBR_FIX=0 volta ao original
        from .. import ptbr

        pipe.g2p = ptbr.wrap_g2p(pipe.g2p)
    return pipe


def _tts(pipe, req: dict) -> float:
    if STUB:
        from .fake import FakeBackend

        return FakeBackend().tts(req["text"], req["voice"], req["speed"], req["out"])
    import soundfile as sf
    import torch

    voice_file = _models_dir() / "kokoro" / "voices" / f"{req['voice']}.pt"
    parts = [torch.as_tensor(a) for _, _, a in pipe(req["text"], voice=str(voice_file), speed=req["speed"])]
    audio = torch.cat(parts).cpu().numpy()
    sf.write(req["out"], audio, 24000, subtype="PCM_16")
    return len(audio) / 24000


# ----------------------------------------------------------------- Whisper
def _load_whisper():
    if STUB:
        return None
    from faster_whisper import WhisperModel

    return WhisperModel(str(_models_dir() / "whisper-large-v3"), device="cuda", compute_type="float16")


def _align(model, req: dict) -> list:
    from ... import captions

    if STUB:
        return captions.proportional_words(req["words"], req["duration"])
    import soundfile as sf
    import torch
    import torchaudio

    data, sr = sf.read(req["wav"], dtype="float32")
    audio = torchaudio.functional.resample(torch.from_numpy(data), sr, 16000).numpy()
    segments, _ = model.transcribe(audio, language="pt", word_timestamps=True, vad_filter=False, beam_size=5)
    heard = [(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or [])]
    return captions.align_words(req["words"], heard, req["duration"])


def _transcribe(model, req: dict) -> dict:
    """Letra de uma música cantada: Whisper large-v3 com os mesmos filtros contra alucinação usados no AudioGlifo."""
    if STUB:
        d = float(req.get("duration") or 30.0)
        return {"segments": [{"start": round(d * i / 4, 2), "end": round(d * (i + 0.8) / 4, 2), "text": f"Linha {i + 1} da letra de teste"} for i in range(4)], "duration": d}
    import subprocess

    import numpy as np

    r = subprocess.run(["ffmpeg", "-v", "error", "-i", req["path"], "-ac", "1", "-ar", "16000", "-af", "highpass=f=120,lowpass=f=7500", "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("não consegui ler o áudio")
    audio = np.frombuffer(r.stdout, dtype=np.float32).copy()
    # SEM vad_filter: o detector de voz do Whisper não reconhece canto sobre a base musical e descartava a música inteira
    # (medido na andes: com ele, 0 trechos; sem ele, a letra completa em 5 s). Quem protege contra alucinação são os filtros abaixo.
    segments, _ = model.transcribe(audio, language=req.get("language", "pt"), vad_filter=False, word_timestamps=False,
                                   condition_on_previous_text=False, beam_size=5, temperature=[0.0, 0.2, 0.4])
    raw = [{"start": float(sg.start), "end": float(sg.end), "text": sg.text, "no_speech_prob": float(sg.no_speech_prob),
            "avg_logprob": float(sg.avg_logprob), "compression_ratio": float(sg.compression_ratio)} for sg in segments]
    return {"segments": clean_segments(raw), "duration": round(len(audio) / 16000, 2)}


HALLUCINATIONS = ("legendas pela comunidade", "legendado por", "legendas por", "obrigado por assistir", "inscreva-se", "inscreva se no canal", "amara.org",
                  "tradução e legendas", "transcrição e legendas", "transcrição e legenda", "legendas:")


def clean_segments(raw: list[dict]) -> list[dict]:
    """Tira o que o Whisper inventa em trechos instrumentais: sem fala, pouca confiança, repetição ou frases típicas de legenda automática."""
    out = []
    for sg in raw:
        if sg["no_speech_prob"] > 0.7 and sg["avg_logprob"] < -1.0:
            continue
        if sg["compression_ratio"] > 2.6 or sg["avg_logprob"] < -1.6:
            continue
        txt = " ".join(str(sg["text"]).split())
        if not txt or not any(c.isalpha() for c in txt) or any(h in txt.lower() for h in HALLUCINATIONS):  # só símbolo (🎶, ♪) ou crédito de legenda
            continue
        if out and out[-1]["text"].lower() == txt.lower():
            continue
        out.append({"start": round(sg["start"], 2), "end": round(sg["end"], 2), "text": txt})
    return out


def _whisper_op(model, req: dict):
    return _transcribe(model, req) if req.get("op") == "transcribe" else _align(model, req)


def main(kind: str) -> None:
    proto = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)  # prints das bibliotecas não podem corromper o protocolo
    load, handle = {"tts": (_load_kokoro, _tts), "align": (_load_whisper, _whisper_op)}[kind]
    model, loaded = None, False
    for line in sys.stdin:
        req = json.loads(line)
        if req.get("op") == "quit":
            break
        try:
            if not loaded:
                model, loaded = load(), True
            proto.write(json.dumps({"ok": handle(model, req)}) + "\n")
        except Exception as e:  # o pai decide o que fazer; o filho continua vivo
            proto.write(json.dumps({"error": f"{type(e).__name__}: {e}"}) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
