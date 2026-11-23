"""Pipeline completo no backend de teste: roteiro -> cenas -> narração -> storyboard -> MP4."""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEXT = ("Primeiro parágrafo com várias frases curtas para formar cenas. Mais uma frase de apoio aqui agora. "
        "Terceira frase seguindo o mesmo ritmo de narração calma. Quarta frase para fechar o primeiro bloco.\n\n"
        "[CENA]\nUma cena manual escolhida pelo autor do roteiro.\n[CENA]\nOutra cena manual, também curta.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job não terminou")


def test_health_and_profiles(client):
    assert client.get("/api/health").json()["mode"] == "fake"
    assert len(client.get("/api/profiles").json()) >= 4
    assert client.get("/previews/cyber-mistico.jpg").status_code == 200


def test_full_flow(client):
    p = client.post("/api/projects", json={"title": "Teste e2e", "text": TEXT, "profile_id": "cinematico-sombrio"}).json()
    pid = p["id"]

    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "planned" and len(proj["scenes"]) >= 3
    assert all(s["visual_prompt"] for s in proj["scenes"])
    assert any(s["motion"] != "ken_burns" for s in proj["scenes"])          # há cenas animadas
    assert client.post(f"/api/projects/{pid}/render").status_code == 409     # sem preparar não renderiza

    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "storyboard"
    assert all(s["image"] and s["audio"] and s["words"] and not s["dirty_image"] for s in proj["scenes"])
    assert client.get(f"/media/{pid}/{proj['scenes'][0]['thumb']}").status_code == 200
    assert client.get(f"/media/{pid}/../../misterclip.db").status_code in (404, 400)  # sem path traversal

    # edita a cena 2: o prompt visual invalida só a imagem; regerar limpa a marca
    n = proj["scenes"][1]["n"]
    s = client.patch(f"/api/projects/{pid}/scenes/{n}", json={"visual_prompt": "a candle in a dark room"}).json()
    assert s["dirty_image"] and not s["dirty_audio"]
    assert wait(client, client.post(f"/api/projects/{pid}/scenes/{n}/regenerate", json={"profile_id": "cyber-mistico"}).json())["status"] == "done"
    s = next(x for x in client.get(f"/api/projects/{pid}").json()["scenes"] if x["n"] == n)
    assert not s["dirty_image"] and s["profile_id"] == "cyber-mistico"

    job = wait(client, client.post(f"/api/projects/{pid}/render").json(), timeout=300)
    assert job["status"] == "done", job["message"]
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "done"

    r = client.get(f"/api/projects/{pid}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    total = sum(s["duration"] for s in proj["scenes"])
    assert len(r.content) / total < 400_000, "bitrate fora de controle (grão/ruído incompressível?)"  # < ~3 Mbps em 640x360
    path = f"/tmp/mc-e2e-{pid}.mp4"
    open(path, "wb").write(r.content)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True).stdout
    assert "video,640,360" in probe and "audio" in probe
    expected = sum(s["duration"] for s in proj["scenes"])
    vid = next(float(l.split(",")[-1]) for l in probe.splitlines() if l.startswith("video"))
    assert abs(vid - expected) < 0.5, (vid, expected)


def test_profile_test_job_and_busy_guard(client):
    job = client.post("/api/profiles/cyber-mistico/test", json={}).json()
    done = wait(client, job)
    assert done["status"] == "done" and client.get(f"/media/{done['result']['image']}").status_code == 200
    assert client.post("/api/projects", json={"title": "x", "text": "  ", "profile_id": "cyber-mistico"}).status_code == 422
    assert client.post("/api/projects", json={"title": "x", "text": "ok", "profile_id": "nao-existe"}).status_code == 422


def _wav_bytes(seconds=6.0, freq=330, rate=22050):
    import io, math, struct, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(int(seconds * rate))))
    return buf.getvalue()


def test_options_music_upload_validation_and_render(client):
    # música: rejeita formato errado e áudio inválido; aceita wav; lista; apaga
    assert client.post("/api/music", files={"file": ("x.txt", b"oi", "text/plain")}).status_code == 422
    assert client.post("/api/music", files={"file": ("quebrado.mp3", b"nao e audio", "audio/mpeg")}).status_code == 422
    up = client.post("/api/music", files={"file": ("trilha teste.wav", _wav_bytes(), "audio/wav")})
    assert up.status_code == 201 and up.json()["seconds"] > 5
    assert client.get(f"/media/music/{up.json()['name']}").status_code == 200
    assert any(m["name"] == up.json()["name"] for m in client.get("/api/music").json())

    p = client.post("/api/projects", json={"title": "Opções", "text": TEXT, "profile_id": "pintura-simbolista"}).json()
    pid = p["id"]
    bad = client.put(f"/api/projects/{pid}", json={"options": {"transition": "wipe-maluco"}})
    assert bad.status_code == 422
    assert client.put(f"/api/projects/{pid}", json={"options": {"music": {"file": "nao-existe.wav"}}}).status_code == 422
    ok = client.put(f"/api/projects/{pid}", json={"options": {"transition": "dissolve", "transition_seconds": 99,
                                                              "music": {"file": up.json()["name"], "volume": 7, "duck": True}}})
    opts = ok.json()["meta"]["options"]
    assert opts["transition_seconds"] == 2.0 and opts["music"]["volume"] == 1.0   # valores são limitados

    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert wait(client, client.post(f"/api/projects/{pid}/render").json(), timeout=300)["status"] == "done"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["meta"]["rendered_with"] == {"transition": "dissolve", "music": True}
    path = f"/tmp/mc-opt-{pid}.mp4"
    open(path, "wb").write(client.get(f"/api/projects/{pid}/download").content)
    total = sum(s["duration"] for s in proj["scenes"])
    vid = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", path],
                               capture_output=True, text=True).stdout.strip())
    assert abs(vid - total) < 0.6, (vid, total)

    # corte seco também funciona e é registrado
    client.put(f"/api/projects/{pid}", json={"options": {"transition": "cut", "music": {"file": None}}})
    assert wait(client, client.post(f"/api/projects/{pid}/render").json(), timeout=300)["status"] == "done"
    assert client.get(f"/api/projects/{pid}").json()["meta"]["rendered_with"] == {"transition": "cut", "music": False}

    assert client.delete(f"/api/music/{up.json()['name']}").status_code == 204
