"""Progresso por etapa, roteiro ao vivo, retomada depois de reinício e "fazer tudo" sem ficar na tela."""
import time

import pytest
from fastapi.testclient import TestClient

from app import db, scheduler
from app.main import app
from app.pipeline.backends.fake import FakeBackend

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui. "
        "Terceira frase seguindo o ritmo calmo da narração em estudo.\n\n[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual curta.\n"
        "[CENA]\nMais uma cena para termos várias imagens.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()  # o agendador é dirigido à mão (tick) nestes testes
        yield c


def wait(client, jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def new_project(client, title="Progresso"):
    return client.post("/api/projects", json={"title": title, "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]


def planned(client, title="Progresso"):
    pid = new_project(client, title)
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json()["id"])["status"] == "done"
    return pid


def stages(job):
    return {it["key"]: it for it in job["stages"]["items"]}


# --------------------------------------------------------------- barras por etapa
def test_each_process_reports_one_bar_per_stage(client):
    pid = new_project(client)
    plan = wait(client, client.post(f"/api/projects/{pid}/plan").json()["id"])
    n = len(client.get(f"/api/projects/{pid}").json()["scenes"])
    assert stages(plan)["plan"]["total"] == n and stages(plan)["plan"]["done"] == n and stages(plan)["plan"]["state"] == "done"

    prep = wait(client, client.post(f"/api/projects/{pid}/prepare").json()["id"])
    st = stages(prep)
    assert list(st) == ["tts", "align", "image"] and all(v["total"] == n and v["done"] == n and v["state"] == "done" for v in st.values())

    rend = wait(client, client.post(f"/api/projects/{pid}/render").json()["id"])
    st = stages(rend)
    assert list(st) == ["clips", "segments", "final"] and st["segments"]["total"] == n and st["final"]["total"] == 3
    assert all(v["state"] == "done" for v in st.values())

    again = wait(client, client.post(f"/api/projects/{pid}/prepare").json()["id"])           # nada a fazer: etapas vazias contam como prontas
    assert all(v["total"] == 0 and v["state"] == "done" for v in stages(again).values())


def test_progress_is_visible_while_running_and_scenes_state_follows_it(client, monkeypatch):
    orig = FakeBackend.image
    monkeypatch.setattr(FakeBackend, "image", lambda self, *a, **k: (time.sleep(0.5), orig(self, *a, **k))[1])
    pid = planned(client, "Ao vivo")
    n = len(client.get(f"/api/projects/{pid}").json()["scenes"])
    before = client.get(f"/api/projects/{pid}/scenes-state").json()
    assert len(before["scenes"]) == n and all(s[3] == 0 for s in before["scenes"]) and before["current"] is None

    job = client.post(f"/api/projects/{pid}/prepare").json()
    seen_current, seen_done, mid = set(), set(), None
    t0 = time.time()
    while time.time() - t0 < 60:
        j = client.get(f"/api/projects/{pid}/status").json()["job"]
        if j["status"] == "done":
            break
        img = next((it for it in (j["stages"] or {}).get("items", []) if it["key"] == "image"), None)
        if img and img["state"] == "running":
            seen_done.add(img["done"])
            cur = j["stages"]["current"]
            if cur:
                seen_current.add(cur)
            state = client.get(f"/api/projects/{pid}/scenes-state").json()
            if 0 < sum(s[3] for s in state["scenes"]) < n and mid is None:
                mid = state                                                              # estado no meio: umas prontas, outras não
        time.sleep(0.1)
    assert len(seen_done) >= 2 and len(seen_current) >= 2                                # a contagem e a cena atual andam
    assert mid is not None and mid["current"] is not None
    assert all(s[1] == 1 and s[2] == 1 for s in mid["scenes"])                           # voz e tempos já estavam prontos
    after = client.get(f"/api/projects/{pid}/scenes-state").json()
    assert all(s[3] == 1 for s in after["scenes"]) and after["current"] is None
    assert wait(client, job["id"])["status"] == "done"


def test_project_list_shows_the_running_process(client, monkeypatch):
    orig = FakeBackend.image
    monkeypatch.setattr(FakeBackend, "image", lambda self, *a, **k: (time.sleep(0.4), orig(self, *a, **k))[1])
    pid = planned(client, "Na lista")
    job = client.post(f"/api/projects/{pid}/prepare").json()
    t0, item = time.time(), None
    while time.time() - t0 < 30 and not item:
        item = next((p for p in client.get("/api/projects").json() if p["id"] == pid and p["active_job"]), None)
        time.sleep(0.05)
    assert item and item["active_job"]["kind"] == "prepare" and 0 <= item["active_job"]["progress"] <= 1
    wait(client, job["id"])
    assert next(p for p in client.get("/api/projects").json() if p["id"] == pid)["active_job"] is None


# ----------------------------------------------------------- retomar depois de reinício
def make_running_job(pid, kind="prepare", attempts=1):
    with db._lock:                                            # atômico: o worker não pega o job antes de virar "running"
        job = db.job_create(kind, pid)
        db.job_update(job["id"], status="running", started=time.time(), attempts=attempts, progress=0.4)
    return job["id"]


def test_interrupted_job_is_requeued_and_finishes_after_restart(client):
    pid = planned(client, "Reinício")
    jid = make_running_job(pid, "prepare", attempts=1)
    out = db.resume_interrupted()                               # é o que acontece ao iniciar o serviço
    assert out["requeued"] >= 1
    j = wait(client, jid)
    assert j["status"] == "done" and j["attempts"] == 2          # tentou de novo (2ª tentativa) e concluiu
    assert client.get(f"/api/projects/{pid}").json()["status"] == "storyboard"


def test_job_that_keeps_being_interrupted_is_given_up_on(client):
    pid = planned(client, "Desiste")
    jid = make_running_job(pid, "prepare", attempts=db.MAX_ATTEMPTS)
    out = db.resume_interrupted()
    assert out["failed"] >= 1
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "failed" and "reinício" in j["message"]


def test_job_being_cancelled_is_closed_as_cancelled_on_restart(client):
    pid = planned(client, "Cancelando")
    with db._lock:
        job = db.job_create("prepare", pid)
        db.job_update(job["id"], status="cancelling", started=time.time())
    db.resume_interrupted()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "cancelled"


def test_schema_migration_adds_columns_to_an_old_database(tmp_path):
    import sqlite3

    con = sqlite3.connect(tmp_path / "antigo.db")
    con.executescript("CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT, kind TEXT, payload TEXT, status TEXT, progress REAL, "
                      "message TEXT, result TEXT, created REAL, started REAL, finished REAL);")
    con.execute("INSERT INTO jobs VALUES ('x','p','prepare','{}','running',0.5,'m',NULL,1,2,NULL)")
    db._migrate(con)                                            # conexão isolada: não mexe no banco dos outros testes
    db._migrate(con)                                            # e é idempotente
    assert {r[1] for r in con.execute("PRAGMA table_info(jobs)")} >= {"stages", "attempts"}
    assert con.execute("SELECT attempts FROM jobs WHERE id='x'").fetchone()[0] in (None, 0)
    con.close()


# -------------------------------------------------------------- fazer tudo sem ficar na tela
def test_run_all_prepares_and_renders_without_anyone_watching(client):
    pid = planned(client, "Tudo de uma vez")
    sc = client.post(f"/api/projects/{pid}/run-all")
    assert sc.status_code == 202 and sc.json()["status"] in ("pending", "running")
    sid = sc.json()["id"]
    t0 = time.time()
    while db.schedule_get(sid)["status"] not in ("done", "failed"):
        scheduler.tick()
        assert time.time() - t0 < 240
        time.sleep(0.2)
    assert db.schedule_get(sid)["status"] == "done"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "done" and [j["kind"] for j in reversed(proj["jobs"])][-4:] == ["prepare", "render", "metadata", "thumbnail"]
    assert client.get(f"/api/projects/{pid}/download").status_code == 200


def test_run_all_validation(client, monkeypatch):
    empty = new_project(client, "Sem cenas")
    assert client.post(f"/api/projects/{empty}/run-all").status_code == 202                  # rascunho: o sistema divide o roteiro sozinho
    assert client.post("/api/projects/nao-existe/run-all").status_code == 404
    pid = planned(client, "Ocupado")
    monkeypatch.setattr(db, "project_busy", lambda p: True)
    assert client.post(f"/api/projects/{pid}/run-all").status_code == 409
