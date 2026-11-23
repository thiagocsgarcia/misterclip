"""Etapas do pipeline. Cada etapa é idempotente: só refaz o que está faltando ou foi marcado como sujo."""
import pathlib
import time
from typing import Callable

from PIL import Image

from .. import cancel, idea_scripts, captions, channel_rules, config, db, imagecheck, metadata, musicclip as mc, profiles, ptnum, scenes as scn, script_draft, shorts, shorts_plan, thumbnail
from . import assemble
from .backends import get_backend

Progress = Callable[[float, str], None]
SUBDIRS = ("audio", "images", "thumbs", "clips", "segments", "thumbs_yt")
IMAGE_TRIES = 3
MOTION_PROMPT = "slow cinematic camera movement, subtle atmospheric motion, gentle drifting light"


def _stages(progress, spec: list[tuple[str, str, int]]) -> None:
    """Declara as etapas do job (chave, rótulo, total) para a tela mostrar uma barra por etapa."""
    f = getattr(progress, "init_stages", None)
    if f:
        f(spec)


def _stage(progress, key: str, done: int, current: int | None = None) -> None:
    f = getattr(progress, "set_stage", None)
    if f:
        f(key, done, current)


def scene_key(s: dict) -> str:
    """Nome-base dos arquivos da cena. Projetos antigos (sem id) continuam usando o número com 3 dígitos."""
    return s.get("id") or f"{s['n']:03d}"


def project_dir(pid: str) -> pathlib.Path:
    d = config.DATA / "projects" / pid
    for s in SUBDIRS:
        (d / s).mkdir(parents=True, exist_ok=True)
    return d


def _profile_for(project: dict, scene: dict) -> dict:
    return profiles.require(scene.get("profile_id") or project["profile_id"])


def _full_prompt(scene: dict, profile: dict) -> str:
    base = scene["visual_prompt"] or scene["text"][:200]
    return f"{base}. {profile['style_prompt']}"


def _image_size(profile: dict) -> tuple[int, int]:
    if config.MODE == "fake":
        return config.VIDEO_W, config.VIDEO_H
    p = profile["params"]
    return p["width"], p["height"]


def _save(pid: str, scenes: list[dict], **extra) -> dict:
    return db.project_update(pid, scenes=scenes, **extra)


# --------------------------------------------------- estado coerente após parada
def settle_status(project: dict) -> str:
    """Status correto de um projeto parado (erro, cancelamento ou reinício), calculado pelo que existe de fato."""
    items = project["scenes"]
    if not items:
        return "draft"
    if is_clip(project):  # clipe musical: a "voz" é a própria música, só as imagens podem faltar
        ready = all(s["image"] and not s["dirty_image"] for s in items)
    else:
        ready = all(s["image"] and s["audio"] and s["words"] and not s["dirty_audio"] and not s["dirty_image"] for s in items)
    return "storyboard" if ready else "planned"


def recover_stuck() -> list[str]:
    """No startup: projetos presos em 'rendering' sem job ativo voltam a um estado em que dá para continuar."""
    fixed = []
    for row in db.project_list():
        if row["status"] == "rendering" and not db.project_busy(row["id"]):
            p = db.project_get(row["id"])
            db.project_update(p["id"], status=settle_status(p), meta={**p["meta"], "last_error": "interrompido por reinício do serviço"})
            fixed.append(p["id"])
    return fixed


# ------------------------------------------------------------------ planejar
def is_clip(project: dict) -> bool:
    return (project.get("meta") or {}).get("kind") == "clip"


def plan(pid: str, progress: Progress) -> dict:
    project = db.project_get(pid)
    if is_clip(project):
        from . import clipengine
        return clipengine.plan_clip(pid, progress)
    profile = profiles.require(project["profile_id"])
    backend = get_backend()
    ch = db.channel_get(project.get("channel_id") or "")
    vrules = channel_rules.effective(ch)["video"]                                               # premissas de vídeo do canal
    texts = scn.split_text(project["text"], float(vrules["segundos_por_cena"] or 0) or None)
    if not texts:
        raise ValueError("o roteiro está vazio")
    visual_extra = channel_rules.visual_extra(ch)   # estética e proibições do canal
    items = [scn.new_scene(i + 1, t) for i, t in enumerate(texts)]
    _stages(progress, [("plan", "Descrever a imagem de cada cena", len(items))])
    for i, s in enumerate(items):
        _stage(progress, "plan", i, s["n"])
        progress(i / len(items), f"descrevendo a imagem da cena {s['n']} de {len(items)}")
        s["visual_prompt"] = backend.visual_prompt(s["text"], extra=visual_extra)
        _stage(progress, "plan", i + 1, s["n"])
    backend.unload("llm")
    engine = vrules["motor_de_animacao"] if vrules["motor_de_animacao"] in ("ltx", "wan") else profile["motion"]["clip_engine"]
    ratio = vrules["proporcao_animada"] if vrules["proporcao_animada"] is not None else profile["motion"]["animated_ratio"]
    for i in scn.pick_animated(len(items), float(ratio)):
        items[i]["motion"] = engine
    progress(1.0, f"{len(items)} cenas planejadas")
    return _save(pid, items, status="planned", meta={**project["meta"], "total_est_seconds": round(sum(s["est_seconds"] for s in items), 1)})  # preserva opções salvas


