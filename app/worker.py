"""Fila de jobs: um único worker, para nunca disputar a GPU entre duas etapas."""
import threading
import time
import traceback

from . import cancel, db, notify, youtube_jobs
from .pipeline import engine

_stop = threading.Event()
_thread: threading.Thread | None = None

def _kw(j: dict) -> dict:
    """Parâmetros do job sem a marca do agendamento (que só serve para o agendador acompanhar a cadeia)."""
    return {k: v for k, v in (j.get("payload") or {}).items() if k != "schedule"}


HANDLERS = {
    "plan": lambda j, p: engine.plan(j["project_id"], p),
    "prepare": lambda j, p: engine.prepare(j["project_id"], p),
    "regen_image": lambda j, p: engine.regen_image(j["project_id"], progress=p, **j["payload"]),
    "scene_clip": lambda j, p: engine.scene_clip(j["project_id"], progress=p, **j["payload"]),
    "render": lambda j, p: engine.render(j["project_id"], p),
    "recaption": lambda j, p: engine.recaption(j["project_id"], p),
    "metadata": lambda j, p: engine.generate_metadata(j["project_id"], p),
    "thumbnail": lambda j, p: engine.generate_thumbnails(j["project_id"], p, **_kw(j)),
    "shorts": lambda j, p: engine.generate_shorts(j["project_id"], p, **_kw(j)),
    "script_draft": lambda j, p: engine.draft_script(j["payload"]["channel_id"], j["payload"]["n"], p, bool(j["payload"].get("force"))),
    "idea_scripts": lambda j, p: engine.write_idea_scripts(j["payload"]["channel_id"], j["payload"]["ns"], bool(j["payload"].get("force")), p),
    "shorts_ideas": lambda j, p: engine.generate_shorts_ideas(j["payload"]["channel_id"], j["payload"]["n"], p),
    "transcribe_lyrics": lambda j, p: engine.transcribe_upload(j["payload"]["upload_id"], p),
    "script_review": lambda j, p: engine.review_script(j["project_id"], p),
    "youtube_upload": lambda j, p: youtube_jobs.run_upload(j["project_id"], j["payload"], p),
    "youtube_sync": lambda j, p: youtube_jobs.run_sync(j["payload"]["channel_id"], p),
    "voice_sample": lambda j, p: engine.voice_sample(j["payload"]["voice"], float(j["payload"]["speed"]), p),
    "profile_test": lambda j, p: engine.profile_test(j["payload"]["profile_id"], j["payload"]["text"], p),
}


FLOW = {"plan", "prepare", "render"}  # só estas etapas mudam o status do vídeo; título/miniatura/amostras são "laterais"


def _settle(project_id: str, error: str | None, set_status: bool = True) -> None:
    """Depois de erro/cancelamento o projeto volta ao estado em que dá para continuar."""
    p = db.project_get(project_id)
    if not p:
        return
    meta = {**p["meta"]}
    if error:
        meta["last_error"] = error[:500]
    if set_status:
        db.project_update(project_id, status=engine.settle_status(p), meta=meta)
    else:
        db.project_update(project_id, meta=meta)


class JobProgress:
    """O que o pipeline recebe como `progress`: barra geral (chamando) e uma barra por etapa (init_stages/set_stage)."""

    def __init__(self, jid: str):
        self.jid = jid
        self.items: list[dict] = []
        self.current: int | None = None

    def __call__(self, frac: float, msg: str) -> None:
        cancel.check()  # cada atualização de progresso é um ponto de parada
        db.job_update(self.jid, progress=round(min(1.0, max(0.0, frac)), 3), message=msg)

    def init_stages(self, spec) -> None:
        self.items = [{"key": k, "label": label, "total": int(t), "done": 0, "state": "done" if int(t) == 0 else "pending"} for k, label, t in spec]
        self.current = None
        self._save()

    def set_stage(self, key: str, done: int, current: int | None = None) -> None:
        for it in self.items:
            if it["key"] == key:
                it["done"] = min(int(done), it["total"])
                it["state"] = "done" if it["done"] >= it["total"] else "running"
        if current is not None:
            self.current = current
        self._save()

    def finish(self) -> None:
        for it in self.items:
            it["done"], it["state"] = it["total"], "done"
        self.current = None
        self._save()

    def _save(self) -> None:
        db.job_update(self.jid, stages={"items": self.items, "current": self.current})


def run_job(job: dict) -> None:
    jid, kind = job["id"], job["kind"]
    started = time.time()
    db.job_update(jid, status="running", started=started, message="iniciando", attempts=(job.get("attempts") or 0) + 1)
    cancel.set_job(jid)
    progress = JobProgress(jid)

    status, message, result = "done", "pronto", None
    try:
        out = HANDLERS[kind](job, progress)
        result = out if kind in ("profile_test", "voice_sample", "shorts_ideas", "script_draft", "idea_scripts", "transcribe_lyrics", "youtube_upload", "youtube_sync") else None
        progress.finish()
    except cancel.Cancelled:
        status, message = "cancelled", "cancelado pelo usuário"
    except Exception as e:
        traceback.print_exc()
        status, message = "failed", f"{type(e).__name__}: {e}"[:500]
    finally:
        cancel.set_job(None)

    fields = {"status": status, "finished": time.time(), "message": message}
    if status == "done":
        fields.update(progress=1.0, result=result)
    db.job_update(jid, **fields)

    title = None
    if job["project_id"]:
        p = db.project_get(job["project_id"])
        title = p["title"] if p else None
        if status == "done" and p and "last_error" in p["meta"]:
            meta = {k: v for k, v in p["meta"].items() if k != "last_error"}
            db.project_update(p["id"], meta=meta)
        elif status != "done":
            _settle(job["project_id"], message if status == "failed" else None, kind in FLOW)
    notify.send({"done": "job_done", "failed": "job_failed", "cancelled": "job_cancelled"}[status], title, kind, message, time.time() - started)


def _loop() -> None:
    while not _stop.is_set():
        job = db.job_next_queued()
        if job is None:
            _stop.wait(0.5)
            continue
        run_job(job)


def start() -> None:
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="mc-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
