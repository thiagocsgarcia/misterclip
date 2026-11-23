"""Agendador: dispara "preparar o que faltar + renderizar" de cada vídeo no horário escolhido.

Regras:
- só um agendamento roda por vez e só quando a fila de jobs está vazia (a GPU é uma só); quem chega primeiro, vai primeiro;
- se a andes estava desligada/ocupada na hora, o agendamento ainda roda até GRACE_SECONDS depois; passou disso, vira "perdido";
- um reinício no meio da execução reenvia a etapa uma vez (preparar e renderizar retomam de onde pararam);
- cancelar um agendamento em execução cancela o job em andamento.
"""
import threading
import time
import traceback

from . import db, notify

POLL_SECONDS = 10
GRACE_SECONDS = 12 * 3600
MAX_HORIZON_SECONDS = 366 * 24 * 3600

_stop = threading.Event()
_thread: threading.Thread | None = None
_tick_lock = threading.Lock()  # dois ticks ao mesmo tempo poderiam criar o job seguinte duas vezes


def _finish(s: dict, status: str, message: str) -> None:
    db.schedule_update(s["id"], status=status, message=message, finished=time.time())
    p = db.project_get(s["project_id"])
    notify.send(f"schedule_{status}", p["title"] if p else None, "agendamento", message, time.time() - (s["started"] or time.time()))


def _advance_running() -> None:
    for s in db.schedules_by_status("running"):
        job = db.job_get(s["job_id"]) if s["job_id"] else None
        if job is None:
            _finish(s, "failed", "o job do agendamento sumiu")
            continue
        if job["status"] in ("queued", "running", "cancelling"):
            continue
        if s["cancel"] or job["status"] == "cancelled":
            _finish(s, "cancelled", "cancelado pelo usuário")
        elif job["status"] == "failed":
            if "reinício" in (job["message"] or "") and s["retries"] < 1:  # queda no meio: retoma a mesma etapa uma vez
                again = db.job_create(s["step"], s["project_id"], job["payload"])
                db.schedule_update(s["id"], job_id=again["id"], retries=s["retries"] + 1, message="retomado após reinício")
            elif s["step"] in ("metadata", "thumbnail", "shorts"):         # o vídeo já está pronto: um passo extra que falha não derruba o resto
                _finish(s, "done", f"vídeo pronto; o passo “{_LABEL[s['step']]}” falhou: {job['message'] or 'erro'}")
            else:
                _finish(s, "failed", job["message"] or "o job falhou")
        else:
            p = db.project_get(s["project_id"])
            nxt = _next_step(p, s["step"]) if p else None
            if nxt is None:
                _finish(s, "done", "vídeo pronto" + (" e preparado para publicar" if s["step"] != "render" else ""))
            else:
                kind, payload = nxt
                job2 = db.job_create(kind, s["project_id"], {"schedule": s["id"], **payload})
                db.schedule_update(s["id"], step=kind, job_id=job2["id"], message=_LABEL.get(kind, kind))


_LABEL = {"plan": "dividindo o roteiro em cenas", "prepare": "gerando voz e imagens", "render": "criando o vídeo", "metadata": "escrevendo título, descrição e tags",
          "thumbnail": "criando as miniaturas", "shorts": "cortando os Shorts"}


def _extras(p: dict) -> list[tuple[str, dict]]:
    """O que o canal manda fazer depois de renderizar (título, miniaturas, Shorts), nas regras do canal."""
    from . import channel_rules
    r = channel_rules.effective(db.channel_get(p.get("channel_id") or ""))["video"]
    out = []
    for kind in r["apos_renderizar"]:
        if kind == "metadata":
            out.append(("metadata", {}))
        elif kind == "thumbnail":
            out.append(("thumbnail", {"count": 3}))
        elif kind == "shorts":
            total = sum((sc.get("duration") or sc.get("est_seconds") or 0) for sc in p.get("scenes", []))
            if total < 30:                                                # vídeo curto demais para cortes de 30 a 45 s: o passo é pulado
                continue
            out.append(("shorts", {"count": max(1, min(5, int(r["shorts_por_video"] or 2))), "layout": "blur"}))
    return out


def _next_step(p: dict, step: str):
    order = {"plan": ("prepare", {}), "prepare": ("render", {})}
    if step in order:
        return order[step]
    extras = _extras(p)
    if step == "render":
        return extras[0] if extras else None
    kinds = [k for k, _ in extras]
    return extras[kinds.index(step) + 1] if step in kinds and kinds.index(step) + 1 < len(extras) else None


def _start_due(now: float) -> None:
    for s in sorted(db.schedules_by_status("pending"), key=lambda x: x["run_at"]):
        if s["run_at"] > now:
            break
        if now - s["run_at"] > GRACE_SECONDS:
            _finish(s, "missed", f"perdido: passaram mais de {GRACE_SECONDS // 3600} h do horário e a andes não conseguiu rodar")
            continue
        if db.worker_busy():  # GPU ocupada: espera a vez, sem furar a fila
            return
        p = db.project_get(s["project_id"])
        if not p:
            _finish(s, "failed", "o projeto foi apagado")
        elif not p["scenes"] and not p["text"].strip():
            _finish(s, "failed", "o projeto não tem roteiro")
        else:
            first = "prepare" if p["scenes"] else "plan"                    # sem cenas ainda: começa dividindo o roteiro
            job = db.job_create(first, s["project_id"], {"schedule": s["id"]})
            db.schedule_update(s["id"], status="running", step=first, job_id=job["id"], started=now, message="em execução")
            return  # um de cada vez


def tick(now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _tick_lock:
        _advance_running()
        _start_due(now)
    try:  # piloto automático do YouTube: envia o próximo vídeo pronto e atualiza os números (limitado a 1 vez a cada 5 min)
        from . import youtube_jobs
        youtube_jobs.tick(now)
    except Exception:
        traceback.print_exc()


def cancel(s: dict) -> dict:
    """Pendente: cancela na hora. Em execução: pede para parar o job; o agendador conclui o cancelamento."""
    if s["status"] == "pending":
        db.schedule_update(s["id"], status="cancelled", message="cancelado pelo usuário", finished=time.time())
    elif s["status"] == "running":
        db.schedule_update(s["id"], cancel=1, message="cancelando…")
        if s["job_id"]:
            db.job_cancel(s["job_id"])
    return db.schedule_get(s["id"])


def _loop() -> None:
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            traceback.print_exc()
        _stop.wait(POLL_SECONDS)


def start() -> None:
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="mc-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=5)
