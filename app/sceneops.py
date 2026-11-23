"""Operações sobre as cenas de um projeto: mesclar, dividir, apagar e adicionar.

Todas devolvem (cenas, arquivos_a_apagar). Os arquivos de cada cena são nomeados pelo `id` (não pelo número),
então renumerar nunca faz uma cena sobrescrever o arquivo de outra.
"""
import re

from . import scenes as scn


class OpError(ValueError):
    pass


def ensure_ids(items: list[dict]) -> None:
    """Projetos antigos nomeavam os arquivos pelo número; congela esse nome como id antes de renumerar."""
    for s in items:
        s.setdefault("id", f"{s['n']:03d}")


def renumber(items: list[dict]) -> None:
    for i, s in enumerate(items, 1):
        s["n"] = i


def _index(items: list[dict], n: int) -> int:
    for i, s in enumerate(items):
        if s["n"] == n:
            return i
    raise OpError("cena não encontrada")


def _files(s: dict, *, keep_visual: bool = False) -> list[str]:
    keys = ("audio",) if keep_visual else ("audio", "image", "thumb", "clip")
    return [s[k] for k in keys if s.get(k)]


def _inherit_visual(new: dict, old: dict) -> None:
    new.update(visual_prompt=old["visual_prompt"], profile_id=old["profile_id"], motion=old["motion"], seed=old["seed"])


def delete(items: list[dict], n: int) -> list[str]:
    ensure_ids(items)
    i = _index(items, n)
    if len(items) == 1:
        raise OpError("o projeto precisa ter pelo menos uma cena")
    removed = _files(items.pop(i))
    renumber(items)
    return removed


def merge_next(items: list[dict], n: int) -> list[str]:
    ensure_ids(items)
    i = _index(items, n)
    if i + 1 >= len(items):
        raise OpError("não há cena seguinte para mesclar")
    a, b = items[i], items[i + 1]
    new = scn.new_scene(a["n"], f"{a['text']} {b['text']}")
    _inherit_visual(new, a)
    if a.get("image"):  # a imagem e o clipe da primeira cena continuam valendo; só a narração é refeita
        new.update(image=a["image"], thumb=a.get("thumb"), clip=a.get("clip"), dirty_image=False)
    items[i:i + 2] = [new]
    renumber(items)
    return _files(a, keep_visual=True) + _files(b)


def split(items: list[dict], n: int, at: int) -> list[str]:
    """Divide a cena no caractere `at` (ajustado para o limite de palavra mais próximo)."""
    ensure_ids(items)
    i = _index(items, n)
    s = items[i]
    text = s["text"]
    if not 0 < at < len(text):
        raise OpError("posição de corte inválida")
    ws = [m.start() for m in re.finditer(r"\s+", text)]
    if not ws:
        raise OpError("a cena tem uma palavra só; não dá para dividir")
    cut = min(ws, key=lambda p: abs(p - at))
    left, right = text[:cut].strip(), text[cut:].strip()
    if not left or not right:
        raise OpError("posição de corte inválida")
    first, second = scn.new_scene(s["n"], left), scn.new_scene(s["n"] + 1, right)
    _inherit_visual(first, s)
    _inherit_visual(second, s)
    second["motion"] = "ken_burns"
    second["seed"] = s["seed"] + 101
    if s.get("image"):  # a primeira metade mantém a imagem; a segunda ganha uma nova
        first.update(image=s["image"], thumb=s.get("thumb"), clip=s.get("clip"), dirty_image=False)
    items[i:i + 1] = [first, second]
    renumber(items)
    return _files(s, keep_visual=True)


def add(items: list[dict], after: int, text: str) -> None:
    ensure_ids(items)
    text = " ".join(text.split())
    if not text:
        raise OpError("o texto da cena está vazio")
    pos = 0 if after <= 0 else _index(items, after) + 1
    items.insert(pos, scn.new_scene(pos + 1, text))
    renumber(items)