# ------------------------------------------------------------ preparar (voz + legendas + imagens)
def prepare(pid: str, progress: Progress) -> dict:
    project = db.project_get(pid)
    if is_clip(project):
        from . import clipengine
        return clipengine.prepare_clip(pid, progress)
    items, backend, d = project["scenes"], get_backend(), project_dir(pid)
    if not items:
        raise ValueError("planeje as cenas antes de preparar")
    pron = channel_rules.effective(db.channel_get(project.get("channel_id") or ""))["narracao"].get("pronuncias") or {}
    todo_audio = [s for s in items if s["dirty_audio"] or not s["audio"]]
    todo_align = [s for s in items if s["dirty_audio"] or not s["audio"] or not s["words"]]  # retoma o que um cancelamento deixou
    todo_image = [s for s in items if s["dirty_image"] or not s["image"]]
    total = max(1, len(todo_audio) + len(todo_align) + len(todo_image))
    done = 0
    _stages(progress, [("tts", "Narração das cenas", len(todo_audio)), ("align", "Tempos das palavras (legendas)", len(todo_align)),
                       ("image", "Imagens das cenas", len(todo_image))])

    try:
        for k, s in enumerate(todo_audio):  # 1) narração
            _stage(progress, "tts", k, s["n"])
            progress(done / total, f"narração da cena {s['n']}")
            wav = d / "audio" / f"scene_{scene_key(s)}.wav"
            s["audio_seconds"] = backend.tts(ptnum.for_tts(s["text"], pron), project["voice"], project["speed"], str(wav))
            s["audio"] = f"audio/{wav.name}"
            s["duration"] = round(s["audio_seconds"] + pause_of(s), 3)
            s["dirty_audio"], s["words"] = False, None
            s["ver"] = s.get("ver", 0) + 1
            done += 1
            _save(pid, items)
            _stage(progress, "tts", k + 1, s["n"])
        backend.unload("tts")

        for k, s in enumerate(todo_align):  # 2) tempos por palavra (Whisper) alinhados ao texto original
            _stage(progress, "align", k, s["n"])
            progress(done / total, f"tempos das palavras da cena {s['n']}")
            s["words"] = backend.align(str(d / s["audio"]), s["text"].split(), s["audio_seconds"])
            done += 1
            _save(pid, items)
            _stage(progress, "align", k + 1, s["n"])
        backend.unload("align")

        for k, s in enumerate(todo_image):  # 3) imagens do storyboard
            _stage(progress, "image", k, s["n"])
            progress(done / total, f"imagem da cena {s['n']}")
            _make_image(project, s, backend, d)
            done += 1
            _save(pid, items)
            _stage(progress, "image", k + 1, s["n"])
        backend.unload("image")
    finally:  # cancelamento ou erro: o que já foi feito fica salvo e os modelos saem da GPU
        _save(pid, items)
        for stage in ("tts", "align", "image"):
            backend.unload(stage)

    _timeline(items)
    progress(1.0, "storyboard pronto para aprovação")
    return _save(pid, items, status="storyboard")


def _make_image(project: dict, scene: dict, backend, d: pathlib.Path) -> None:
    profile = _profile_for(project, scene)
    out = d / "images" / f"scene_{scene_key(scene)}.png"
    tries, why = 0, None
    for tries in range(1, IMAGE_TRIES + 1):   # o gerador às vezes devolve um quadro preto, branco ou liso: tenta de novo com outra semente
        backend.image(_full_prompt(scene, profile), profile, scene["seed"], str(out), _image_size(profile))
        why = imagecheck.problem(str(out))
        if not why:
            break
        if tries < IMAGE_TRIES:
            scene["seed"] = (scene["seed"] * 7919 + 13) % 2_147_483_647
    scene["image_warning"] = f"{why} (mesmo depois de {tries} tentativas)" if why else None
    thumb = d / "thumbs" / f"scene_{scene_key(scene)}.jpg"
    with Image.open(out) as im:
        im.convert("RGB").resize((480, round(480 * im.height / im.width))).save(thumb, quality=85)
    for old_path in (scene.get("image"), scene.get("thumb"), scene.get("clip")):  # arquivos de uma geração anterior (outro nome)
        if old_path and old_path not in (f"images/{out.name}", f"thumbs/{thumb.name}"):
            (d / old_path).unlink(missing_ok=True)
    scene.update(image=f"images/{out.name}", thumb=f"thumbs/{thumb.name}", dirty_image=False, clip=None, ver=scene.get("ver", 0) + 1,
                 image_profile=profile.get("id"))


