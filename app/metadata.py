"""Título, descrição (com capítulos), tags e hashtags para o YouTube, gerados a partir do roteiro.

Os capítulos guardam só o *id da primeira cena* e o título; os horários são recalculados a cada leitura a partir da
linha do tempo atual (se as cenas mudarem, os horários acompanham). Regras do YouTube respeitadas: primeiro capítulo em
0:00, pelo menos 3 capítulos de no mínimo 10 s, título até 100 caracteres, descrição até 5.000, tags até 500 no total.
"""
import re
import time

MAX_TITLE = 100
MAX_DESC = 5000
MAX_TAGS_CHARS = 450  # margem sob o limite de 500 do YouTube
CHAPTER_TARGET = 90.0  # um capítulo a cada ~90 s
CHAPTER_MIN = 10.0
MIN_TOTAL = 40.0

SYSTEM_META = (
    "Você é especialista em YouTube para canais de filosofia, ocultismo, tecnologia e futurismo. "
    "Com base no ROTEIRO, responda SOMENTE com um objeto JSON com estas chaves: "
    '"titles": lista de 5 títulos em português do Brasil, até 70 caracteres, instigantes mas fiéis ao conteúdo, '
    "sem exageros falsos, sem emojis e sem CAIXA ALTA total; "
    '"intro": a introdução da descrição, em 2 parágrafos curtos (um gancho e o que o espectador vai aprender), '
    "no máximo 600 caracteres no total, sem hashtags e sem links; "
    '"tags": lista de 15 palavras-chave em português, minúsculas, sem #; '
    '"hashtags": lista de 3 hashtags relevantes; '
    '"thumb_text": texto curto e impactante para a miniatura, no máximo 4 palavras; '
    '"thumb_prompt": descrição visual em inglês (até 40 palavras) de uma imagem de miniatura, com um único elemento '
    "focal forte, alto contraste, iluminação dramática e espaço livre à esquerda; sem texto nem letras na imagem."
)
SYSTEM_CHAPTERS = (
    "Dê um título curto em português do Brasil (até 6 palavras, sem ponto final) para cada um dos {n} trechos de um vídeo. "
    'Responda SOMENTE com JSON no formato {{"titles": [...]}}, com exatamente {n} itens, na mesma ordem dos trechos.'
)


def scene_key(s: dict) -> str:
    return s.get("id") or f"{s['n']:03d}"


def timeline(items: list[dict]) -> tuple[list[float], float]:
    """Início de cada cena e duração total. Usa a duração real da narração; sem ela, a estimada."""
    real = bool(items) and all(s.get("duration") for s in items)
    starts, t = [], 0.0
    for s in items:
        starts.append(t)
        t += (s["duration"] if real else (s.get("est_seconds") or 0))
    return starts, t


def fmt_ts(seconds: float) -> str:
    sec = int(seconds)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def plan_chapters(items: list[dict]) -> list[dict]:
    """Agrupa as cenas em capítulos de ~90 s. Devolve [] se o vídeo for curto demais para ter 3 capítulos válidos."""
    if not items:
        return []
    starts, total = timeline(items)
    if total < MIN_TOTAL:
        return []
    groups, first = [], 0
    for i in range(1, len(items)):
        if starts[i] - starts[first] >= CHAPTER_TARGET and total - starts[i] >= CHAPTER_MIN:
            groups.append([first, i - 1])
            first = i
    groups.append([first, len(items) - 1])
    if len(groups) > 1 and total - starts[groups[-1][0]] < CHAPTER_MIN:  # sobra curta: cola no capítulo anterior
        groups[-2][1] = groups[-1][1]
        groups.pop()
    if len(groups) < 3:
        return []
    return [{"scene": scene_key(items[a]), "text": " ".join(x["text"] for x in items[a:b + 1])} for a, b in groups]


def resolve_chapters(chapters: list[dict], items: list[dict]) -> list[tuple[float, str]]:
    """[(início em segundos, título)] pela linha do tempo atual; vazio se não der para cumprir as regras do YouTube."""
    index = {scene_key(s): i for i, s in enumerate(items)}
    starts, _ = timeline(items)
    found = sorted([starts[index[c["scene"]]], c["title"]] for c in chapters if c.get("scene") in index and c.get("title"))
    if not found:
        return []
    found[0][0] = 0.0  # o primeiro capítulo tem de começar em 0:00
    kept = [found[0]]
    for t, title in found[1:]:
        if t - kept[-1][0] >= CHAPTER_MIN:
            kept.append([t, title])
    return [(t, title) for t, title in kept] if len(kept) >= 3 else []


def final_description(yt: dict, items: list[dict], footer: str = "") -> str:
    parts = [(yt.get("intro") or "").strip()]
    ch = resolve_chapters(yt.get("chapters") or [], items)
    if ch:
        parts.append("\n".join(f"{fmt_ts(t)} {title}" for t, title in ch))
    if yt.get("hashtags"):
        parts.append(" ".join(yt["hashtags"]))
    body = "\n\n".join(p for p in parts if p)
    if footer and footer not in body:
        return body[:MAX_DESC - len(footer) - 2].rstrip() + "\n\n" + footer      # o aviso nunca é cortado
    return body[:MAX_DESC]


