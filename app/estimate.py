"""Estimativa de tempo por etapa, calibrada com as medições reais da andes (RTX 5060 Ti, 2026-11-21)."""
from . import config

# segundos medidos: LLM 5 s/cena; FLUX 12-15 s/imagem (com o ComfyUI mantendo o modelo em cache);
# Wan 237 s/clipe; LTX ~40-55 s/clipe; montagem 1080p ~0,65 s por segundo de vídeo.
REAL = {"plan_scene": 5.0, "prepare_fixed": 30.0, "tts_align_scene": 3.0, "image": 14.0,
        "clip_wan": 240.0, "clip_ltx": 60.0, "metadata": 60.0, "thumb_fixed": 35.0, "assemble_scene": 1.5, "final_per_video_second": 0.65, "render_fixed": 20.0}
FAKE_SCALE = 0.01  # no modo de teste tudo é quase instantâneo


def _k() -> float:
    return FAKE_SCALE if config.MODE == "fake" else 1.0


def human(seconds: float) -> str:
    s = int(round(seconds))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"~{round(s / 60)} min"
    h, m = divmod(round(s / 60), 60)
    return f"~{h} h {m:02d} min"


def for_project(project: dict) -> dict:
    items = project["scenes"]
    n = len(items)
    video_seconds = sum((s["duration"] or s["est_seconds"] or 0) for s in items)
    todo_audio = sum(1 for s in items if s["dirty_audio"] or not s["audio"])
    todo_image = sum(1 for s in items if s["dirty_image"] or not s["image"])
    clips_wan = sum(1 for s in items if s["motion"] == "wan" and not s["clip"] or (s["motion"] == "wan" and s["dirty_image"]))
    clips_ltx = sum(1 for s in items if s["motion"] == "ltx" and not s["clip"] or (s["motion"] == "ltx" and s["dirty_image"]))
    k = _k()
    plan = n * REAL["plan_scene"] * k if n else (project["text"].count(".") * 1.2 * REAL["plan_scene"] * k)
    prepare = (REAL["prepare_fixed"] + todo_audio * REAL["tts_align_scene"] + todo_image * REAL["image"]) * k if (todo_audio or todo_image) else 0
    clips = (clips_wan * REAL["clip_wan"] + clips_ltx * REAL["clip_ltx"]) * k
    assemble = (REAL["render_fixed"] + n * REAL["assemble_scene"] + video_seconds * REAL["final_per_video_second"]) * k
    render = clips + assemble
    return {
        "scenes": n, "video_seconds": round(video_seconds), "clips": {"wan": clips_wan, "ltx": clips_ltx},
        "seconds": {"plan": round(plan), "prepare": round(prepare), "render": round(render), "render_clips": round(clips),
                    "metadata": round(REAL["metadata"] * k), "thumbnail": round((REAL["thumb_fixed"] + 3 * REAL["image"]) * k)},
        "human": {"plan": human(plan), "prepare": human(prepare), "render": human(render), "total": human(plan + prepare + render),
                  "metadata": human(REAL["metadata"] * k), "thumbnail": human((REAL["thumb_fixed"] + 3 * REAL["image"]) * k)},
        "mode": config.MODE,
    }
