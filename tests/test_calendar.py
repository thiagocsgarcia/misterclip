"""Calendário da Agenda: itens por mês (agendamentos e execuções manuais), janela com folga e validação."""
import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient

from app import db, scheduler
from app.main import app
from app.pipeline.backends.fake import FakeBackend

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui.\n\n"
        "[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual curta.")
UTC = dt.timezone.utc


def ts(y, m, d, h=0, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=UTC).timestamp()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


@pytest.fixture(autouse=True)
def clean_schedules():
    for s in db.schedules_list(500):
        if s["status"] == "pending":
            db.schedule_update(s["id"], status="cancelled", finished=time.time())
    yield


def wait(client, jid, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def planned(client, title="Calendário"):
    pid = client.post("/api/projects", json={"title": title, "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json()["id"])["status"] == "done"
    return pid


def month(client, ym):
    r = client.get(f"/api/calendar?month={ym}")
    assert r.status_code == 200, r.text
    return r.json()["itens"]


@pytest.mark.parametrize("bad", ["", "2026", "2026-13", "2026-00", "2019-12", "2101-01", "abc", "2026-1"])
def test_invalid_months_are_rejected(client, bad):
    assert client.get(f"/api/calendar?month={bad}").status_code == 422


def test_schedule_shows_in_its_month_with_estimated_end_and_is_cancellable(client):
    pid = planned(client, "Agendado no calendário")
    s = db.schedule_create(pid, ts(2031, 5, 10, 2, 0))
    items = [i for i in month(client, "2031-05") if i["id"] == f"s:{s['id']}"]
    assert len(items) == 1
    it = items[0]
    assert it["origem"] == "agendamento" and it["status"] == "pending" and it["project_title"] == "Agendado no calendário"
    assert it["inicio"] == ts(2031, 5, 10, 2, 0) and it["fim"] > it["inicio"] and it["fim_estimado"] is True and it["cancelavel"] is True
    assert all(i["id"] != f"s:{s['id']}" for i in month(client, "2031-08"))                   # fora da janela do mês
    assert [i for i in month(client, "2031-05") if i["id"] == f"s:{s['id']}"][0]["inicio"] == it["inicio"]


def test_window_has_slack_so_the_client_can_bucket_by_local_day(client):
    pid = planned(client, "Virada")
    a = db.schedule_create(pid, ts(2031, 1, 1, 0, 30))        # 31/12 21:30 em São Paulo: pertence a dezembro, no fuso do usuário
    assert any(i["id"] == f"s:{a['id']}" for i in month(client, "2030-12"))                     # a janela de dezembro vai além do mês
    assert any(i["id"] == f"s:{a['id']}" for i in month(client, "2031-01"))
    assert month(client, "2030-12") is not None and client.get("/api/calendar?month=2030-12").status_code == 200   # dezembro -> janeiro (virada do ano)


def test_finished_schedule_uses_real_end_and_manual_runs_are_listed_separately(client, monkeypatch):
    pid = planned(client, "Histórico")
    run_at = time.time() + 600
    sid = client.put(f"/api/projects/{pid}/schedule", json={"run_at": run_at}).json()["id"]
    t0 = time.time()
    while db.schedule_get(sid)["status"] != "done":
        scheduler.tick(now=run_at + 1)
        assert time.time() - t0 < 180
        time.sleep(0.15)
    # uma preparação manual (fora do agendamento) em seguida
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json()["id"])["status"] == "done"
    ym = dt.datetime.now(UTC).strftime("%Y-%m")
    items = [i for i in month(client, ym) if i["project_id"] == pid]
    sch = [i for i in items if i["origem"] == "agendamento"]
    man = [i for i in items if i["origem"] == "manual"]
    assert len(sch) == 1 and sch[0]["status"] == "done" and sch[0]["fim_estimado"] is False and sch[0]["cancelavel"] is False
    assert sch[0]["fim"] == pytest.approx(db.schedule_get(sid)["finished"], abs=1) or sch[0]["fim"] >= sch[0]["inicio"] + 60
    assert [m["tipo"] for m in man] == ["preparar"] and man[0]["status"] == "done"            # os jobs do agendamento NÃO viram "manuais"
    assert not any(i["tipo"] in ("renderizar",) and i["origem"] == "manual" for i in items)


def test_failed_manual_job_carries_its_message(client, monkeypatch):
    pid = planned(client, "Falha no calendário")
    monkeypatch.setattr(FakeBackend, "tts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("GPU sem memória (simulado)")))
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json()["id"])["status"] == "failed"
    ym = dt.datetime.now(UTC).strftime("%Y-%m")
    failed = [i for i in month(client, ym) if i["project_id"] == pid and i["status"] == "failed"]
    assert failed and "GPU sem memória" in failed[0]["mensagem"]


def test_items_are_sorted_by_start(client):
    ym = dt.datetime.now(UTC).strftime("%Y-%m")
    starts = [i["inicio"] for i in month(client, ym)]
    assert starts == sorted(starts)