def _make_clip(project: dict, s: dict, backend, d: pathlib.Path) -> None:
    """Anima a imagem de uma cena. Se falhar, a cena fica sem clipe (usa zoom suave) e o erro é guardado, sem derrubar o vídeo."""
    out = d / "clips" / f"scene_{scene_key(s)}.mp4"
    try:
        if is_clip(project):  # clipe musical: só o cenário se move; pessoas quase paradas (corrida e gestos deformavam rosto e corpo)
            prompt, seconds = mc.motion_prompt(s["visual_prompt"], s["n"]), mc.CLIP_SECONDS
        else:
            prompt, seconds = f"{MOTION_PROMPT}. {s['visual_prompt']}", 4.0
        ok = backend.clip(s["motion"], str(d / s["image"]), prompt, str(out), seconds, int(s.get("clip_seed") or s["seed"] + 13))
        s["clip"] = f"clips/{out.name}" if ok else None
        s["ver"] = s.get("ver", 0) + 1
        s.pop("clip_error", None)
    except Exception as e:  # cai para Ken Burns em vez de derrubar o vídeo inteiro
        s["clip"], s["clip_error"] = None, str(e)[:300]


def scene_clip(pid: str, n: int, progress: Progress) -> dict:
    """Gera só a animação de uma cena (por exemplo depois de trocar a imagem), sem refazer o vídeo todo."""
    project = db.project_get(pid)
    items = project["scenes"]
    scene = next(s for s in items if s["n"] == n)
    if not scene.get("image") or scene.get("dirty_image"):
        raise ValueError("gere a imagem desta cena antes de animar")
    if scene["motion"] not in ("ltx", "wan"):
        raise ValueError("esta cena usa zoom suave; escolha uma animação no efeito da imagem")
    _stages(progress, [("clips", "Animação da cena", 1)])
    _stage(progress, "clips", 0, n)
    progress(0.1, f"animando a imagem da cena {n}")
    backend = get_backend()
    _make_clip(project, scene, backend, project_dir(pid))
    backend.unload("clip")
    _stage(progress, "clips", 1, n)
    if not scene.get("clip"):
        _save(pid, items)
        raise RuntimeError("a animação não deu certo: " + (scene.get("clip_error") or "motivo desconhecido"))
    progress(1.0, "animação pronta")
    return _save(pid, items)


def pause_of(s: dict) -> float:
    """Silêncio depois da fala da cena: o ajuste do usuário, ou o padrão do sistema."""
    v = s.get("pause")
    return config.SCENE_PAUSE_SECONDS if v is None else max(0.0, min(3.0, float(v)))


def set_pause(s: dict, seconds: float | None) -> None:
    """Muda a pausa da cena e recalcula a duração (a narração e as legendas da cena não mudam: a pausa vem depois da fala)."""
    s["pause"] = None if seconds is None else round(max(0.0, min(3.0, float(seconds))), 2)
    if s.get("audio_seconds") and s.get("audio") and not s.get("dirty_audio"):
        s["duration"] = round(s["audio_seconds"] + pause_of(s), 3)


def _timeline(items: list[dict]) -> None:
    t = 0.0
    for s in items:
        s["start"] = round(t, 3)
        t += s["duration"] or 0


def regen_image(pid: str, n: int, progress: Progress, profile_id: str | None = None, prompt: str | None = None, new_seed: bool = True) -> dict:
    project = db.project_get(pid)
    items = project["scenes"]
    scene = next(s for s in items if s["n"] == n)
    if profile_id is not None:
        scene["profile_id"] = profile_id or None
    if prompt is not None:
        scene["visual_prompt"] = prompt
    if new_seed:
        scene["seed"] = (scene["seed"] * 7919 + 13) % 2_147_483_647
    _stages(progress, [("image", "Nova imagem da cena", 1)])
    _stage(progress, "image", 0, n)
    progress(0.1, f"regerando a imagem da cena {n}")
    backend = get_backend()
    _make_image(project, scene, backend, project_dir(pid))
    _stage(progress, "image", 1, n)
    backend.unload("image")
    progress(1.0, "imagem regerada")
    return _save(pid, items)


