"""Divide o roteiro em cenas (~9 s cada) e distribui as cenas que serão animadas."""
import re
import uuid

from . import config

MARKER = re.compile(r"^\s*\[cena\]\s*$", re.IGNORECASE | re.MULTILINE)
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def count_words(text: str) -> int:
    return len(text.split())


def est_seconds(text: str) -> float:
    return round(count_words(text) / config.WORDS_PER_SECOND, 1)


def _sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in SENTENCE_END.split(paragraph.strip()) if s.strip()]


def _group(sentences: list[str], target: float) -> list[str]:
    """Agrupa frases consecutivas até chegar perto da duração-alvo da cena."""
    scenes, cur = [], []
    for s in sentences:
        cand = " ".join(cur + [s])
        if cur and est_seconds(cand) > target * 1.25:
            scenes.append(" ".join(cur))
            cur = [s]
        else:
            cur.append(s)
        if est_seconds(" ".join(cur)) >= target:
            scenes.append(" ".join(cur))
            cur = []
    if cur:
        tail = " ".join(cur)
        # sobra muito curta: cola na cena anterior em vez de virar cena própria
        if scenes and est_seconds(tail) < target * 0.4:
            scenes[-1] = f"{scenes[-1]} {tail}"
        else:
            scenes.append(tail)
    return scenes


def split_text(text: str, target: float | None = None) -> list[str]:
    target = target or config.SCENE_TARGET_SECONDS
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    if MARKER.search(text):  # cortes manuais do autor
        return [" ".join(part.split()) for part in MARKER.split(text) if part.strip()]
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if para:
            out.extend(_group(_sentences(para), target))
    return out


def pick_animated(n_scenes: int, ratio: float) -> set[int]:
    """Índices (0-based) das cenas animadas, espaçados de forma uniforme; a 1ª sempre entra (gancho)."""
    k = round(n_scenes * ratio)
    if k <= 0 or n_scenes == 0:
        return set()
    if k >= n_scenes:
        return set(range(n_scenes))
    step = n_scenes / k
    return {min(n_scenes - 1, int(i * step)) for i in range(k)}


def new_scene(n: int, text: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],  # identifica os arquivos da cena; o número n muda quando cenas são movidas/apagadas
        "n": n,
        "text": text,
        "est_seconds": est_seconds(text),
        "visual_prompt": "",
        "profile_id": None,  # None = herda o perfil do projeto
        "motion": "ken_burns",  # ken_burns | ltx | wan
        "seed": 1000 + n,
        "audio": None,
        "duration": None,
        "words": None,
        "image": None,
        "thumb": None,
        "clip": None,
        "dirty_audio": True,
        "dirty_image": True,
    }
