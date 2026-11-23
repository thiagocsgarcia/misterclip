"""Aviso opcional de fim de job: POST JSON para a URL em MC_NOTIFY_URL (ex.: um tópico ntfy seu).

Desligado por padrão. Só envia o que o próprio usuário configurou, e só título do projeto, tipo e resultado do job.
"""
import json
import threading
import urllib.request

from . import config


def send(event: str, project_title: str | None, kind: str, message: str, seconds: float | None) -> None:
    url = config.NOTIFY_URL
    if not url:
        return
    body = json.dumps({"event": event, "project": project_title, "job": kind, "message": message,
                       "seconds": round(seconds or 0)}, ensure_ascii=False).encode()

    def _post():
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:  # aviso é "melhor esforço": nunca derruba o job
            pass

    threading.Thread(target=_post, daemon=True).start()
