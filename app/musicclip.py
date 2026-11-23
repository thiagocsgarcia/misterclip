"""Clipe musical: análise da música, cenas cortadas no ritmo, letra por cena e a "bíblia visual" da história.

O clipe conta a HISTÓRIA da letra (nunca um cantor cantando). O LLM lê a letra e define o protagonista, o cenário, a paleta e o arco
da história; cada cena recebe o momento certo desse arco, e todas repetem a mesma descrição do protagonista para as imagens
combinarem entre si. A análise (andamento, batidas, compassos e partes por intensidade) usa só numpy e roda dentro do
MisterClip, sem depender de outro serviço.
"""
import bisect
import re
import subprocess

import numpy as np

SR, HOP, NFFT = 22050, 512, 1024
FPS_ENV = SR / HOP
RITMOS = {"calmo": 4.2, "normal": 3.2, "agitado": 2.2}          # duração-alvo de cada cena, em segundos
RITMO_NOME = {"calmo": "Calmo (cortes mais longos)", "normal": "Normal", "agitado": "Agitado (cortes mais rápidos)"}
ANIMACOES = {"total": "Animar todas as cenas (recomendado)", "destaques": "Animar só as partes mais intensas", "camera": "Só movimento de câmera (mais rápido)"}
NIVEL = {0: "calma", 1: "intermediária", 2: "intensa"}
MAX_SCENE = 5.5
MIN_SCENE = 1.5


