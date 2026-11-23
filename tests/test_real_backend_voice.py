"""Protocolo do processo filho de voz (com modelos de mentira): sobe, atende, e morre no unload."""
import os
import wave

import pytest

from app.pipeline.backends.real import RealBackend


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setenv("MC_VOICE_STUB", "1")  # herdado pelo processo filho


def test_tts_and_align_children_live_and_die(tmp_path):
    b = RealBackend()
    wav = str(tmp_path / "a.wav")
    dur = b.tts("uma frase curta para testar o filho de voz", "pm_alex", 0.85, wav)
    assert dur > 1.0 and wave.open(wav).getnframes() > 0
    pid = b._children["tts"].proc.pid
    os.kill(pid, 0)                                           # está vivo

    words = "uma frase curta".split()
    out = b.align(wav, words, dur)
    assert [w[0] for w in out] == words and out[-1][2] <= dur + 1e-3  # tempos são arredondados a 3 casas

    b.unload("tts")
    assert "tts" not in b._children
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)                                       # morreu: RAM/VRAM devolvidas
    assert "align" in b._children
    b.close()
    assert not b._children


def test_error_from_child_is_raised_not_swallowed(tmp_path):
    b = RealBackend()
    with pytest.raises(RuntimeError):
        b.tts("texto", "pm_alex", 0.85, str(tmp_path / "nao" / "existe" / "a.wav"))  # pasta inexistente
    # o filho continua útil depois de um erro
    assert b.tts("outro texto aqui", "pm_alex", 0.85, str(tmp_path / "ok.wav")) > 0
    b.close()


def test_comfy_is_freed_when_engine_changes_or_ram_is_low(monkeypatch, tmp_path):
    """Regressão do OOM na andes: Wan + LTX carregados juntos estouravam a RAM."""
    from app.pipeline.backends import real

    b = real.RealBackend()
    calls = {"free": 0}
    b.comfy.free = lambda: calls.__setitem__("free", calls["free"] + 1)
    b.comfy.upload = lambda path, name: name
    b.comfy.run = lambda wf, timeout=0, should_stop=None: {"1": {"images": [{"filename": "x.mp4"}]}}
    b.comfy.fetch = lambda info: b"video"
    img = tmp_path / "i.png"
    img.write_bytes(b"png")

    monkeypatch.setattr(real, "mem_available_gb", lambda: 25.0)
    for engine in ("wan", "wan", "wan", "ltx", "ltx"):
        b.clip(engine, str(img), "move", str(tmp_path / "o.mp4"), 4.0)
    assert calls["free"] == 2                      # só na 1ª vez (wan) e na troca para ltx

    calls["free"] = 0
    monkeypatch.setattr(real, "mem_available_gb", lambda: 5.0)   # RAM baixa: descarrega a cada clipe
    for _ in range(3):
        b.clip("ltx", str(img), "move", str(tmp_path / "o.mp4"), 4.0)
    assert calls["free"] == 3