def profile_test(profile_id: str, text: str, progress: Progress) -> dict:
    profile = profiles.require(profile_id)
    backend = get_backend()
    out = config.DATA / "profile_tests"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{profile_id}.png"
    progress(0.2, "gerando imagem de teste")
    prompt = backend.visual_prompt(text)
    backend.unload("llm")
    backend.image(f"{prompt}. {profile['style_prompt']}", profile, 42, str(path), _image_size(profile))
    backend.unload("image")
    progress(1.0, "pronto")
    return {"image": f"profile_tests/{path.name}", "prompt": prompt}


def generate_metadata(pid: str, progress: Progress) -> None:
    """Título, descrição, tags e capítulos para o YouTube (LLM da andes)."""
    project = db.project_get(pid)
    ch = db.channel_get(project.get("channel_id") or "")
    rules = channel_rules.effective(ch)
    yt = metadata.generate(project, get_backend(), progress, ctx=channel_rules.context_text(ch))
    yt["ajustes_das_regras"] = channel_rules.enforce_metadata(yt, rules)     # o que o LLM devolveu fora das regras é corrigido ou descartado
    db.project_update(pid, meta={**project["meta"], "youtube": yt})
    progress(1.0, "sugestões prontas")


def generate_thumbnails(pid: str, progress: Progress, count: int = 3) -> None:
    project = db.project_get(pid)
    profile = profiles.require(project["profile_id"])
    state = thumbnail.generate(project, profile, get_backend(), project_dir(pid) / "thumbs_yt", progress, count)
    db.project_update(pid, meta={**project["meta"], "thumbnail": state})
    progress(1.0, "miniaturas prontas")


SAMPLE_TEXT = "Esta é uma amostra da voz escolhida para a narração do seu vídeo."


def voice_sample(voice: str, speed: float, progress: Progress) -> dict:
    """Áudio curto para o usuário ouvir a voz antes de criar o projeto (com cache por voz e velocidade)."""
    out = config.DATA / "voice_samples"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{voice}_{speed:.2f}.wav"
    if not path.is_file():
        progress(0.3, "gerando amostra de voz")
        backend = get_backend()
        try:
            backend.tts(SAMPLE_TEXT, voice, speed, str(path))
        finally:
            backend.unload("tts")
    progress(1.0, "pronto")
    return {"audio": f"voice_samples/{path.name}"}



# ---------------------------------------------------------------- legendas (editáveis) e montagem final
def _captions_on(project: dict) -> bool:
    if is_clip(project):
        return bool(project["meta"]["clip"].get("legendas", True))
    return bool(channel_rules.effective(db.channel_get(project.get("channel_id") or ""))["video"]["legendas"])


def auto_caption_events(project: dict, items: list[dict]) -> list[list]:
    """As linhas de legenda que o sistema monta sozinho a partir dos tempos das palavras."""
    if not _captions_on(project):
        return []
    if is_clip(project):                                    # clipe: a legenda segue o verso, não a cena de 3 s
        words = [(0.0, ln) for ln in mc.caption_lines(items, mc.lyric_lines(project["text"]))]
    else:
        words = [(s["start"], s["words"] or []) for s in items]
    return captions.make_events(words)


def caption_state(project: dict) -> dict:
    """Linhas de legenda do vídeo: as editadas à mão (se ainda valem para a duração atual) ou as automáticas."""
    items = project["scenes"]
    _timeline(items)
    total = round(sum(s["duration"] or 0 for s in items), 2)
    auto = auto_caption_events(project, items)
    edit = (project["meta"].get("captions_edit") or {})
    valid = bool(edit.get("events")) and abs(edit.get("total", -9) - total) < 0.06 and edit.get("n") == len(items)
    return {"events": edit["events"] if valid else auto, "auto": auto, "edited": valid, "stale_edit": bool(edit.get("events")) and not valid, "total": total}


def _burn(project: dict, items: list[dict], d: pathlib.Path, profile: dict, narration: str, total: float) -> dict | None:
    """Escreve as legendas e faz o vídeo final (acabamento, narração, música e legendas) a partir de video_raw.mp4. Só FFmpeg, sem GPU."""
    ev = caption_state({**project, "scenes": items})["events"]
    ass = captions.build_ass([], config.VIDEO_W, config.VIDEO_H, profile.get("captions", {}), events=ev)
    (d / "captions.ass").write_text(ass, encoding="utf-8")
    music = None
    m = (project["meta"].get("options") or {}).get("music") or {}
    if not is_clip(project) and m.get("file") and (config.MUSIC_DIR / m["file"]).is_file():
        music = {"path": str(config.MUSIC_DIR / m["file"]), "volume": m.get("volume", 0.25), "duck": m.get("duck", True)}
    assemble.final_render(str(d), str(d / "video_raw.mp4"), narration, "captions.ass", profile, str(d / "final.mp4"), total, music)
    return music


