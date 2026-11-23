"""Tela de login: enviar o token por e-mail (sem enviar a ninguém além do dono configurado)."""
import pytest
from fastapi.testclient import TestClient

from app import config, mailer
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(config, "TOKEN", "segredo-de-teste")
    monkeypatch.setattr(mailer, "_sent", [])
    with TestClient(app) as c:
        yield c


def test_endpoint_is_public_but_the_rest_is_not(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/send-token").status_code == 503      # sem SMTP configurado


def test_sends_only_to_configured_owner_and_rate_limits(client, monkeypatch):
    for k, v in (("TOKEN_EMAIL", "dono@exemplo.com"), ("SMTP_HOST", "smtp.exemplo.com"), ("SMTP_FROM", "mc@exemplo.com"), ("SMTP_USER", ""), ("SMTP_PORT", 587)):
        monkeypatch.setattr(config, k, v)
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    r = client.post("/api/auth/send-token", json={"to": "invasor@mal.com"}, headers={"X-To": "invasor@mal.com"})
    assert r.status_code == 200 and len(sent) == 1
    assert sent[0]["To"] == "dono@exemplo.com" and "segredo-de-teste" in sent[0].get_content()      # destinatário nunca vem do pedido
    assert "segredo-de-teste" not in r.text                                                          # a resposta da tela não repete o token
    assert client.post("/api/auth/send-token").status_code == 429 and len(sent) == 1


def test_smtp_failure_hides_the_reason_from_the_page(client, monkeypatch):
    for k, v in (("TOKEN_EMAIL", "dono@exemplo.com"), ("SMTP_HOST", "smtp.exemplo.com"), ("SMTP_FROM", "mc@exemplo.com"), ("SMTP_PORT", 587)):
        monkeypatch.setattr(config, k, v)
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(OSError("senha errada smtp.exemplo.com")))
    r = client.post("/api/auth/send-token")
    assert r.status_code == 502 and "senha errada" not in r.text
