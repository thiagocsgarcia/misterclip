"""Backend real (andes): Ollama (prompts), Kokoro (voz), faster-whisper (tempos) e ComfyUI (imagens/clipes).

Regra do projeto: cada modelo é descarregado da GPU ao fim da sua etapa. Kokoro e Whisper rodam em
processos filhos (voice_worker) que são encerrados no `unload`; o ComfyUI recebe /free; o Ollama usa keep_alive=0.
Este módulo não importa torch, então o processo principal fica leve.
"""
import json
import subprocess
import sys
import urllib.request

from ... import cancel, config
from .comfy import Comfy, ComfyError

LLM_SYSTEM = (
    "You write image prompts for a text-to-image model. Given a narration excerpt in Portuguese, reply with ONE "
    "concrete visual description in English (max 40 words): subject, setting, light, composition. "
    "No abstract concepts, no text or letters in the image, no people's names, no quotes. Reply with the description only."
)
CLIP_SIZE = {"ltx": (768, 416), "wan": (960, 544)}
MIN_FREE_GB = 12.0  # abaixo disso, descarrega o ComfyUI antes de carregar outro modelo (a andes tem 30 GB no total)


def mem_available_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 99.0  # sem /proc/meminfo, não bloqueia nada


class _Child:
    """Processo filho de voz/legendas falando JSON por linhas."""

    def __init__(self, kind: str):
        self.kind = kind
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.pipeline.backends.voice_worker", kind],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )

    def call(self, req: dict):
        if self.proc.poll() is not None:
            raise RuntimeError(f"processo de {self.kind} morreu (código {self.proc.returncode})")
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"processo de {self.kind} encerrou sem responder (memória?)")
        res = json.loads(line)
        if "error" in res:
            raise RuntimeError(res["error"])
        return res["ok"]

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write('{"op": "quit"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=15)
        except Exception:
            self.proc.kill()
            self.proc.wait()


class RealBackend:
    name = "real"

    def __init__(self):
        self.comfy = Comfy(config.COMFY_URL)
        self._children: dict[str, _Child] = {}
        self._last_engine: str | None = None

    def _child(self, kind: str) -> _Child:
        c = self._children.get(kind)
        if c is None or c.proc.poll() is not None:
            c = self._children[kind] = _Child(kind)
        return c

    # ------------------------------------------------------------- LLM
    def visual_prompt(self, scene_text: str, system: str | None = None, extra: str = "") -> str:
        body = {
            "model": config.LLM_MODEL,
            "stream": False,
            "think": False,
            "keep_alive": 0,  # descarrega o LLM da GPU logo após a resposta
            "options": {"temperature": 0.7},
            "messages": [{"role": "system", "content": (system or LLM_SYSTEM) + (" " + extra if extra else "")}, {"role": "user", "content": scene_text}],
        }
        req = urllib.request.Request(config.OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            text = json.loads(r.read())["message"]["content"].strip()
        return text.strip('"').splitlines()[0] if text else scene_text[:200]

    def llm_text(self, system: str, user: str, max_tokens: int = 1200) -> str:
        """Ollama em texto livre (roteiros): contexto grande e limite de tamanho da resposta."""
        body = {
            "model": config.LLM_MODEL, "stream": False, "think": False, "keep_alive": 0,
            "options": {"temperature": 0.75, "num_ctx": 8192, "num_predict": int(max_tokens), "repeat_penalty": 1.08},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        req = urllib.request.Request(config.OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["message"]["content"].strip()

    def llm_json(self, system: str, user: str) -> dict:
        """Ollama com saída restrita a JSON. Uma segunda tentativa cobre o raro caso de JSON malformado."""
        last = None
        for attempt in range(2):
            body = {
                "model": config.LLM_MODEL, "stream": False, "think": False, "keep_alive": 0, "format": "json",
                "options": {"temperature": 0.6 if attempt == 0 else 0.2, "num_ctx": 16384},  # o padrão do Ollama (~4 mil tokens) cortaria o roteiro
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
            req = urllib.request.Request(config.OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as r:
                text = json.loads(r.read())["message"]["content"]
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError as e:
                last = e
        raise RuntimeError(f"o LLM não devolveu um JSON válido: {last}")

    # ------------------------------------------------- voz e legendas
    def tts(self, text: str, voice: str, speed: float, out_wav: str) -> float:
        return float(self._child("tts").call({"op": "tts", "text": text, "voice": voice, "speed": speed, "out": out_wav}))

    def align(self, wav: str, words: list[str], duration: float) -> list[list]:
        return self._child("align").call({"op": "align", "wav": wav, "words": words, "duration": duration})

    def transcribe_lyrics(self, path: str, duration: float | None = None) -> list[dict]:
        return self._child("align").call({"op": "transcribe", "path": path, "language": "pt"})["segments"]

    # --------------------------------------------------------- imagens
    def _make_room(self, engine: str | None = None) -> None:
        """O ComfyUI mantém os modelos em RAM entre execuções. Ao trocar de motor (FLUX/Wan/LTX), ou quando a
        RAM disponível está baixa, descarrega tudo antes: sem isso Wan + LTX juntos estouraram os 30 GB da andes."""
        switched = engine is not None and engine != self._last_engine
        if switched or mem_available_gb() < MIN_FREE_GB:
            self.comfy.free()
        self._last_engine = engine

    def image(self, prompt: str, profile: dict, seed: int, out_png: str, size: tuple[int, int]) -> None:
        self._make_room("flux")
        outputs = self.comfy.run(self.comfy.flux_workflow(prompt, profile, seed, "mc_img"), should_stop=cancel.requested)
        info = next(v["images"][0] for v in outputs.values() if v.get("images"))
        with open(out_png, "wb") as f:
            f.write(self.comfy.fetch(info))

    def clip(self, engine: str, image: str, prompt: str, out_mp4: str, seconds: float, seed: int = 7) -> bool:
        self._make_room(engine)
        w, h = CLIP_SIZE[engine]
        frames = max(25, int(seconds * 24) // 8 * 8 + 1)  # LTX/Wan pedem 8n+1 quadros
        name = self.comfy.upload(image, "mc_clip_input.png")
        build = self.comfy.ltx_workflow if engine == "ltx" else self.comfy.wan_workflow
        outputs = self.comfy.run(build(name, prompt, w, h, frames, f"mc_{engine}", seed), timeout=3 * 3600, should_stop=cancel.requested)
        info = next((v["images"][0] for v in outputs.values() if v.get("images")), None)
        if info is None:
            raise ComfyError("ComfyUI não devolveu o vídeo")
        with open(out_mp4, "wb") as f:
            f.write(self.comfy.fetch(info))
        return True

    # ---------------------------------------------------- descarregar
    def unload(self, stage: str) -> None:
        if stage in ("tts", "align"):
            child = self._children.pop(stage, None)
            if child:
                child.close()
        elif stage in ("image", "clip"):
            self.comfy.free()

    def close(self) -> None:
        for c in list(self._children.values()):
            c.close()
        self._children.clear()
