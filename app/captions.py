"""Legendas: alinha o TEXTO ORIGINAL aos tempos do Whisper e gera o arquivo ASS.

O Whisper erra grafias (ex.: "Levy") e pode inventar interjeições; por isso a legenda usa sempre
as palavras do roteiro e o Whisper só fornece os instantes em que cada palavra é falada.
"""
import difflib
import re
import unicodedata


def norm(word: str) -> str:
    w = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", w)


def align_words(orig: list[str], heard: list[tuple[str, float, float]], duration: float) -> list[list]:
    """Retorna [[palavra_original, início, fim], ...] com o mesmo tamanho de `orig`.

    `heard` = palavras reconhecidas (texto, início, fim). Palavras sem correspondência são
    interpoladas, proporcionalmente ao tamanho, entre as âncoras vizinhas.
    """
    o_norm = [norm(w) for w in orig]
    h_norm = [norm(w) for w, _, _ in heard]
    times: list[tuple[float, float] | None] = [None] * len(orig)
    sm = difflib.SequenceMatcher(a=o_norm, b=h_norm, autojunk=False)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            _, s, e = heard[block.b + k]
            times[block.a + k] = (s, e)

    i = 0
    while i < len(orig):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(orig) and times[j] is None:
            j += 1
        left = times[i - 1][1] if i > 0 else 0.0
        right = times[j][0] if j < len(orig) else duration
        right = max(right, left)
        weights = [max(1, len(orig[k])) for k in range(i, j)]
        total, acc = sum(weights), left
        for k, wgt in zip(range(i, j), weights):
            span = (right - left) * wgt / total
            times[k] = (acc, acc + span)
            acc += span
        i = j
    return [[w, round(t[0], 3), round(t[1], 3)] for w, t in zip(orig, times)]


def proportional_words(orig: list[str], duration: float) -> list[list]:
    """Tempos estimados pelo tamanho das palavras (usado no backend de teste)."""
    weights = [max(1, len(w)) for w in orig]
    total, acc, out = sum(weights), 0.0, []
    for w, wgt in zip(orig, weights):
        span = duration * wgt / total
        out.append([w, round(acc, 3), round(acc + span, 3)])
        acc += span
    return out


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


FONTS = {"serif": "DejaVu Serif", "sans": "DejaVu Sans", "mono": "DejaVu Sans Mono"}


def chunk_words(words: list[list], max_words: int = 7, max_chars: int = 44) -> list[list[list]]:
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x[0] for x in cur)
        if len(cur) >= max_words or len(text) >= max_chars or re.search(r"[.!?…:;]$", w[0]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    if len(chunks) >= 2 and len(chunks[-1]) <= 2 and not re.search(r"[.!?…:;]$", chunks[-2][-1][0]):   # sobra de uma ou duas palavras: reparte o fim em duas partes parecidas
        both = chunks[-2] + chunks[-1]
        half = (len(both) + 1) // 2
        chunks[-2:] = [both[:half], both[half:]]
    return chunks


def make_events(scene_words: list[tuple[float, list[list]]], max_words: int = 7, max_chars: int = 44) -> list[list]:
    """Linhas de legenda [[início, fim, texto], ...] que o vídeo mostra (já sem sobreposição entre uma e outra)."""
    events = []
    for offset, words in scene_words:
        for chunk in chunk_words(words, max_words, max_chars):
            text = " ".join(w[0] for w in chunk)
            events.append([round(offset + chunk[0][1], 2), round(offset + chunk[-1][2] + 0.15, 2), text])
    for cur, nxt in zip(events, events[1:]):  # o "segura" de 0,15 s nunca invade o trecho seguinte (senão as duas linhas empilham)
        cur[1] = round(max(cur[0] + 0.05, min(cur[1], nxt[0])), 2)
    return events


def build_ass(scene_words: list[tuple[float, list[list]]], width: int, height: int, style: dict, *, max_words: int = 7, max_chars: int = 44,
              size_div: float = 24, margin_frac: float = 0.06, side_frac: float = 0.08, hook: str | None = None, hook_seconds: float = 3.5,
              events: list[list] | None = None) -> str:
    """scene_words = [(início_da_cena_em_s, [[palavra, ini, fim], ...]), ...]

    Os parâmetros opcionais servem ao formato vertical (Shorts): linhas mais curtas, margem maior embaixo e uma frase de gancho no topo.
    `events` (linhas já prontas, p.ex. editadas à mão) substitui o cálculo a partir de `scene_words`."""
    font = FONTS.get(style.get("font", "sans"), "DejaVu Sans")
    size = max(14, round(height / size_div))
    color = _ass_color(style.get("color", "#FFFFFF"))
    margin_v = round(height * margin_frac)
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{font},{size},{color},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,"
        f"{round(width * side_frac)},{round(width * side_frac)},{margin_v},1\n"
        + (f"Style: Hook,{font},{round(size * 0.85)},&H0000C8FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,"
           f"{round(width * side_frac)},{round(width * side_frac)},{round(height * 0.09)},1\n" if hook else "")
        + "\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    if events is None:
        events = make_events(scene_words, max_words, max_chars)
    lines = [f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{t.replace('{', '(').replace('}', ')')}" for a, b, t in events]
    if hook:
        safe = hook.replace("{", "(").replace("}", ")").replace("\n", " ")
        lines.insert(0, f"Dialogue: 1,{_ass_time(0.0)},{_ass_time(hook_seconds)},Hook,,0,0,0,,{safe}")
    return head + "\n".join(lines) + "\n"
