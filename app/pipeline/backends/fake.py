"""Backend de teste: roda em CPU, sem modelos. Serve para desenvolver a interface e o pipeline."""
import hashlib
import math
import os
import time
import struct
import textwrap
import wave

from PIL import Image, ImageDraw

from ... import captions, config

SR = 24000


class FakeBackend:
    name = "fake"

    def visual_prompt(self, scene_text: str, system: str | None = None, extra: str = "") -> str:
        excerpt = " ".join(scene_text.split()[:28])
        return f"an evocative scene illustrating: {excerpt}"

    def llm_text(self, system: str, user: str, max_tokens: int = 1200) -> str:
        n = max(30, min(240, max_tokens // 3))
        base = "A história desta ideia começa pequena, mas cresce quando olhamos para as fontes e para as pessoas que a defenderam em público".split()
        words = (base * (n // len(base) + 1))[:n]
        half = len(words) // 2
        return " ".join(words[:half]) + ".\n\n" + " ".join(words[half:]) + "."

    def llm_json(self, system: str, user: str) -> dict:
        """Respostas determinísticas para o modo de teste (a forma é a mesma que o LLM real devolve)."""
        words = user.split()
        if "ESBOÇO" in system:
            return {"tese": "A tese de teste do vídeo.", "gancho": "Você já se perguntou por que isso importa?",
                    "secoes": [{"titulo": f"Seção {i + 1}", "objetivo": "explicar", "pontos": ["um ponto segundo uma fonte", "outro ponto"]} for i in range(4)],
                    "fecho": "E você, o que acha?", "fontes": ["Autor de Teste, Livro de Teste, 2001"], "incertezas": ["confirmar a data citada"]}
        topic = " ".join(words[:5]).strip(".,:;") or "Vídeo"
        if "trechos" in system:  # pedido de títulos de capítulos
            n = user.count("[trecho")
            return {"titles": [f"Parte {i + 1}: {topic}"[:40] for i in range(n)]}
        return {
            "titles": [f"{topic} — versão {i + 1}" for i in range(5)],
            "intro": f"Neste vídeo exploramos {topic.lower()}.\n\nVeja até o fim e compartilhe sua opinião nos comentários.",
            "tags": [f"tag{i}" for i in range(15)],
            "hashtags": ["#filosofia", "#ocultismo", "#tecnologia"],
            "thumb_text": " ".join(words[:3]).upper() or "ASSISTA",
            "thumb_prompt": "a lone figure facing a glowing doorway, dramatic lighting, high contrast, empty space on the left",
        }

    def tts(self, text: str, voice: str, speed: float, out_wav: str) -> float:
        words = max(1, len(text.split()))
        seconds = max(1.0, words / (config.WORDS_PER_SECOND * (speed / config.DEFAULT_SPEED)))
        n = int(seconds * SR)
        frames = bytearray()
        for i in range(n):
            t = i / SR
            env = 0.5 * (1 + math.sin(2 * math.pi * 3.0 * t))  # "sílabas" a 3 Hz
            frames += struct.pack("<h", int(2500 * env * math.sin(2 * math.pi * 170 * t)))
        with wave.open(out_wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(bytes(frames))
        return n / SR

    def align(self, wav: str, words: list[str], duration: float) -> list[list]:
        return captions.proportional_words(words, duration)

    def transcribe_lyrics(self, path: str, duration: float | None = None) -> list[dict]:
        d = float(duration or 30.0)
        return [{"start": round(d * i / 5, 2), "end": round(d * (i + 0.8) / 5, 2), "text": f"Linha {i + 1} da letra de teste"} for i in range(5)]

    def image(self, prompt: str, profile: dict, seed: int, out_png: str, size: tuple[int, int]) -> None:
        time.sleep(float(os.getenv("MC_FAKE_DELAY", "0")))  # só para demonstrar a interface com jobs demorados
        w, h = size
        digest = hashlib.sha256(f"{profile.get('id')}-{seed}".encode()).digest()
        top = tuple(40 + digest[i] % 120 for i in range(3))
        bottom = tuple(10 + digest[3 + i] % 60 for i in range(3))
        img = Image.new("RGB", (w, h))
        px = ImageDraw.Draw(img)
        for y in range(h):
            f = y / max(1, h - 1)
            px.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - f) + bottom[i] * f) for i in range(3)))
        d = ImageDraw.Draw(img)
        d.text((12, 10), f"[teste] {profile.get('name', '?')}  seed {seed}", fill=(255, 255, 255))
        y = 34
        for line in textwrap.wrap(prompt, width=max(20, w // 8))[:8]:
            d.text((12, y), line, fill=(230, 230, 230))
            y += 14
        img.save(out_png)

    def clip(self, engine: str, image: str, prompt: str, out_mp4: str, seconds: float, seed: int = 7) -> bool:
        from .. import assemble

        assemble.ken_burns_segment(image, min(seconds, 4.0), out_mp4, variant=1, fade=0.0)
        return True

    def unload(self, stage: str) -> None:
        pass
