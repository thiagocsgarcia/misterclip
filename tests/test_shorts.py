"""Shorts: escolha dos trechos (30 a 45 s, limites de cena) e geração do corte vertical a partir do vídeo pronto."""
import pathlib
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app import db, shorts
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job não terminou")


def fake_items(n=20, dur=9.0):
    t, out = 0.0, []
    for k in range(1, n + 1):
        out.append({"n": k, "text": ("Por que a máquina fala? " if k % 5 == 1 else "Uma ideia segue aqui. ") * 2, "start": t, "duration": dur, "words": []})
        t += dur
    return out


def test_windows_are_between_30_and_45_seconds_on_scene_boundaries():
    items = fake_items()
    ws = shorts.windows(items)
    assert ws and all(30 <= sum(s["duration"] for s in items[i:j + 1]) <= 45 for i, j in ws)


def test_choose_returns_non_overlapping_windows_in_order_with_hook_and_title():
    items = fake_items(40)
    picked = shorts.choose(items, 3)
    assert len(picked) == 3 and picked == sorted(picked, key=lambda p: p["i"])
    assert all(a["j"] < b["i"] for a, b in zip(picked, picked[1:]))
    assert all(p["hook"] and p["title"] and len(p["title"]) <= 60 for p in picked)


def test_choose_prefers_a_valid_llm_pick_and_ignores_garbage():
    items = fake_items(40)

    class Good:
        def llm_json(self, system, user):
            return {"shorts": [{"start_scene": 6, "end_scene": 9, "hook": "Por que a máquina fala agora mesmo hoje sim", "title": "A máquina que fala"}]}

    got = shorts.choose(items, 2, Good())
    assert (got[0]["i"], got[0]["j"]) == (5, 8) and got[0]["title"] == "A máquina que fala" and len(got) == 2

    class Bad:
        def llm_json(self, system, user):
            return {"shorts": [{"start_scene": 99, "end_scene": 2}, {"x": 1}]}

    assert len(shorts.choose(items, 2, Bad())) == 2


def test_short_video_is_refused_and_needs_a_finished_video(client):
    prof = client.get("/api/profiles").json()[0]["id"]
    p = client.post("/api/projects", json={"title": "x", "text": "Frase um. Frase dois.", "profile_id": prof}).json()
    assert client.post(f"/api/projects/{p['id']}/shorts/generate", json={"count": 2}).status_code == 409
    assert client.get(f"/api/projects/{p['id']}/shorts").json()["items"] == []


def test_generate_shorts_end_to_end_in_fake_mode(client):
    prof = client.get("/api/profiles").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do roteiro de teste que precisa ficar longa o bastante para render." for i in range(1, 60))
    p = client.post("/api/projects", json={"title": "Com shorts", "text": text, "profile_id": prof}).json()
    pid = p["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "done"
    r = client.post(f"/api/projects/{pid}/shorts/generate", json={"count": 2, "layout": "blur"})
    assert r.status_code == 202
    assert wait(client, r.json())["status"] == "done"
    st = client.get(f"/api/projects/{pid}/shorts").json()
    assert len(st["items"]) == 2 and st["ready"]
    it = st["items"][0]
    f = pathlib.Path(db.config.DATA) / "projects" / pid / it["file"]
    assert f.is_file() and f.stat().st_size > 1000
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0", str(f)],
                         capture_output=True, text=True).stdout.split()
    assert "1080,1920" in out[0] and 29 <= float(out[1]) <= 46
    assert it["hook"] and "#Shorts" in it["description"]
    assert client.get(f"/api/projects/{pid}/shorts/{it['i']}/download").status_code == 200
    assert client.get(f"/api/projects/{pid}/shorts/99/download").status_code == 404
    assert client.post(f"/api/projects/{pid}/shorts/generate", json={"layout": "xyz"}).status_code == 422
