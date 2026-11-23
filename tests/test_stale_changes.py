"""Trocar o estilo (ou a voz) de um vídeo pronto marca imagens (ou narrações) como desatualizadas; o usuário pode desfazer."""
import time

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui. "
        "Terceira frase seguindo o ritmo calmo da narração em estudo.\n\n[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual curta.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def done_project(client, profile="cinematico-sombrio"):
    pid = client.post("/api/projects", json={"title": "Estilo", "text": TEXT, "profile_id": profile}).json()["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "done"
    return pid


def get(client, pid):
    return client.get(f"/api/projects/{pid}").json()


def outdated(p):
    return [s for s in p["scenes"] if s["image"] and s["dirty_image"]]


def render_works_without_preparing(client, pid):
    j = wait(client, client.post(f"/api/projects/{pid}/render").json())
    assert j["status"] == "done", j["message"]


# ------------------------------------------------------------------------- estilo
def test_style_change_is_recorded_and_revert_restores_everything(client):
    pid = done_project(client)
    before = get(client, pid)
    paths = [s["image"] for s in before["scenes"]]
    after = client.put(f"/api/projects/{pid}", json={"profile_id": "cyber-mistico"}).json()
    assert len(outdated(after)) == len(paths) and after["status"] == "done"               # o status do vídeo não muda
    sc = after["meta"]["style_change"]
    assert sc["from"] == "cinematico-sombrio" and sc["to"] == "cyber-mistico" and len(sc["scenes"]) == len(paths)
    refused = client.post(f"/api/projects/{pid}/render")                                       # antes: virava um job que falhava
    assert refused.status_code == 409 and "desatualizadas" in refused.json()["detail"]
    assert get(client, pid)["status"] == "done"                                                # e não rebaixava o status do vídeo

    rev = client.post(f"/api/projects/{pid}/style/revert", json={"profile_id": "cinematico-sombrio"}).json()
    assert rev["profile_id"] == "cinematico-sombrio" and not outdated(rev) and "style_change" not in rev["meta"]
    assert [s["image"] for s in rev["scenes"]] == paths and rev["status"] == "done"            # nada foi apagado ou refeito
    render_works_without_preparing(client, pid)


def test_switching_back_by_hand_also_clears_the_flags(client):
    pid = done_project(client)
    client.put(f"/api/projects/{pid}", json={"profile_id": "cyber-mistico"})
    back = client.put(f"/api/projects/{pid}", json={"profile_id": "cinematico-sombrio"}).json()
    assert not outdated(back) and "style_change" not in back["meta"]


def test_keep_current_images_accepts_the_new_style_for_the_future(client):
    pid = done_project(client)
    paths = [s["image"] for s in get(client, pid)["scenes"]]
    client.put(f"/api/projects/{pid}", json={"profile_id": "pintura-simbolista"})
    kept = client.post(f"/api/projects/{pid}/stale/keep", json={"kind": "image"}).json()
    assert not outdated(kept) and kept["profile_id"] == "pintura-simbolista" and "style_change" not in kept["meta"]
    assert [s["image"] for s in kept["scenes"]] == paths and kept["status"] == "done"
    render_works_without_preparing(client, pid)


def test_keep_only_some_scenes(client):
    pid = done_project(client)
    client.put(f"/api/projects/{pid}", json={"profile_id": "cyber-mistico"})
    part = client.post(f"/api/projects/{pid}/stale/keep", json={"kind": "image", "scenes": [1]}).json()
    assert [s["n"] for s in outdated(part)] == [s["n"] for s in part["scenes"] if s["n"] != 1]
    assert "style_change" in part["meta"]                                                      # ainda há imagens pendentes


def test_origin_is_remembered_across_several_changes(client):
    pid = done_project(client)
    client.put(f"/api/projects/{pid}", json={"profile_id": "cyber-mistico"})
    mid = client.put(f"/api/projects/{pid}", json={"profile_id": "gravura-alquimica"}).json()
    assert mid["meta"]["style_change"]["from"] == "cinematico-sombrio" and mid["meta"]["style_change"]["to"] == "gravura-alquimica"
    rev = client.post(f"/api/projects/{pid}/style/revert", json={"profile_id": mid["meta"]["style_change"]["from"]}).json()
    assert rev["profile_id"] == "cinematico-sombrio" and not outdated(rev)


def test_images_remember_the_style_they_were_made_with(client):
    pid = done_project(client, "gravura-alquimica")
    assert all(s["image_profile"] == "gravura-alquimica" for s in get(client, pid)["scenes"])
    client.put(f"/api/projects/{pid}", json={"profile_id": "cyber-mistico"})
    j = wait(client, client.post(f"/api/projects/{pid}/scenes/1/regenerate", json={}).json())
    assert j["status"] == "done"
    p = get(client, pid)
    assert p["scenes"][0]["image_profile"] == "cyber-mistico" and not p["scenes"][0]["dirty_image"]
    # a cena já refeita no estilo novo não conta como desatualizada se o usuário escolher esse estilo de novo
    again = client.put(f"/api/projects/{pid}", json={"profile_id": "gravura-alquimica"}).json()
    assert again["scenes"][0]["dirty_image"] is True and again["scenes"][1]["dirty_image"] is False


def test_scene_with_own_style_is_not_touched_by_revert(client):
    pid = done_project(client)
    client.patch(f"/api/projects/{pid}/scenes/1", json={"profile_id": "cyber-mistico"})       # marca só a cena 1 como desatualizada
    client.put(f"/api/projects/{pid}", json={"profile_id": "gravura-alquimica"})
    rev = client.post(f"/api/projects/{pid}/style/revert", json={"profile_id": "cinematico-sombrio"}).json()
    assert [s["n"] for s in outdated(rev)] == [1]                                              # a cena 1 continua com a pendência dela


# --------------------------------------------------------------------------- voz
def test_voice_change_can_be_reverted_without_regenerating(client):
    pid = done_project(client)
    old = get(client, pid)
    audios = [s["audio"] for s in old["scenes"]]
    ch = client.put(f"/api/projects/{pid}", json={"voice": "pm_santa", "speed": 0.95}).json()
    assert all(s["dirty_audio"] for s in ch["scenes"]) and ch["meta"]["voice_change"]["from_voice"] == "pm_alex"
    rev = client.post(f"/api/projects/{pid}/voice/revert", json={"voice": "pm_alex", "speed": old["speed"]}).json()
    assert rev["voice"] == "pm_alex" and not any(s["dirty_audio"] for s in rev["scenes"]) and "voice_change" not in rev["meta"]
    assert [s["audio"] for s in rev["scenes"]] == audios
    render_works_without_preparing(client, pid)


def test_keep_current_narration_after_a_voice_change(client):
    pid = done_project(client)
    client.put(f"/api/projects/{pid}", json={"voice": "pf_dora"})
    kept = client.post(f"/api/projects/{pid}/stale/keep", json={"kind": "audio"}).json()
    assert kept["voice"] == "pf_dora" and not any(s["dirty_audio"] for s in kept["scenes"])
    render_works_without_preparing(client, pid)


def test_narration_of_an_edited_text_cannot_be_kept(client):
    """O texto mudou: a narração antiga já não corresponde ao que está escrito, então não dá para "mantê-la"."""
    pid = done_project(client)
    client.patch(f"/api/projects/{pid}/scenes/1", json={"text": "Um texto totalmente novo para esta cena."})
    kept = client.post(f"/api/projects/{pid}/stale/keep", json={"kind": "audio"}).json()
    assert kept["scenes"][0]["dirty_audio"] is True


def test_actions_are_refused_while_busy_and_validate_input(client, monkeypatch):
    pid = done_project(client)
    assert client.post(f"/api/projects/{pid}/stale/keep", json={"kind": "outro"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/style/revert", json={"profile_id": "nao-existe"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/voice/revert", json={"voice": "x", "speed": 0.9}).status_code == 422
    monkeypatch.setattr(db, "project_busy", lambda p: True)
    for path, body in (("stale/keep", {"kind": "image"}), ("style/revert", {"profile_id": "cyber-mistico"}), ("voice/revert", {"voice": "pm_alex", "speed": 0.85})):
        assert client.post(f"/api/projects/{pid}/{path}", json=body).status_code == 409
