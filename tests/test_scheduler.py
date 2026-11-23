"""Agendamento de renderização por vídeo: validação, execução em cadeia, fila da GPU, cancelamento e reinício."""
import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient

from app import db, notify, scheduler
from app.main import app
from app.pipeline.backends.fake import FakeBackend

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui. "
        "Terceira frase seguindo o ritmo calmo da narração em estudo.\n\n[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual curta.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()  # os testes dirigem o agendador à mão (tick com horário simulado), sem a thread de fundo
        yield c


@pytest.fixture(autouse=True)
def no_leftovers():
    for s in db.schedules_list(500):
        if s["status"] in db.ACTIVE_SCHEDULE and s["status"] == "pending":
            db.schedule_update(s["id"], status="cancelled", finished=time.time())
    yield


def wait_job(client, jid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def planned(client, title="Agendado"):
    pid = client.post("/api/projects", json={"title": title, "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    j = client.post(f"/api/projects/{pid}/plan").json()
    assert wait_job(client, j["id"])["status"] == "done"
    return pid


def drive(sid, now, timeout=180, until=("done", "failed", "cancelled", "missed")):
    """Faz o agendador andar (como se fosse `now`) até o agendamento chegar a um estado final."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        scheduler.tick(now=now)
        s = db.schedule_get(sid)
        if s["status"] in until:
            return s
        time.sleep(0.15)
    raise AssertionError(f"agendamento não terminou: {db.schedule_get(sid)}")


# ------------------------------------------------------------------------ validação
def test_validation_and_replace_and_cancel(client):
    pid = planned(client)
    future = time.time() + 3600
    for bad in (time.time() - 60, time.time() + 2, time.time() + 400 * 86400, "isto não é data", "2030-01-01T10:00:00"):
        assert client.put(f"/api/projects/{pid}/schedule", json={"run_at": bad}).status_code == 422, bad
    draft = client.post("/api/projects", json={"title": "sem cenas", "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    assert client.put(f"/api/projects/{draft}/schedule", json={"run_at": future}).status_code == 422   # nada planejado
    assert client.put("/api/projects/nao-existe/schedule", json={"run_at": future}).status_code == 404

    a = client.put(f"/api/projects/{pid}/schedule", json={"run_at": future}).json()
    assert a["status"] == "pending" and a["project_title"] == "Agendado" and a["eta_seconds"] is not None
    iso = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)).isoformat()                       # ISO com fuso é aceito
    b = client.put(f"/api/projects/{pid}/schedule", json={"run_at": iso}).json()
    assert b["id"] != a["id"] and db.schedule_get(a["id"])["status"] == "cancelled"                     # o novo substitui o antigo
    assert client.get(f"/api/projects/{pid}/schedule").json()["id"] == b["id"]
    assert any(x["id"] == b["id"] for x in client.get("/api/schedules").json())
    assert next(p for p in client.get("/api/projects").json() if p["id"] == pid)["schedule"]["status"] == "pending"
    assert client.get(f"/api/projects/{pid}/status").json()["schedule"]["status"] == "pending"

    assert client.delete(f"/api/projects/{pid}/schedule").json()["status"] == "cancelled"
    assert client.delete(f"/api/projects/{pid}/schedule").status_code == 404
    assert next(p for p in client.get("/api/projects").json() if p["id"] == pid)["schedule"] is None


# ----------------------------------------------------------------- execução em cadeia
def test_due_schedule_prepares_then_renders_and_notifies(client, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: sent.append(a))
    pid = planned(client, "noite")
    run_at = time.time() + 3600
    sid = client.put(f"/api/projects/{pid}/schedule", json={"run_at": run_at}).json()["id"]

    scheduler.tick(now=run_at - 5)
    assert db.schedule_get(sid)["status"] == "pending"                         # ainda não é a hora
    final = drive(sid, run_at + 1)
    assert final["status"] == "done" and final["message"] == "vídeo pronto e preparado para publicar"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "done" and client.get(f"/api/projects/{pid}/download").status_code == 200
    kinds = [j["kind"] for j in reversed(proj["jobs"])]
    assert kinds[-4:] == ["prepare", "render", "metadata", "thumbnail"]            # a cadeia do canal: vídeo, depois título e miniaturas (Shorts só em vídeo de 30 s ou mais)
    assert proj["meta"]["youtube"]["title"] and proj["meta"]["thumbnail"]["variants"]
    assert any(a[0] == "schedule_done" and a[1] == "noite" for a in sent)


def test_chain_steps_follow_the_channel_rules():
    long = {"channel_id": None, "scenes": [{"duration": 12.0}] * 6}
    short = {"channel_id": None, "scenes": [{"duration": 5.0}] * 3}
    assert [k for k, _ in scheduler._extras(long)] == ["metadata", "thumbnail", "shorts"] and dict(scheduler._extras(long))["shorts"]["count"] == 2
    assert [k for k, _ in scheduler._extras(short)] == ["metadata", "thumbnail"]
    assert scheduler._next_step(long, "plan")[0] == "prepare" and scheduler._next_step(long, "prepare")[0] == "render" and scheduler._next_step(long, "render")[0] == "metadata"
    assert scheduler._next_step(long, "metadata")[0] == "thumbnail" and scheduler._next_step(long, "thumbnail")[0] == "shorts" and scheduler._next_step(long, "shorts") is None


def test_due_schedule_waits_for_busy_gpu_and_does_not_skip_the_queue(client, monkeypatch):
    orig = FakeBackend.image
    monkeypatch.setattr(FakeBackend, "image", lambda self, *a, **k: (time.sleep(0.4), orig(self, *a, **k))[1])
    a, b = planned(client, "A"), planned(client, "B")
    busy = client.post(f"/api/projects/{a}/prepare").json()                       # GPU ocupada com o projeto A
    run_at = time.time() + 600
    sid = client.put(f"/api/projects/{b}/schedule", json={"run_at": run_at}).json()["id"]
    scheduler.tick(now=run_at + 1)
    assert db.schedule_get(sid)["status"] == "pending"                          # espera a vez
    assert wait_job(client, busy["id"])["status"] == "done"
    assert drive(sid, run_at + 2)["status"] == "done"


def test_overdue_beyond_grace_is_marked_missed(client):
    pid = planned(client, "perdido")
    s = db.schedule_create(pid, time.time() - scheduler.GRACE_SECONDS - 60)
    assert drive(s["id"], time.time())["status"] == "missed"
    assert "perdido" in db.schedule_get(s["id"])["message"]


def test_overdue_within_grace_still_runs(client):
    pid = planned(client, "atrasado")
    s = db.schedule_create(pid, time.time() - 1800)                              # a andes voltou 30 min depois da hora
    assert drive(s["id"], time.time())["status"] == "done"


# --------------------------------------------------------------- falha, cancelar, reinício
def test_failed_step_marks_schedule_failed_with_reason(client, monkeypatch):
    pid = planned(client, "falha")
    monkeypatch.setattr(FakeBackend, "tts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("GPU sem memória (simulado)")))
    run_at = time.time() + 600
    sid = client.put(f"/api/projects/{pid}/schedule", json={"run_at": run_at}).json()["id"]
    s = drive(sid, run_at + 1)
    assert s["status"] == "failed" and "GPU sem memória" in s["message"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "planned"
    assert client.get(f"/api/projects/{pid}/schedule").json()["status"] == "failed"   # fica no histórico


def test_cancel_running_schedule_stops_the_job_and_never_renders(client, monkeypatch):
    orig = FakeBackend.image
    monkeypatch.setattr(FakeBackend, "image", lambda self, *a, **k: (time.sleep(0.4), orig(self, *a, **k))[1])
    pid = planned(client, "cancelável")
    run_at = time.time() + 600
    sid = client.put(f"/api/projects/{pid}/schedule", json={"run_at": run_at}).json()["id"]
    scheduler.tick(now=run_at + 1)
    s = db.schedule_get(sid)
    assert s["status"] == "running" and s["step"] == "prepare"
    t0 = time.time()
    while not client.get(f"/api/jobs/{s['job_id']}").json()["message"].startswith("imagem"):
        assert time.time() - t0 < 60
        time.sleep(0.05)
    assert client.delete(f"/api/projects/{pid}/schedule").status_code == 200
    assert wait_job(client, s["job_id"])["status"] == "cancelled"
    assert drive(sid, run_at + 2)["status"] == "cancelled"
    assert not any(j["kind"] == "render" for j in client.get(f"/api/projects/{pid}").json()["jobs"])


def test_restart_in_the_middle_retries_the_step_once(client):
    pid = planned(client, "reinício")
    s = db.schedule_create(pid, time.time() - 5)
    job = db.job_create("prepare", pid)
    db.job_update(job["id"], status="failed", message="interrompido por reinício")
    db.schedule_update(s["id"], status="running", step="prepare", job_id=job["id"], started=time.time())
    scheduler.tick(now=time.time())
    cur = db.schedule_get(s["id"])
    assert cur["retries"] == 1 and cur["job_id"] != job["id"] and cur["status"] == "running"   # reenviou a mesma etapa
    assert drive(s["id"], time.time())["status"] == "done"
    # uma segunda queda no mesmo agendamento já não é reenviada
    s2 = db.schedule_create(pid, time.time() - 5)
    j2 = db.job_create("prepare", pid)
    db.job_update(j2["id"], status="failed", message="interrompido por reinício")
    db.schedule_update(s2["id"], status="running", step="prepare", job_id=j2["id"], retries=1, started=time.time())
    scheduler.tick(now=time.time())
    assert db.schedule_get(s2["id"])["status"] == "failed"
