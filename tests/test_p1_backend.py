"""P1 (mobile/usabilidade): polling leve, payload enxuto, operações de cena e amostra de voz."""
import pathlib
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui. "
        "Terceira frase seguindo o ritmo calmo da narração em estudo. Quarta frase que ainda cabe neste parágrafo de teste.\n\n"
        "[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual, também curta.\n[CENA]\nMais uma para garantir várias imagens.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def ready_project(client, title="P1"):
    pid = client.post("/api/projects", json={"title": title, "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    return pid


def get(client, pid):
    return client.get(f"/api/projects/{pid}").json()


def exists(pid, rel):
    return (config.DATA / "projects" / pid / rel).is_file()


# --------------------------------------------------------------- polling leve / payload enxuto
def test_status_endpoint_is_tiny_and_slim_drops_word_timings(client):
    pid = ready_project(client, "enxuto")
    full = client.get(f"/api/projects/{pid}")
    slim = client.get(f"/api/projects/{pid}?slim=1")
    st = client.get(f"/api/projects/{pid}/status")
    assert all("words" in s for s in full.json()["scenes"]) and all("words" not in s and s["has_words"] for s in slim.json()["scenes"])
    assert len(slim.content) < 0.8 * len(full.content)           # os tempos por palavra são a maior parte do JSON
    assert len(st.content) < 900
    j = st.json()
    assert j["status"] == "storyboard" and j["busy"] is False and j["job"]["kind"] == "prepare" and j["job"]["status"] == "done"
    assert client.get("/api/projects/nao-existe/status").status_code == 404


# --------------------------------------------------------------------- operações de cena
def test_merge_split_delete_add_keep_files_and_state_consistent(client):
    pid = ready_project(client, "ops")
    p = get(client, pid)
    n0 = len(p["scenes"])
    t1, t2 = p["scenes"][0]["text"], p["scenes"][1]["text"]
    old_audio = [p["scenes"][0]["audio"], p["scenes"][1]["audio"]]
    old_img2 = p["scenes"][1]["image"]

    # mesclar 1+2: texto junto, 1 cena a menos, a imagem da 1ª vale, narração a refazer, arquivos órfãos apagados
    m = client.post(f"/api/projects/{pid}/scenes/1/merge").json()
    assert len(m["scenes"]) == n0 - 1 and m["scenes"][0]["text"] == f"{t1} {t2}"
    assert m["scenes"][0]["image"] == p["scenes"][0]["image"] and not m["scenes"][0]["dirty_image"] and m["scenes"][0]["dirty_audio"]
    assert [s["n"] for s in m["scenes"]] == list(range(1, n0))
    assert m["status"] == "planned"                                  # há narração a refazer
    assert not any(exists(pid, a) for a in old_audio) and not exists(pid, old_img2)

    # dividir a 1ª cena: duas cenas, cortando em limite de palavra; a 2ª precisa de imagem nova
    text = m["scenes"][0]["text"]
    sp = client.post(f"/api/projects/{pid}/scenes/1/split", json={"at": len(text) // 2}).json()
    assert len(sp["scenes"]) == n0 and " ".join([sp["scenes"][0]["text"], sp["scenes"][1]["text"]]) == text
    assert sp["scenes"][1]["dirty_image"] and not sp["scenes"][0]["dirty_image"]
    assert client.post(f"/api/projects/{pid}/scenes/1/split", json={"at": 0}).status_code == 422

    # adicionar após a cena 2 e apagar a última
    ad = client.post(f"/api/projects/{pid}/scenes", json={"after": 2, "text": "Cena nova inserida pelo usuário."}).json()
    assert ad["scenes"][2]["text"].startswith("Cena nova") and len(ad["scenes"]) == n0 + 1
    last = ad["scenes"][-1]
    dl = client.delete(f"/api/projects/{pid}/scenes/{last['n']}").json()
    assert len(dl["scenes"]) == n0 and not (last.get("image") and exists(pid, last["image"]))
    assert client.post(f"/api/projects/{pid}/scenes", json={"after": 1, "text": "   "}).status_code == 422
    assert client.post(f"/api/projects/{pid}/scenes/{len(dl['scenes'])}/merge").status_code == 422   # última não tem próxima

    # tudo volta a ficar pronto com um novo "preparar"
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    final = get(client, pid)
    assert final["status"] == "storyboard" and all(s["image"] and s["audio"] and s["words"] for s in final["scenes"])
    imgs = [s["image"] for s in final["scenes"]]
    assert len(set(imgs)) == len(imgs) and all(exists(pid, i) for i in imgs)       # nenhuma cena usa o arquivo de outra


def test_legacy_project_without_ids_does_not_overwrite_images_after_delete(client):
    """Antes, arquivos eram nomeados pelo número: apagar a cena 1 e regerar a 2 sobrescrevia a imagem da (antiga) 2."""
    pid = ready_project(client, "legado")
    p = get(client, pid)
    for s in p["scenes"]:                                                         # simula um projeto criado antes dos ids
        s.pop("id", None)
    items = db.project_get(pid)["scenes"]
    for s in items:
        s.pop("id", None)
    db.project_update(pid, scenes=items)

    assert client.delete(f"/api/projects/{pid}/scenes/1").status_code == 200
    after = get(client, pid)
    before_paths = {s["n"]: s["image"] for s in after["scenes"]}
    job = wait(client, client.post(f"/api/projects/{pid}/scenes/1/regenerate", json={}).json())
    assert job["status"] == "done"
    cur = get(client, pid)
    paths = [s["image"] for s in cur["scenes"]]
    assert len(set(paths)) == len(paths)                                          # caminhos distintos
    for s in cur["scenes"][1:]:
        assert s["image"] == before_paths[s["n"]] and exists(pid, s["image"])       # as demais não foram tocadas


def test_scene_ops_are_refused_while_project_is_busy(client, monkeypatch):
    pid = ready_project(client, "ocupado")
    monkeypatch.setattr(db, "project_busy", lambda p: True)
    assert client.delete(f"/api/projects/{pid}/scenes/1").status_code == 409
    assert client.post(f"/api/projects/{pid}/scenes/1/merge").status_code == 409


# ---------------------------------------------------------------------- amostra de voz
def test_voice_sample_job_is_cached_and_validated(client):
    assert client.post("/api/voice-sample", json={"voice": "nao-existe"}).status_code == 422
    j = wait(client, client.post("/api/voice-sample", json={"voice": "pm_alex", "speed": 0.85}).json())
    assert j["status"] == "done" and j["result"]["audio"] == "voice_samples/pm_alex_0.85.wav"
    r = client.get(f"/media/{j['result']['audio']}")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    f = config.DATA / j["result"]["audio"]
    mtime = f.stat().st_mtime_ns
    again = wait(client, client.post("/api/voice-sample", json={"voice": "pm_alex", "speed": 0.85}).json())
    assert again["status"] == "done" and f.stat().st_mtime_ns == mtime            # reaproveitou o arquivo em cache