def recaption(pid: str, progress: Progress) -> dict:
    """Refaz só as legendas do vídeo pronto (texto e tempos editados à mão), sem animar nada e sem mexer na narração. Leva segundos."""
    project = db.project_get(pid)
    d = project_dir(pid)
    narration = d / project["meta"]["clip"]["audio"] if is_clip(project) else d / "narration.wav"
    if project["status"] != "done" or not (d / "video_raw.mp4").is_file() or not narration.is_file():
        raise ValueError("o vídeo precisa estar pronto para trocar as legendas")
    items = project["scenes"]
    _stages(progress, [("final", "Gravar as legendas no vídeo", 1)])
    _stage(progress, "final", 0)
    progress(0.2, "gravando as legendas no vídeo")
    _timeline(items)
    total = sum(s["duration"] or 0 for s in items)
    _burn(project, items, d, profiles.require(project["profile_id"]), str(narration), total)
    _stage(progress, "final", 1)
    progress(1.0, "legendas gravadas")
    return _save(pid, items, meta={**project["meta"], "captions_applied": time.time()})


# ---------------------------------------------------------------- renderizar
def render(pid: str, progress: Progress) -> dict:
    project = db.project_get(pid)
    items, backend, d = project["scenes"], get_backend(), project_dir(pid)
    missing = [s["n"] for s in items if not s["image"] or not s["audio"] or s["dirty_audio"] or s["dirty_image"]]
    if missing:
        raise ValueError(f"cenas incompletas (rode 'preparar'): {missing}")
    _save(pid, items, status="rendering")
    profile = profiles.require(project["profile_id"])

    animated = [s for s in items if s["motion"] in ("ltx", "wan") and not s["clip"]]
    animated.sort(key=lambda s: s["motion"])  # um motor de cada vez: trocar Wan por LTX recarrega o modelo inteiro
    _stages(progress, [("clips", "Animação das imagens", len(animated)), ("segments", "Montagem das cenas", len(items)),
                       ("final", "Vídeo final (transições, narração, música e legendas)", 3)])
    for i, s in enumerate(animated):  # 1) clipes animados
        _stage(progress, "clips", i, s["n"])
        progress(0.05 + 0.55 * i / max(1, len(animated)), f"animando a imagem da cena {s['n']}")
        _make_clip(project, s, backend, d)
        _save(pid, items)
        _stage(progress, "clips", i + 1, s["n"])
    if animated:
        backend.unload("clip")

    opts = project["meta"].get("options", {})
    kind = assemble.transition_kind(opts.get("transition"), profile)
    seconds = float(opts.get("transition_seconds", 0.5)) if kind != "cut" else 0.0
    seconds = min(seconds, 0.45 * min(s["duration"] for s in items))  # cena curta demais não comporta a transição
    tail = round(seconds * assemble.FPS)
    if tail < 2:
        kind, tail = "cut", 0

    progress(0.62, "montando as cenas")  # 2) segmentos (cada cena, menos a última, ganha `tail` quadros de sobreposição)
    _timeline(items)
    segments, bodies, cum = [], [], 0.0
    for i, s in enumerate(items):
        _stage(progress, "segments", i, s["n"])
        start_f, end_f = round(cum * assemble.FPS), round((cum + s["duration"]) * assemble.FPS)
        cum += s["duration"]
        body = end_f - start_f
        frames = body + (tail if i < len(items) - 1 else 0)
        seg = d / "segments" / f"seg_{scene_key(s)}.mp4"
        if s["clip"]:
            assemble.clip_segment(str(d / s["clip"]), frames, str(seg), fade=0)
        else:
            assemble.ken_burns_segment(str(d / s["image"]), 0, str(seg), variant=i, frames=frames, fade=0)
        segments.append(str(seg))
        bodies.append(body)
        progress(0.62 + 0.20 * (i + 1) / len(items), f"cena {s['n']}/{len(items)} montada")
        _stage(progress, "segments", i + 1, s["n"])

    _stage(progress, "final", 0)
    progress(0.83, "unindo as cenas" if kind == "cut" else "unindo as cenas com transição")
    raw = str(d / "video_raw.mp4")
    if kind == "cut":
        assemble.join_cut(segments, raw)
    else:
        assemble.crossfade_join(segments, bodies, tail, assemble.XFADES[kind], raw)
    _stage(progress, "final", 1)

    clip = is_clip(project)
    progress(0.88, "juntando a música e a letra" if clip else "juntando narração, música e legendas")  # 3) áudio, legendas e render final
    if clip:  # o áudio do clipe é a própria música, inteira e sem ducking
        narration = str(d / project["meta"]["clip"]["audio"])
    else:
        assemble.join_narration([str(d / s["audio"]) for s in items], [s["duration"] for s in items], str(d / "narration.wav"))
        narration = str(d / "narration.wav")
    _stage(progress, "final", 2)
    progress(0.9, "criando o vídeo final")
    music = _burn(project, items, d, profile, narration, cum)
    _stage(progress, "final", 3)

    meta = {**project["meta"], "video": "final.mp4", "total_seconds": round(cum, 1), "rendered_with": {"transition": kind, "music": bool(music)}, "render_stale": False}
    progress(1.0, "vídeo pronto")
    return _save(pid, items, status="done", meta=meta)