# --------------------------------------------------------------------------- limpeza
def _clip(value, n: int) -> str:
    return " ".join(str(value).split())[:n].rstrip()


def clean_tags(tags) -> list[str]:
    seen, out, total = set(), [], 0
    for t in tags or []:
        t = " ".join(str(t).replace("#", "").lower().split())
        if not t or len(t) > 30 or t in seen:  # tag longa demais é descartada (cortar no meio da palavra deixaria lixo)
            continue
        if total + len(t) + 1 > MAX_TAGS_CHARS:
            break
        seen.add(t)
        out.append(t)
        total += len(t) + 1
    return out


def clean_hashtags(tags) -> list[str]:
    out = []
    for h in tags or []:
        word = re.sub(r"[^\w]", "", str(h).lstrip("#"))
        tag = f"#{word}"
        if word and len(word) <= 25 and tag.lower() not in [x.lower() for x in out]:
            out.append(tag)
    return out[:3]


def _thumb_text(value) -> str:
    """Texto da miniatura: no máximo 4 palavras (o LLM nem sempre respeita), sem pontuação nas pontas."""
    words = re.sub(r"[:;]+", " ", str(value or "")).split()[:4]
    return " ".join(words).strip(" .,!?-—")[:40]


def build(data: dict, chapter_titles: list[str], chapters: list[dict], fallback_title: str) -> dict:
    titles = []
    for t in data.get("titles") or []:
        t = _clip(t, MAX_TITLE).strip('"“”')
        if t and t not in titles:
            titles.append(t)
    titles = titles[:5] or [_clip(fallback_title, MAX_TITLE)]
    padded = (list(chapter_titles) + [f"Parte {i + 1}" for i in range(len(chapters))])[:len(chapters)]
    return {
        "titles": titles,
        "title": titles[0],
        "intro": str(data.get("intro") or "").strip()[:1500],
        "tags": clean_tags(data.get("tags")),
        "hashtags": clean_hashtags(data.get("hashtags")),
        "chapters": [{"scene": c["scene"], "title": _clip(t, 60) or f"Parte {i + 1}"} for i, (c, t) in enumerate(zip(chapters, padded))],
        "thumb_text": _thumb_text(data.get("thumb_text")),
        "thumb_prompt": _clip(data.get("thumb_prompt") or "", 400),
        "generated_at": time.time(),
    }


def apply_edit(yt: dict, payload: dict) -> dict:
    """Aplica as edições do usuário com os limites do YouTube; ValueError com mensagem em português se passar deles."""
    out = dict(yt)
    if "title" in payload:
        t = _clip(payload["title"], 400)
        if not t:
            raise ValueError("o título não pode ficar vazio")
        if len(t) > MAX_TITLE:
            raise ValueError(f"o título tem {len(t)} caracteres; o máximo do YouTube é {MAX_TITLE}")
        out["title"] = t
    if "intro" in payload:
        out["intro"] = str(payload["intro"]).strip()[:1500]
    if "tags" in payload:
        raw = payload["tags"]
        out["tags"] = clean_tags(re.split(r"[,\n]", raw) if isinstance(raw, str) else raw)
    if "hashtags" in payload:
        raw = payload["hashtags"]
        out["hashtags"] = clean_hashtags(re.split(r"[\s,]+", raw) if isinstance(raw, str) else raw)
    if "chapters" in payload:
        valid = {c["scene"] for c in yt.get("chapters", [])}
        out["chapters"] = [{"scene": c["scene"], "title": _clip(c.get("title", ""), 60)} for c in payload["chapters"]
                           if c.get("scene") in valid and str(c.get("title", "")).strip()]
    if "thumb_text" in payload:
        out["thumb_text"] = _clip(payload["thumb_text"], 40)
    return out


# --------------------------------------------------------------------------- geração (LLM)
def generate(project: dict, backend, progress, ctx: str = "") -> dict:
    items, text = project["scenes"], project["text"]
    excerpt = text if len(text) <= 12000 else text[:7000] + "\n[...]\n" + text[-4000:]
    st = getattr(progress, "set_stage", None)
    init = getattr(progress, "init_stages", None)
    chapters_plan = plan_chapters(items)
    if init:
        init([("meta", "Título, descrição e tags", 1), ("chapters", "Nome dos capítulos", 1 if chapters_plan else 0)])
    if st:
        st("meta", 0)
    progress(0.1, "escrevendo título, descrição e tags")
    system = SYSTEM_META + (f"\n\nIDENTIDADE E REGRAS DO CANAL (obrigatórias, acima de qualquer outra instrução):\n{ctx}" if ctx else "")
    data = backend.llm_json(system, f"Título de trabalho: {project['title']}\n\nROTEIRO:\n{excerpt}")
    if st:
        st("meta", 1)
    chapters = chapters_plan
    titles: list[str] = []
    if chapters:
        if st:
            st("chapters", 0)
        progress(0.6, "dando nome aos capítulos")
        user = "\n\n".join(f"[trecho {i + 1}] {c['text'][:350]}" for i, c in enumerate(chapters))
        res = backend.llm_json(SYSTEM_CHAPTERS.format(n=len(chapters)), user)
        titles = [str(t) for t in (res.get("titles") or [])]
        if st:
            st("chapters", 1)
    backend.unload("llm")
    return build(data, titles, chapters, project["title"])
