"""Etapas do clipe musical: planejar (ouvir a música, criar a história, marcar a letra, descrever cada cena) e preparar (imagens).

A montagem final é a mesma dos vídeos narrados (`engine.render`), com a música inteira como áudio.
"""
import pathlib

from .. import channel_rules, config, db, musicclip as mc, profiles, scenes as scn
from .backends import get_backend

SONG_PAUSE = 0.0


def song_file(project: dict, d: pathlib.Path) -> pathlib.Path:
    return d / project["meta"]["clip"]["audio"]


def plan_clip(pid: str, progress) -> dict:
    from . import engine
    project = db.project_get(pid)
    cfg = project["meta"]["clip"]
    d, backend = engine.project_dir(pid), get_backend()
    scene_system = (mc.SYSTEM_SCENE + " " + channel_rules.visual_extra(db.channel_get(project.get("channel_id") or ""))).strip()   # estética e proibições do canal
    song = song_file(project, d)
    if not song.is_file():
        raise ValueError("o arquivo da música não está mais no projeto")

    engine._stages(progress, [("analyze", "Ouvir a música (andamento, batidas e partes)", 1), ("story", "Criar a história do clipe a partir da letra", 1),
                              ("lyrics", "Marcar a letra no tempo", 1), ("plan", "Descrever a imagem de cada cena", 1)])
    engine._stage(progress, "analyze", 0)
    progress(0.03, "ouvindo a música")
    an = mc.analyze(song)
    engine._stage(progress, "analyze", 1)

    engine._stage(progress, "story", 0)
    progress(0.10, "criando a história do clipe a partir da letra")
    bible = mc.build_story(project["title"], project["text"], cfg.get("conceito", ""), backend)
    engine._stage(progress, "story", 1)

    engine._stage(progress, "lyrics", 0)
    progress(0.22, "marcando a letra no tempo da música")
    lines = mc.lyric_lines(project["text"]) if cfg.get("tem_letra", True) else []
    times = None
    if lines:
        try:
            aligned = backend.align(str(song), [w for ln in lines for w in ln.split()], an["duration"])
            times = mc.line_times_from_words(lines, aligned, an["duration"])
        except Exception:
            times = None  # o alinhamento por voz cantada falha com frequência: a letra é então espalhada pela parte cantada
        backend.unload("align")
    cuts = mc.plan_cuts(an, cfg.get("ritmo", "normal"))
    words = []
    if lines:
        times = times or mc.line_times_proportional(len(lines), an)
        words = mc.words_for_lines(lines, times, an["duration"])
        mc.attach_lyrics(cuts, lines, times, words)
    else:
        for c in cuts:
            c["lines"], c["words"] = [], []
    motion = mc.plan_motion(cuts, cfg.get("animacao", "total"))
    engine._stage(progress, "lyrics", 1)

    n = len(cuts)
    engine._stages(progress, [("analyze", "Ouvir a música (andamento, batidas e partes)", 1), ("story", "Criar a história do clipe a partir da letra", 1),
                              ("lyrics", "Marcar a letra no tempo", 1), ("plan", "Descrever a imagem de cada cena", n)])
    for k in ("analyze", "story", "lyrics"):
        engine._stage(progress, k, 1)
    items = []
    for i, c in enumerate(cuts):
        engine._stage(progress, "plan", i, i + 1)
        progress(0.3 + 0.68 * i / n, f"descrevendo a imagem da cena {i + 1} de {n}")
        s = scn.new_scene(i + 1, " / ".join(c["lines"]) if c["lines"] else "(trecho instrumental)")
        arc = bible["arco"][mc.arc_index(((c["start"] + c["end"]) / 2) / an["duration"], len(bible["arco"]))]
        s["visual_prompt"] = mc.fill_protagonist(backend.visual_prompt(mc.scene_context(bible, arc, c["lines"], c["nivel"]), system=scene_system), bible)
        s.update(duration=c["duration"], est_seconds=c["duration"], audio="song", audio_seconds=c["duration"], dirty_audio=False,
                 words=c["words"], motion=motion[i], nivel=c["nivel"], momento=arc.get("momento", ""))
        items.append(s)
        engine._stage(progress, "plan", i + 1, i + 1)
    backend.unload("llm")
    engine._timeline(items)
    cfg = {**cfg, "analise": {"duration": an["duration"], "bpm": an["bpm"], "confidence": an["confidence"], "beats": len(an["beats"]),
                              "sections": an["sections"]}, "historia": bible, "tem_letra": bool(lines)}
    progress(1.0, f"{n} cenas planejadas no ritmo da música")
    return engine._save(pid, items, status="planned", meta={**project["meta"], "clip": cfg, "total_est_seconds": an["duration"]})


def prepare_clip(pid: str, progress) -> dict:
    """Só as imagens: a música já é o áudio do clipe."""
    from . import engine
    project = db.project_get(pid)
    items, backend, d = project["scenes"], get_backend(), engine.project_dir(pid)
    if not items:
        raise ValueError("planeje as cenas antes de preparar")
    todo = [s for s in items if s["dirty_image"] or not s["image"]]
    engine._stages(progress, [("image", "Imagens das cenas", len(todo))])
    try:
        for k, s in enumerate(todo):
            engine._stage(progress, "image", k, s["n"])
            progress(k / max(1, len(todo)), f"imagem da cena {s['n']} de {len(items)}")
            engine._make_image(project, s, backend, d)
            engine._save(pid, items)
            engine._stage(progress, "image", k + 1, s["n"])
        backend.unload("image")
    finally:
        engine._save(pid, items)
        backend.unload("image")
    engine._timeline(items)
    progress(1.0, "storyboard pronto para aprovação")
    return engine._save(pid, items, status="storyboard")


def lyrics_from_segments(segs: list[dict]) -> dict:
    """Texto da letra, uma frase por linha; uma pausa longa entre frases vira linha em branco (separa as estrofes)."""
    lines, prev_end = [], None
    for sg in segs:
        txt = " ".join(str(sg.get("text", "")).split())
        if not txt:
            continue
        if prev_end is not None and float(sg["start"]) - prev_end > 4.0 and lines:
            lines.append("")
        lines.append(txt)
        prev_end = float(sg["end"])
    text = "\n".join(lines).strip()
    return {"lyrics": text, "linhas": sum(1 for x in lines if x), "instrumental": not text}
