"""Gerar só a animação de uma cena (depois de trocar a imagem), sem refazer o vídeo todo."""
import time

import pytest
from fastapi.testclient import TestClient

from app import scheduler
from app.main import app

TEXT = "Primeira frase para a cena de abertura do vídeo de teste agora. Segunda frase com algumas palavras de apoio."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def wait(client, job, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("job não terminou")


def test_animate_one_scene_after_a_new_image(client):
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "anima", "text": TEXT, "profile_id": prof}).json()["id"]
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    assert client.post(f"/api/projects/{pid}/scenes/1/animate").status_code == 409                      # ainda sem imagem
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"motion": "ken_burns"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/scenes/1/animate").status_code == 409                      # zoom suave não anima
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"motion": "ltx"}).status_code == 200
    assert wait(client, client.post(f"/api/projects/{pid}/scenes/1/regenerate", json={"new_seed": True}).json())["status"] == "done"
    s1 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert s1["motion"] == "ltx" and not s1["clip"]                                                       # a imagem nova apagou a animação antiga
    j = wait(client, client.post(f"/api/projects/{pid}/scenes/1/animate").json())
    assert j["status"] == "done"
    s1 = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert s1["clip"] and s1["clip"].startswith("clips/") and "clip_error" not in s1
    assert client.post(f"/api/projects/{pid}/scenes/99/animate").status_code == 404