# --------------------------------------------------------------------------- áudio
def decode(path, sr: int = SR) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise ValueError("não consegui ler o áudio da música")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _frames_spectrum(y: np.ndarray):
    """Magnitudes por quadro, em blocos (música de 4 minutos tem ~10 mil quadros)."""
    n = 1 + (len(y) - NFFT) // HOP
    if n < 20:
        raise ValueError("a música é curta demais para analisar")
    win = np.hanning(NFFT).astype(np.float32)
    out = np.empty((n, NFFT // 2 + 1), dtype=np.float32)
    for a in range(0, n, 1500):
        b = min(n, a + 1500)
        idx = np.arange(NFFT)[None, :] + HOP * np.arange(a, b)[:, None]
        out[a:b] = np.abs(np.fft.rfft(y[idx] * win, axis=1))
    return out


def onset_envelope(y: np.ndarray):
    """(envoltória de ataques, envoltória só dos graves, energia em dB por quadro)."""
    S = _frames_spectrum(y)
    L = np.log1p(S * 10.0)
    edges = np.unique(np.geomspace(2, L.shape[1] - 1, 25).astype(int))
    bands = np.add.reduceat(L, edges, axis=1)
    flux = np.maximum(0.0, bands[1:] - bands[:-1]).sum(axis=1)
    low_bins = max(3, int(160 / (SR / NFFT)))
    low = np.maximum(0.0, L[1:, :low_bins] - L[:-1, :low_bins]).sum(axis=1)

    def clean(x):
        k = int(FPS_ENV * 0.5)
        mean = np.convolve(x, np.ones(k) / k, mode="same")
        z = np.maximum(0.0, x - mean)
        return z / (z.std() + 1e-9)

    rms = np.sqrt((S ** 2).mean(axis=1) + 1e-12)
    return clean(flux), clean(low), 20 * np.log10(rms + 1e-9)


def estimate_tempo(env: np.ndarray) -> tuple[float, float]:
    """Andamento (BPM) por autocorrelação da envoltória, com preferência por 70 a 160 BPM, e a confiança (0 a 1)."""
    x = env - env.mean()
    f = np.fft.rfft(x, 2 * len(x))
    ac = np.fft.irfft(f * np.conj(f))[: len(x)]
    ac = ac / (ac[0] + 1e-9)
    bpms = np.arange(60.0, 200.0, 0.25)
    lags = FPS_ENV * 60.0 / bpms

    def at(l):
        return np.interp(l, np.arange(len(ac)), ac, right=0.0)

    score = (at(lags) + 0.5 * at(2 * lags) + 0.25 * at(4 * lags)) * np.exp(-0.5 * (np.log2(bpms / 110.0) / 1.0) ** 2)
    i = int(np.argmax(score))
    conf = float(np.clip((score[i] - np.median(score)) / (abs(score[i]) + 1e-9), 0.0, 1.0))
    return float(bpms[i]), conf


def beat_grid(env: np.ndarray, bpm: float, duration: float) -> list[float]:
    """Grade de batidas com a fase que melhor casa com os ataques da música."""
    period = FPS_ENV * 60.0 / bpm
    best, best_score = 0.0, -1.0
    pooled = np.maximum.reduce([env, np.roll(env, 1), np.roll(env, -1)])
    for phase in np.arange(0.0, period, 0.5):
        pos = np.arange(phase, len(env) - 1, period)
        sc = pooled[np.round(pos).astype(int).clip(0, len(env) - 1)].sum()
        if sc > best_score:
            best, best_score = phase, sc
    times = [(best + k * period) / FPS_ENV for k in range(int((duration * FPS_ENV - best) / period) + 2)]
    return [float(round(t, 3)) for t in times if t <= duration + 60.0 / bpm]


def analyze(path) -> dict:
    y = decode(path)
    duration = len(y) / SR
    env, low, db = onset_envelope(y)
    bpm, conf = estimate_tempo(env)
    beats = beat_grid(env, bpm, duration)
    # compassos: dos 4 encaixes possíveis, o que tem mais grave nas batidas "um"
    low_at = [low[min(len(low) - 1, int(b * FPS_ENV))] for b in beats]
    k = int(np.argmax([np.mean(low_at[j::4]) if len(low_at[j::4]) else 0.0 for j in range(4)])) if len(beats) >= 8 else 0
    bars = beats[k::4]
    return {"duration": float(round(duration, 2)), "bpm": float(round(bpm, 1)), "confidence": float(round(conf, 2)), "beats": beats, "bars": [float(b) for b in bars],
            "sections": sections(bars, db, duration)}


def sections(bars: list[float], db: np.ndarray, duration: float) -> list[dict]:
    """Partes por intensidade: compassos agrupados em calma, intermediária e intensa (aproximação, não identifica estrofe nem refrão)."""
    if len(bars) < 4:
        return [{"start": 0.0, "end": round(duration, 2), "nivel": 1, "nome": NIVEL[1]}]
    edges = [0.0] + [b for b in bars[1:]] + [duration]
    en = []
    for a, b in zip(edges[:-1], edges[1:]):
        fa, fb = int(a * FPS_ENV), max(int(a * FPS_ENV) + 1, int(b * FPS_ENV))
        en.append(float(np.mean(db[fa:fb])) if fa < len(db) else float(db[-1]))
    en = np.array(en)
    sm = np.array([np.median(en[max(0, i - 1): i + 2]) for i in range(len(en))])
    lvl = _three_levels(sm)
    out = []
    for i, v in enumerate(lvl):
        if out and out[-1]["nivel"] == v:
            out[-1]["end"] = float(round(edges[i + 1], 2))
        else:
            out.append({"start": float(round(edges[i], 2)), "end": float(round(edges[i + 1], 2)), "nivel": int(v), "nome": NIVEL[int(v)]})
    return _merge_short(out)


def _three_levels(x: np.ndarray) -> list[int]:
    """Agrupa as energias (dB) em 3 níveis por k-means em 1 dimensão; se tudo é parecido (menos de 3 dB), é tudo intermediário."""
    if x.max() - x.min() < 3.0:
        return [1] * len(x)
    c = np.array([x.min(), np.median(x), x.max()], dtype=float)
    for _ in range(25):
        lab = np.argmin(np.abs(x[:, None] - c[None, :]), axis=1)
        nc = np.array([x[lab == k].mean() if np.any(lab == k) else c[k] for k in range(3)])
        if np.allclose(nc, c):
            break
        c = nc
    order = np.argsort(c)
    rank = {int(o): r for r, o in enumerate(order)}
    return [rank[int(k)] for k in lab]


def _merge_short(secs: list[dict], min_len: float = 3.0) -> list[dict]:
    """Partes muito curtas (menos de 3 s) viram parte da vizinha, para os cortes não mudarem de ritmo a toda hora."""
    changed = True
    while changed and len(secs) > 1:
        changed = False
        for i, s in enumerate(secs):
            if s["end"] - s["start"] < min_len:
                j = i - 1 if i > 0 else i + 1
                keep = secs[j]
                keep["start"], keep["end"] = float(min(keep["start"], s["start"])), float(max(keep["end"], s["end"]))
                secs.pop(i)
                changed = True
                break
    out = []
    for s in secs:
        if out and out[-1]["nivel"] == s["nivel"]:
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    return out


# --------------------------------------------------------------------------- cenas no ritmo
def _level_at(secs: list[dict], t: float) -> int:
    for s in secs:
        if s["start"] <= t < s["end"]:
            return s["nivel"]
    return secs[-1]["nivel"] if secs else 1


def choose_k(beat: float, target: float) -> int:
    ks = [2, 3, 4, 6, 8]
    ok = [k for k in ks if k * beat <= MAX_SCENE] or [2]
    return min(ok, key=lambda k: abs(k * beat - target))


def plan_cuts(an: dict, ritmo: str = "normal") -> list[dict]:
    """Cenas com início e fim sobre a grade de batidas; partes intensas cortam mais rápido e partes calmas, mais devagar."""
    target = RITMOS.get(ritmo, RITMOS["normal"])
    dur, beats, secs = an["duration"], an["beats"], an["sections"]
    beat = 60.0 / an["bpm"]
    g = list(beats)
    while g and g[0] > beat * 0.9:                    # estende a grade para trás, até o começo da música
        g.insert(0, round(g[0] - beat, 3))
    g = [t for t in g if t >= 0.0]
    i = bisect.bisect_left(g, 0.25)
    cuts = [0.0]
    if i < len(g) and g[i] > 1.5:
        cuts.append(g[i])                              # fim da introdução sem batida
    while True:
        factor = {0: 1.25, 1: 1.0, 2: 0.75}[_level_at(secs, cuts[-1])]
        j = i + choose_k(beat, target * factor)
        if j >= len(g) or g[j] >= dur - MIN_SCENE:
            break
        if g[j] - cuts[-1] >= MIN_SCENE - 0.01:
            cuts.append(g[j])
        i = j
    cuts.append(round(dur, 3))
    if len(cuts) > 2 and cuts[-1] - cuts[-2] < MIN_SCENE:
        cuts.pop(-2)
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        mid = (a + b) / 2
        out.append({"start": float(round(a, 3)), "end": float(round(b, 3)), "duration": float(round(b - a, 3)), "nivel": int(_level_at(secs, mid))})
    return out


def plan_motion(scenes: list[dict], modo: str) -> list[str]:
    n = len(scenes)
    if modo == "camera":
        return ["ken_burns"] * n
    if modo == "destaques":
        return ["ltx" if (s["nivel"] == 2 or i == 0) else "ken_burns" for i, s in enumerate(scenes)]
    motion = ["ltx"] * n
    heroes = [0] + [i for i in range(1, n) if scenes[i]["nivel"] == 2 and scenes[i - 1]["nivel"] != 2]
    for i in heroes[: max(1, min(6, n // 8))]:         # as cenas de maior destaque usam o Wan (mais bonito e bem mais lento)
        motion[i] = "wan"
    return motion


# --------------------------------------------------------------------------- letra
def lyric_lines(text: str) -> list[str]:
    """Linhas cantadas da letra, sem marcações como [Refrão] ou (x2)."""
    out = []
    for ln in (text or "").replace("\r\n", "\n").split("\n"):
        ln = ln.strip()
        if not ln or re.fullmatch(r"[\[(].*[\])]", ln):
            continue
        out.append(re.sub(r"\s+", " ", ln))
    return out


def line_times_proportional(n: int, an: dict) -> list[float]:
    """Sem tempos reais: espalha as linhas pela parte cantada (do fim da introdução calma até o começo do final calmo)."""
    dur, secs = an["duration"], an["sections"]
    first_active = next((s["start"] for s in secs if s["nivel"] >= 1), 0.0)
    start = first_active if first_active < 0.25 * dur else 0.08 * dur
    end = dur
    if secs and secs[-1]["nivel"] == 0 and (secs[-1]["end"] - secs[-1]["start"]) < 0.15 * dur:
        end = secs[-1]["start"]
    if n == 0:
        return []
    step = (end - start) / n
    return [round(start + k * step, 3) for k in range(n)]


def line_times_from_words(lines: list[str], aligned: list[list], dur: float) -> list[float] | None:
    """Tempo de cada linha pela primeira palavra alinhada; None se o alinhamento não parece confiável."""
    words = [w for ln in lines for w in ln.split()]
    if not aligned or len(aligned) != len(words):
        return None
    starts, i = [], 0
    for ln in lines:
        starts.append(float(aligned[i][1]))
        i += len(ln.split())
    if any(b < a for a, b in zip(starts, starts[1:])) or starts[-1] > dur or (starts[-1] - starts[0]) < 0.35 * dur:
        return None
    return [round(s, 3) for s in starts]


def words_for_lines(lines: list[str], times: list[float], dur: float) -> list[list]:
    """[[palavra, início, fim], ...] em tempo da música, repartindo cada linha pelo seu intervalo (por número de letras)."""
    out = []
    for k, ln in enumerate(lines):
        t0 = times[k]
        nxt = times[k + 1] if k + 1 < len(times) else dur
        span = max(0.8, min(nxt - t0 - 0.1, max(1.5, 0.11 * len(ln))))
        ws = ln.split()
        total = sum(len(w) for w in ws) or 1
        t = t0
        for w in ws:
            d = span * len(w) / total
            out.append([w, round(t, 3), round(t + d, 3)])
            t += d
    return out


def attach_lyrics(scenes: list[dict], lines: list[str], times: list[float], words: list[list]) -> None:
    """Põe em cada cena as linhas e as palavras (com tempo relativo ao início da cena) que começam dentro dela."""
    starts = [s["start"] for s in scenes]
    for s in scenes:
        s["lines"], s["words"] = [], []
    for ln, t in zip(lines, times):
        scenes[max(0, bisect.bisect_right(starts, t) - 1)]["lines"].append(ln)
    for w, a, b in words:
        s = scenes[max(0, bisect.bisect_right(starts, a) - 1)]
        s["words"].append([w, round(max(0.0, a - s["start"]), 3), round(min(s["duration"], max(a + 0.05, b) - s["start"]), 3)])


def caption_lines(scenes: list[dict], lyrics: list[str] | None = None) -> list[list[list]]:
    """Palavras da letra com tempo absoluto, agrupadas por verso. A legenda segue o verso inteiro, mesmo quando ele atravessa várias cenas de 3 s
    (montar por cena cortava o verso em pedaços e juntava versos diferentes na mesma legenda)."""
    flat = [[w[0], round(s["start"] + w[1], 3), round(s["start"] + max(w[1], w[2]), 3)] for s in scenes for w in (s.get("words") or [])]
    lines = lyrics or [ln for s in scenes for ln in (s.get("lines") or [])]      # a letra do projeto manda; as linhas guardadas nas cenas são o plano B
    if lines and sum(len(ln.split()) for ln in lines) == len(flat):          # contagem bate: cada verso recebe as suas palavras
        out, i = [], 0
        for ln in lines:
            n = len(ln.split())
            if n:
                out.append(flat[i:i + n])
            i += n
        return out
    out, cur = [], []                                                         # letra editada depois de planejar: separa os versos pelas pausas
    for w in flat:
        if cur and w[1] - cur[-1][2] > 0.35:
            out.append(cur)
            cur = []
        cur.append(w)
    return out + ([cur] if cur else [])


# --------------------------------------------------------------------------- história (LLM)
CLIP_SECONDS = 3.0   # clipes animados mais curtos: a deformação cresce com o tempo, e 3 s bastam para uma cena de 3 a 4 s (o resto é zoom suave)
ENV_HINTS = [
    (("water", "lake", "sea", "ocean", "river", "rain", "wave", "shore", "beach", "harbor"), "gentle ripples and small waves moving on the water"),
    (("mist", "fog", "smoke", "haze"), "mist drifting slowly"),
    (("leaves", "grass", "tree", "forest", "flower", "field", "wind", "meadow"), "leaves, grass and flowers swaying softly in a light breeze"),
    (("sky", "cloud", "sun", "sunset", "sunrise", "moon", "star"), "clouds drifting slowly across the sky"),
    (("light", "lamp", "candle", "lantern", "lighthouse", "window", "street", "city"), "lights glowing and flickering softly"),
]
CAMERAS = ["a slow gentle push-in", "a slow gentle pan to the right", "a slow gentle pan to the left", "a slow gentle pull-back"]


def motion_prompt(visual_prompt: str, n: int) -> str:
    """Prompt para o modelo de animação. NÃO repete a ação da cena (correr, rasgar, dançar...): é isso que deforma rosto e corpo.
    Pede câmera lenta, movimento só do ambiente e pessoas quase paradas."""
    low = visual_prompt.lower()
    hints = [h for keys, h in ENV_HINTS if any(k in low for k in keys)][:2] or ["soft light shimmering in the air"]
    return (f"Very gentle cinematic motion: {CAMERAS[n % len(CAMERAS)]} with soft parallax. {' and '.join(hints)}. "
            "The people stay almost still, calm and relaxed, and their faces and bodies keep exactly the same shape; only hair and clothing sway very slightly. "
            "Smooth, stable, peaceful and dreamy.")


SYSTEM_STORY = (
    "Você é diretor de videoclipes. O clipe NUNCA mostra o cantor cantando, microfone, palco ou show: ele conta a história que a letra "
    "conta, como um filme curto. "
    "O tom é poético, humano e acolhedor (saudade, esperança, beleza), NUNCA terror: nada de coisas inquietantes, assustadoras, corpos ou rostos "
    "deformados, sósias, espelhos que mostram outra pessoa, sangue ou escuridão opressiva. Prefira cenas amplas e luz bonita. "
    "Com base na LETRA e no CONCEITO do autor, responda SOMENTE com JSON com estas chaves: "
    '"resumo": a história do clipe em até 3 frases em português; '
    '"protagonista": descrição visual CONCRETA em inglês, em uma frase, de quem vive a história: idade aproximada, cabelo, roupa, cores e um acessório marcante, SEM descrever o rosto '
    "(nada de sorriso, olhos, barba ou pele), porque as cenas mostram a pessoa de costas ou de longe; ela será repetida em todas as cenas; "
    '"cenario": o mundo da história em inglês, em uma frase; '
    '"paleta": cores e luz dominantes em inglês, em poucas palavras; '
    '"arco": lista de 6 a 10 momentos em ordem, cada um com "momento" (português, curto) e "visual" (uma imagem concreta em inglês, '
    "de até 25 palavras, que mostra aquele momento da história sem texto e sem cantor)."
)
SYSTEM_SCENE = (
    "You write image prompts for a text-to-image model for ONE scene of an animated music video that tells a story. When the protagonist is "
    "in the scene, write exactly [P] once where the person goes (the system replaces [P] with the character description, so NEVER describe the "
    "protagonist's looks, clothes or face yourself). Use SETTING and PALETTE as given. The scene shows the story, never a singer performing, "
    "no microphone, no stage, no band. Reply with ONE concrete visual description in English (max 40 words besides [P]): who or what is "
    "calmly present, setting, camera framing and light. SAFE COMPOSITION (the image will be animated by a video model that distorts faces and "
    "bodies): use a wide or medium-wide shot; show people from behind, in silhouette or from a distance, calm and still (standing, sitting, "
    "slowly walking away); NEVER a close-up of a face or hands, never running, fighting, dancing, crowds, mirrors or reflections showing another "
    "person; put the life of the scene in the environment (water, wind, clouds, mist, light). Warm, beautiful and peaceful, never scary or "
    "unsettling. No text or letters, no quotes, no labels. Reply with the description only."
)


def fill_protagonist(prompt: str, bible: dict) -> str:
    """Troca [P] pela descrição fixa do personagem (a mesma em todas as cenas) e tira rótulos que o LLM às vezes copia do pedido."""
    out = re.sub(r"^\s*(?:PROTAGONIST|SETTING|PALETTE|STORY MOMENT|LYRIC|MUSIC ENERGY)\s*:\s*", "", prompt.strip(), flags=re.I)
    desc = str(bible.get("protagonista") or "").strip().rstrip(".")
    out = re.sub(r"\[P\]", desc, out, count=1) if desc else out
    out = out.replace("[P]", "the person")
    return " ".join(out.split())


def story_defaults(title: str, concept: str) -> dict:
    base = concept.strip() or title
    return {"resumo": base[:300], "protagonista": "a lone young person with long hair in a light coat, seen from behind",
            "cenario": "a vast moody landscape that changes with the story", "paleta": "deep blue shadows with warm amber light",
            "arco": [{"momento": f"Parte {i + 1}", "visual": f"cinematic scene {i + 1} of the story, {base[:80]}"} for i in range(6)]}


def build_story(title: str, lyrics: str, concept: str, backend) -> dict:
    default = story_defaults(title, concept)
    user = f"TÍTULO: {title}\n\nCONCEITO DO AUTOR: {concept or '(sem conceito; deduza da letra)'}\n\nLETRA:\n{lyrics[:9000]}"
    try:
        data = backend.llm_json(SYSTEM_STORY, user)
    except Exception:
        return default
    arc = []
    for a in data.get("arco") or []:
        if isinstance(a, dict) and str(a.get("visual") or "").strip():
            arc.append({"momento": " ".join(str(a.get("momento") or "").split())[:80], "visual": " ".join(str(a["visual"]).split())[:240]})
    out = dict(default)
    for k in ("resumo", "protagonista", "cenario", "paleta"):
        v = " ".join(str(data.get(k) or "").split())
        if v:
            out[k] = v[:400]
    if len(arc) >= 3:
        out["arco"] = arc[:10]
    return out


def arc_index(frac: float, n: int) -> int:
    return min(n - 1, int(frac * n))


def scene_context(bible: dict, arc: dict, lines: list[str], nivel: int) -> str:
    lyric = " / ".join(lines) if lines else "(instrumental passage)"
    return (f"The protagonist is a person: write [P] for them.\nSETTING: {bible['cenario']}\nPALETTE: {bible['paleta']}\n"
            f"STORY MOMENT: {arc['visual']}\nLYRIC (Portuguese): {lyric}\nMUSIC ENERGY: {NIVEL[nivel]}")
