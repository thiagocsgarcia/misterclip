"""Envio do token de acesso por e-mail (esqueci a senha).

O destinatário vem SEMPRE da configuração do servidor (MC_TOKEN_EMAIL), nunca do pedido: quem abre a tela de login não escolhe
para onde o token vai. O limite de envios evita que a tela vire gerador de spam na caixa do dono.
"""
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage

from . import config

_lock = threading.Lock()
_sent: list[float] = []
MIN_GAP = 120.0          # segundos entre dois envios
MAX_PER_HOUR = 5


class MailError(RuntimeError):
    pass


def configured() -> bool:
    return bool(config.TOKEN and config.TOKEN_EMAIL and config.SMTP_HOST and config.SMTP_FROM)


def _allow(now: float) -> bool:
    with _lock:
        _sent[:] = [t for t in _sent if now - t < 3600]
        if len(_sent) >= MAX_PER_HOUR or (_sent and now - _sent[-1] < MIN_GAP):
            return False
        _sent.append(now)
        return True


def send_token(now: float | None = None) -> str:
    """Envia o token ao e-mail configurado. Devolve 'sent', 'limited' ou 'unconfigured'; erros de SMTP viram MailError."""
    if not configured():
        return "unconfigured"
    if not _allow(now if now is not None else time.time()):
        return "limited"
    msg = EmailMessage()
    msg["Subject"] = "MisterClip: seu token de acesso"
    msg["From"] = config.SMTP_FROM
    msg["To"] = config.TOKEN_EMAIL
    msg.set_content("Você pediu o token de acesso do MisterClip na tela de login.\n\nToken: " + config.TOKEN +
                    "\n\nSe não foi você, ignore este e-mail (o token só é enviado para este endereço).\n")
    try:
        ctx = ssl.create_default_context()
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20, context=ctx) as s:
                _login(s)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
                s.starttls(context=ctx)
                _login(s)
                s.send_message(msg)
    except Exception as e:
        raise MailError(f"{type(e).__name__}: {e}") from e
    return "sent"


def _login(s: smtplib.SMTP) -> None:
    if config.SMTP_USER:
        s.login(config.SMTP_USER, config.SMTP_PASSWORD)