def generate_shorts(pid: str, progress: Progress, count: int = 3, layout: str = "blur") -> None:
    """Cortes verticais de 30 a 45 s do vídeo pronto (trechos escolhidos pelo LLM; montagem só com FFmpeg, sem GPU)."""
    project = db.project_get(pid)
    items, d = project["scenes"], project_dir(pid)
    raw = d / "video_raw.mp4"
    narration = d / project["meta"]["clip"]["audio"] if is_clip(project) else d / "narration.wav"
    if project["status"] != "done" or not raw.is_file() or not narration.is_file():
        raise ValueError("o vídeo precisa estar pronto para gerar Shorts")
    if sum(s["duration"] for s in items) < shorts.MIN_S:
        raise ValueError("o vídeo é curto demais para Shorts (menos de 30 segundos)")
    count = max(1, min(5, int(count)))
    layout = layout if layout in shorts.LAYOUTS else "blur"
    profile = profiles.require(project["profile_id"])
    yt = project["meta"].get("youtube") or {}
    opts = project["meta"].get("options", {})
    music = None
    m = opts.get("music") or {}
    if m.get("file") and (config.MUSIC_DIR / m["file"]).is_file():
        music = {"path": str(config.MUSIC_DIR / m["file"]), "volume": m.get("volume", 0.25), "duck": m.get("duck", True)}

    _stages(progress, [("pick", "Escolher os melhores trechos", 1), ("short", "Montar os Shorts", count)])
    _stage(progress, "pick", 0)
    progress(0.05, "escolhendo os melhores trechos do roteiro")
    _timeline(items)
    chosen = shorts.choose(items, count, get_backend())
    try:
        get_backend().unload("llm")
    except Exception:
        pass
    _stage(progress, "pick", 1)

    out_dir = d / "shorts"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*"):
        old.unlink()
    rows = []
    for k, c in enumerate(chosen, start=1):
        _stage(progress, "short", k - 1, items[c["i"]]["n"])
        progress(0.1 + 0.85 * (k - 1) / len(chosen), f"montando o Short {k} de {len(chosen)}")
        part = items[c["i"]:c["j"] + 1]
        t0, secs = part[0]["start"], sum(s["duration"] for s in part)
        ass = captions.build_ass([(s["start"] - t0, s["words"]) for s in part], 1080, 1920, profile.get("captions", {}),
                                 max_words=4, max_chars=22, size_div=24, margin_frac=0.27, side_frac=0.09, hook=c["hook"])
        ass_name = f"shorts/short_{k}.ass"
        (d / ass_name).write_text(ass, encoding="utf-8")
        out = d / "shorts" / f"short_{k}.mp4"
        assemble.short_render(str(d), str(raw), str(narration), ass_name, profile, str(out), t0, secs, layout, music)
        assemble.poster_frame(str(out), str(d / "shorts" / f"short_{k}.jpg"), min(1.5, secs / 2))
        rows.append({"i": k, "file": f"shorts/short_{k}.mp4", "poster": f"shorts/short_{k}.jpg", "start": round(t0, 1), "duration": round(secs, 1),
                     "scenes": [part[0]["n"], part[-1]["n"]], "hook": c["hook"], "title": c["title"],
                     "description": shorts.description(c["hook"], yt.get("hashtags"), c["title"])})
        _stage(progress, "short", k, part[-1]["n"])
    prev = project["meta"].get("shorts") or {}
    db.project_update(pid, meta={**project["meta"], "shorts": {"items": rows, "layout": layout, "ver": prev.get("ver", 0) + 1, "generated_at": time.time()}})
    progress(1.0, "Shorts prontos")


