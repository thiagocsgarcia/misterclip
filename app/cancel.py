"""Cancelamento cooperativo: o worker consulta o banco entre os passos (e o ComfyUI a cada segundo)."""
from . import db

current_job: str | None = None


class Cancelled(Exception):
    """O usuário pediu para parar o job em andamento."""


def set_job(job_id: str | None) -> None:
    global current_job
    current_job = job_id


def requested() -> bool:
    jid = current_job
    if not jid:
        return False
    job = db.job_get(jid)
    return bool(job and job["status"] == "cancelling")


def check() -> None:
    if requested():
        raise Cancelled("cancelado pelo usuário")
