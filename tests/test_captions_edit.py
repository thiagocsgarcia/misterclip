"""Editar as legendas e a pausa das cenas depois do vídeo pronto, sem refazer a narração nem as animações."""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app import captions, scheduler
from app.main import app

TEXT = ("Primeira frase para a cena de abertura do vídeo de teste agora. Segunda frase com algumas palavras de apoio ao ritmo calmo. "
        "Terceira frase que continua a narração com mais um pouco de texto.\n\n[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual curta.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def wait(client, job, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("job não terminou")


@pytest.fixture(scope="module")
def pid(client):
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "legendas", "text": TEXT, "profile_id": prof}).json()["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    return pid


def test_make_events_and_build_ass_accept_edited_events():
    words = [[w, i * 0.4, i * 0.4 + 0.35] for i, w in enumerate("uma frase curta para testar a divisão das linhas.".split())]
    ev = captions.make_events([(1.0, words)])
    assert ev and ev[0][0] == pytest.approx(1.0) and all(a < b for a, b, _ in ev)
    ass = captions.build_ass([], 640, 360, {}, events=[[0, 1, "olá {mundo}"], [1.2, 2, "segunda"]])
    assert "olá (mundo)" in ass and "segunda" in ass and ass.count("Dialogue:") == 2


def test_captions_list_edit_apply_and_reset(client, pid):
    c = client.get(f"/api/projects/{pid}/captions").json()
    assert c["items"] and not c["edited"] and c["pode_aplicar"]
    items = c["items"]
    items[0]["text"] = "TEXTO CORRIGIDO À MÃO"
    r = client.put(f"/api/projects/{pid}/captions", json={"items": items}).json()
    assert r["edited"] and r["items"][0]["text"] == "TEXTO CORRIGIDO À MÃO"

    bad = [dict(items[0], end=items[0]["start"] - 1)]
    assert client.put(f"/api/projects/{pid}/captions", json={"items": bad}).status_code == 422             # fim antes do início
    assert client.put(f"/api/projects/{pid}/captions", json={"items": [dict(items[0], text="  ")]}).status_code == 422
    assert client.put(f"/api/projects/{pid}/captions", json={"items": []}).status_code == 422
    overlap = [dict(items[0], start=0, end=2), dict(items[0], start=1, end=3)]
    assert client.put(f"/api/projects/{pid}/captions", json={"items": overlap}).status_code == 422

    before = client.get(f"/api/projects/{pid}").json()
    scene_files = [(s["audio"], s["clip"], s["image"]) for s in before["scenes"]]
    assert wait(client, client.post(f"/api/projects/{pid}/captions/apply").json())["status"] == "done"
    after = client.get(f"/api/projects/{pid}").json()
    assert after["status"] == "done" and [(s["audio"], s["clip"], s["image"]) for s in after["scenes"]] == scene_files   # nada além das legendas
    assert "recaption" in [j["kind"] for j in after["jobs"]]
    ass = client.get(f"/media/{pid}/captions.ass").text
    assert "TEXTO CORRIGIDO À MÃO" in ass
    assert client.get(f"/api/projects/{pid}/download").status_code == 200

    reset = client.delete(f"/api/projects/{pid}/captions").json()
    assert not reset["edited"] and reset["items"][0]["text"] != "TEXTO CORRIGIDO À MÃO"


def test_pause_changes_duration_and_invalidates_caption_edit(client, pid):
    p = client.get(f"/api/projects/{pid}").json()
    s1 = p["scenes"][0]
    base = s1["duration"]
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"pause": 9}).status_code == 422
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"pause": "x"}).status_code == 422

    items = client.get(f"/api/projects/{pid}/captions").json()["items"]
    assert client.put(f"/api/projects/{pid}/captions", json={"items": items}).json()["edited"]
    got = client.patch(f"/api/projects/{pid}/scenes/1", json={"pause": 1.5}).json()
    assert got["duration"] == pytest.approx(got["audio_seconds"] + 1.5, abs=0.002) and got["duration"] != base
    p = client.get(f"/api/projects/{pid}").json()
    assert p["meta"]["render_stale"] is True and p["status"] == "done"
    c = client.get(f"/api/projects/{pid}/captions").json()
    assert not c["edited"] and c["stale_edit"]                                                              # a duração mudou: a edição antiga não vale
    assert client.post(f"/api/projects/{pid}/captions/apply").status_code == 409                          # primeiro a montagem
    assert wait(client, client.post(f"/api/projects/{pid}/render").json())["status"] == "done"
    p = client.get(f"/api/projects/{pid}").json()
    assert p["meta"]["render_stale"] is False
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                f"/{__import__('app.config', fromlist=['DATA']).DATA}/projects/{pid}/final.mp4".replace("//", "/")], capture_output=True, text=True).stdout)
    assert dur == pytest.approx(sum(s["duration"] for s in p["scenes"]), abs=1.0)
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"pause": None}).json()["duration"] == pytest.approx(got["audio_seconds"] + 0.45, abs=0.002)