def generate_shorts_ideas(cid: str, n: int, progress: Progress) -> dict:
    """Ideias de Short para um vídeo do calendário, escritas pelo LLM a partir do roteiro; se falhar, ficam as ideias-base."""
    ch = db.channel_get(cid)
    v = next((x for x in (ch["plan"].get("videos", []) if ch else []) if x["n"] == n), None)
    if not v:
        raise ValueError("vídeo do calendário não encontrado")
    proj = db.project_get(v["project_id"]) if v.get("project_id") else None
    script = (proj["text"] if proj else "").strip()
    _stages(progress, [("ideas", "Escrever as ideias de Short", 1)])
    _stage(progress, "ideas", 0)
    progress(0.1, "lendo o roteiro" if script else "criando ideias a partir do título")
    excerpt = script if len(script) <= 12000 else script[:7000] + "\n[...]\n" + script[-4000:]
    user = f"Título do vídeo: {v['titulo']}\n\nROTEIRO:\n{excerpt or '(ainda não há roteiro; use só o título e o seu conhecimento do tema)'}"
    data = get_backend().llm_json(shorts_plan.SYSTEM_IDEAS, user)
    try:
        get_backend().unload("llm")
    except Exception:
        pass
    fresh = shorts_plan.from_llm(v, data)
    _stage(progress, "ideas", 1)
    ch = db.channel_get(cid)  # relê: o plano pode ter mudado enquanto o LLM trabalhava
    v = next(x for x in ch["plan"]["videos"] if x["n"] == n)
    if not fresh:
        progress(1.0, "o LLM não trouxe ideias úteis; ficaram as ideias-base")
        return {"ideias": 0}
    v["shorts"] = shorts_plan.merge(v, fresh)
    db.channel_update(cid, plan=ch["plan"])
    progress(1.0, "ideias prontas")
    return {"ideias": len(fresh)}


def transcribe_upload(upload_id: str, progress: Progress) -> dict:
    """Escreve a letra de uma música enviada (Whisper na andes) para o usuário revisar antes de criar o clipe."""
    from . import clipengine
    d = config.CLIP_UPLOADS / upload_id
    song = next((f for f in d.glob("song.*")), None) if d.is_dir() else None
    if song is None:
        raise ValueError("a música enviada não está mais no servidor; envie de novo")
    _stages(progress, [("listen", "Ouvir a música e escrever a letra", 1)])
    _stage(progress, "listen", 0)
    progress(0.05, "ouvindo a música para escrever a letra")
    backend = get_backend()
    segs = backend.transcribe_lyrics(str(song))
    backend.unload("align")
    _stage(progress, "listen", 1)
    progress(1.0, "letra pronta para revisar")
    return clipengine.lyrics_from_segments(segs)


def review_script(pid: str, progress: Progress) -> dict:
    """Revisão do roteiro pelo LLM da andes, contra a identidade e as regras do canal. Fica em meta.review."""
    project = db.project_get(pid)
    text = project["text"]
    if len(text.split()) < 30:
        raise ValueError("o roteiro está curto demais para revisar")
    ch = db.channel_get(project.get("channel_id") or "")
    _stages(progress, [("review", "Revisar o roteiro com as regras do canal", 1)])
    _stage(progress, "review", 0)
    progress(0.1, "lendo o roteiro com as regras do canal")
    excerpt = text if len(text) <= 14000 else text[:9000] + "\n[...]\n" + text[-4000:]
    data = get_backend().llm_json(channel_rules.review_system(ch), f"Título de trabalho: {project['title']}\n\nROTEIRO:\n{excerpt}")
    try:
        get_backend().unload("llm")
    except Exception:
        pass
    review = {"veredito": str(data.get("veredito") or "")[:600], "tese": str(data.get("tese") or "")[:400], "fontes_citadas": [str(x)[:120] for x in (data.get("fontes_citadas") or [])][:12],
              "pontos_fortes": [str(x)[:300] for x in (data.get("pontos_fortes") or [])][:8],
              "riscos": [{"trecho": str(r.get("trecho", ""))[:200], "problema": str(r.get("problema", ""))[:400], "sugestao": str(r.get("sugestao", ""))[:400]} for r in (data.get("riscos") or []) if isinstance(r, dict)][:10],
              "pontos_de_saida": [{"aprox": str(r.get("aprox", ""))[:30], "risco": str(r.get("risco", ""))[:300], "solucao": str(r.get("solucao", ""))[:300]} for r in (data.get("pontos_de_saida") or []) if isinstance(r, dict)][:8],
              "abertura_sugerida": str(data.get("abertura_sugerida") or "")[:400], "originalidade": data.get("originalidade") if isinstance(data.get("originalidade"), dict) else {}, "gerado_em": time.time()}
    db.project_update(pid, meta={**db.project_get(pid)["meta"], "review": review})
    _stage(progress, "review", 1)
    progress(1.0, "revisão pronta")
    return {"ok": True}


