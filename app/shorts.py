"""Shorts: cortes verticais (1080x1920) de 30 a 45 s tirados do vídeo pronto.

O trecho sempre começa e termina em limites de cena (a fala nunca é cortada no meio). A escolha é feita pelo LLM da andes
(os trechos que melhor funcionam sozinhos, começando por uma pergunta ou afirmação forte); se ele falhar ou responder algo
inválido, uma pontuação simples por texto escolhe no lugar. A montagem usa o vídeo SEM legendas (`video_raw.mp4`) e a
narração originais, e refaz as legendas em tamanho vertical.
"""
import re

MIN_S, MAX_S = 30.0, 45.0
HOOK_WORDS = ("segredo", "ninguém", "nunca", "verdade", "descobr", "mas ", "por que", "como ", "morte", "máquina", "inteligência artificial",
              "alquimia", "magia", "futuro", "consciência", "oculto", "proibido", "poder", "perigo", "sentido", "?")
LAYOUTS = {"blur": "Imagem inteira com fundo desfocado (recomendado)", "crop": "Preencher a tela (corta as laterais)"}

SYSTEM_SHORTS = (
    "Você escolhe os melhores trechos de um roteiro para virarem YouTube Shorts em português do Brasil. Cada trecho é uma "
    "sequência de cenas seguidas e deve durar de 30 a 45 segundos somando as durações indicadas. Escolha trechos que façam "
    "sentido sozinhos, que comecem por uma pergunta ou afirmação forte e que terminem em uma ideia completa; sem sobreposição "
    "entre trechos. Responda SOMENTE com JSON no formato "
    '{{"shorts": [{{"start_scene": N, "end_scene": M, "hook": "frase de até 8 palavras para o topo da tela", '
    '"title": "título de até 60 caracteres, sem caixa alta e sem emoji"}}]}} com exatamente {n} itens, em ordem de cena.'
)


def _scene_end(s: dict) -> float:
    return s["start"] + s["duration"]


def windows(items: list[dict], min_s: float = MIN_S, max_s: float = MAX_S) -> list[tuple[int, int]]:
    """Todas as janelas (índice inicial, índice final) de cenas seguidas com duração entre min_s e max_s."""
    out = []
    for i in range(len(items)):
        total = 0.0
        for j in range(i, len(items)):
            total += items[j]["duration"]
            if total > max_s:
                break
            if total >= min_s:
                out.append((i, j))
    return out


def score(items: list[dict], i: int, j: int) -> float:
    text = " ".join(s["text"] for s in items[i:j + 1]).lower()
    first = items[i]["text"].strip()
    pts = 3.0 * ("?" in first) + sum(1.0 for w in HOOK_WORDS if w in text) + 0.5 * len(re.findall(r"\d", text[:200]))
    pts += 1.0 if re.search(r"[.!?…]$", items[j]["text"].strip()) else -1.0          # termina numa ideia fechada
    pts += 1.0 if i == 0 or re.search(r"[.!?…]$", items[i - 1]["text"].strip()) else -0.5  # começa numa frase nova
    pts -= 2.0 if i == 0 else 0.0                                                        # a abertura do vídeo já tem seu gancho
    return pts


def pick_by_score(items: list[dict], count: int, taken: list[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
    """Os `count` melhores trechos sem sobreposição (greedy por pontuação), em ordem de cena."""
    chosen = list(taken or [])
    ranked = sorted(windows(items), key=lambda w: (-score(items, *w), w[0]))
    for w in ranked:
        if len(chosen) >= count:
            break
        if all(w[1] < c[0] or w[0] > c[1] for c in chosen):
            chosen.append(w)
    return sorted(chosen)


def _first_words(text: str, n: int) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")[:n]
    return " ".join(words).strip(" ,;:-—") + ("…" if len(text.split()) > n else "")


def llm_pick(items: list[dict], count: int, backend) -> list[dict]:
    """Pede ao LLM os trechos; devolve só os válidos ({i, j, hook, title}), já sem sobreposição."""
    lines = "\n".join(f"[cena {s['n']} | {s['duration']:.0f}s] {s['text']}" for s in items)
    try:
        data = backend.llm_json(SYSTEM_SHORTS.format(n=count), lines[:14000])
    except Exception:
        return []
    by_n = {s["n"]: k for k, s in enumerate(items)}
    out: list[dict] = []
    for r in (data.get("shorts") or [])[: count + 2]:
        try:
            i, j = by_n[int(r["start_scene"])], by_n[int(r["end_scene"])]
        except (KeyError, TypeError, ValueError):
            continue
        if j < i:
            continue
        dur = sum(s["duration"] for s in items[i:j + 1])
        if not (MIN_S - 5 <= dur <= MAX_S + 5) or any(not (j < o["i"] or i > o["j"]) for o in out):
            continue
        out.append({"i": i, "j": j, "hook": _first_words(str(r.get("hook") or ""), 8), "title": " ".join(str(r.get("title") or "").split())[:60]})
    return out[:count]


def choose(items: list[dict], count: int, backend=None) -> list[dict]:
    """Trechos finais: o que o LLM sugeriu (se válido) completado por pontuação. Cada um: i, j, hook, title."""
    picked = llm_pick(items, count, backend) if backend is not None else []
    if len(picked) < count:
        extra = pick_by_score(items, count, [(p["i"], p["j"]) for p in picked])
        have = {(p["i"], p["j"]) for p in picked}
        for i, j in extra:
            if (i, j) not in have:
                picked.append({"i": i, "j": j, "hook": "", "title": ""})
    picked = sorted(picked[:count], key=lambda p: p["i"])
    for p in picked:
        if not p["hook"]:
            p["hook"] = _first_words(items[p["i"]]["text"], 8)
        if not p["title"]:
            p["title"] = _first_words(items[p["i"]]["text"], 10)[:60]
    return picked


def description(hook: str, hashtags: list[str] | None, title: str) -> str:
    tags = " ".join((hashtags or [])[:3]) or "#ocultismo #filosofia #tecnologia"
    return f"{hook}\n\nO vídeo completo está no canal. Se você curtiu, se inscreva para a próxima parte.\n\n#Shorts {tags}".strip()