def draft_script(cid: str, n: int, progress: Progress, force: bool = False) -> dict:
    """Rascunho de roteiro para um vídeo do calendário, escrito pelo LLM da andes dentro das regras do canal. Fica em plan.roteiros, marcado como rascunho."""
    ch = db.channel_get(cid)
    v = next((x for x in (ch["plan"].get("videos", []) if ch else []) if x["n"] == n), None)
    if not v:
        raise ValueError("vídeo do calendário não encontrado")
    old = next((r for r in ch["plan"].get("roteiros", []) if r.get("video_n") == n), None)
    if old and not old.get("rascunho") and not force:
        raise ValueError("este vídeo já tem um roteiro seu; o rascunho não o substitui")
    backend = get_backend()
    try:
        out = script_draft.write(ch, v, backend, progress, _stages, _stage)
    finally:
        try:
            backend.unload("llm")
        except Exception:
            pass
    ch = db.channel_get(cid)   # relê: o plano pode ter mudado enquanto o LLM trabalhava
    plan = ch["plan"]
    entry = {"video_n": n, "titulo": v["titulo"], "duracao_min": out["minutos"], "quebra_de_padrao_a_cada_s": 60, "marcado": out["texto"], "pontos_de_saida": [],
             "rascunho": {"gerado_em": time.time(), "tese": out["tese"], "fontes": out["fontes"], "incertezas": out["incertezas"], "avisos": out["avisos"]}}
    plan["roteiros"] = [r for r in plan.get("roteiros", []) if r.get("video_n") != n] + [entry]
    plan["roteiros"].sort(key=lambda r: r.get("video_n", 0))
    ed = plan.setdefault("_edited", [])
    if "roteiros" not in ed:
        ed.append("roteiros")
    db.channel_update(cid, plan=plan)
    progress(1.0, "rascunho pronto para revisar")
    return {"palavras": out["palavras"], "minutos": out["minutos"], "avisos": len(out["avisos"])}


def write_idea_scripts(cid: str, ns: list[int], force: bool, progress: Progress) -> dict:
    """Escreve (em fila, uma ideia por vez) o roteiro marcado de cada ideia pedida, com o prompt de roteiro do playbook. Cada roteiro é salvo assim que fica pronto."""
    ch = db.channel_get(cid)
    if not ch:
        raise ValueError("canal não encontrado")
    ideas = {i["n"]: i for i in ch["plan"].get("ideias", [])}
    todo = [n for n in ns if n in ideas and (force or not idea_scripts.load(cid, n))]
    if not todo:
        raise ValueError("nenhuma ideia precisa de roteiro")
    backend = get_backend()
    done, failed = [], []
    _stages(progress, [("ideas", "Roteiros das ideias", len(todo))])
    try:
        for k, n in enumerate(todo):
            idea = ideas[n]
            _stage(progress, "ideas", k, n)
            base, span = k / len(todo), 1 / len(todo)
            sub = lambda f, m, _b=base, _s=span, _n=n: progress(_b + _s * f, f"ideia {_n} ({k + 1} de {len(todo)}): {m}")
            video = {"titulo": idea["titulo"], "pilar": idea.get("categoria"), "formato": "ensaio", "serie": ""}
            try:
                out = script_draft.write(ch, video, backend, sub, lambda *a, **k2: None, lambda *a, **k2: None, marks=True)
            except cancel.Cancelled:
                raise
            except Exception as e:      # uma ideia que falha não derruba as outras
                failed.append({"n": n, "erro": f"{type(e).__name__}: {e}"[:200]})
                continue
            idea_scripts.save(cid, n, {"titulo": idea["titulo"], "marcado": out["texto"], "palavras": out["palavras"], "minutos": out["minutos"], "duracao_min": out["minutos"],
                                       "quebra_de_padrao_a_cada_s": 60, "pontos_de_saida": out["pontos_de_saida"], "editado": False,
                                       "rascunho": {"gerado_em": time.time(), "tese": out["tese"], "fontes": out["fontes"], "incertezas": out["incertezas"], "avisos": out["avisos"]}})
            done.append(n)
            _stage(progress, "ideas", k + 1, n)
    finally:
        try:
            backend.unload("llm")
        except Exception:
            pass
    progress(1.0, f"{len(done)} roteiro(s) pronto(s)" + (f", {len(failed)} com erro" if failed else ""))
    return {"feitos": done, "erros": failed}
