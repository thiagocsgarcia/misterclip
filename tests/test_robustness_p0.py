"""P0: recuperar projetos presos, cancelar/tentar de novo, estimativa, aviso de fim, workflows e clipe sem loop."""
import http.server
import json
import pathlib
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db, estimate
from app.main import app
from app.pipeline import assemble
from app.pipeline.backends.comfy import Comfy
from app.pipeline.backends.fake import FakeBackend
from app.pipeline.engine import recover_stuck

TEXT = ("Primeira frase para formar a cena de abertura do vídeo de teste agora. Segunda frase com mais algumas palavras de apoio aqui. "
        "Terceira frase seguindo o ritmo calmo da narração em estudo. Quarta frase que ainda cabe neste parágrafo de teste.\n\n"
        "[CENA]\nUma cena manual curta do autor.\n[CENA]\nOutra cena manual, também curta.\n[CENA]\nMais uma para garantir várias imagens.")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=120, until=("done", "failed", "cancelled")):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in until:
            return j
        time.sleep(0.1)
    raise AssertionError(f"job não chegou a {until}: {j}")


def new_planned(client, title="P0"):
    pid = client.post("/api/projects", json={"title": title, "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    return pid


@pytest.fixture
def slow_images(monkeypatch):
    orig = FakeBackend.image

    def slow(self, *a, **k):
        time.sleep(0.4)
        return orig(self, *a, **k)

    monkeypatch.setattr(FakeBackend, "image", slow)


# ------------------------------------------------------------ cancelar e tentar de novo
def test_cancel_running_prepare_keeps_progress_then_retry_finishes(client, slow_images):
    pid = new_planned(client, "cancelável")
    job = client.post(f"/api/projects/{pid}/prepare").json()
    t0 = time.time()
    while not client.get(f"/api/jobs/{job['id']}").json()["message"].startswith("imagem da cena 2"):
        assert time.time() - t0 < 60
        time.sleep(0.05)
    res = client.post(f"/api/jobs/{job['id']}/cancel")
    assert res.status_code == 202 and res.json()["status"] in ("cancelling", "cancelled")
    done = wait(client, job)
    assert done["status"] == "cancelled" and "cancelado" in done["message"]

    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "planned" and not proj["busy"]                        # voltou a um estado utilizável
    scenes = proj["scenes"]
    assert all(s["audio"] and s["words"] for s in scenes)                           # voz e tempos já feitos ficaram salvos
    assert 1 <= sum(1 for s in scenes if s["image"]) < len(scenes)                  # imagens: parcial
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409          # não cancela job que já acabou

    retry = client.post(f"/api/jobs/{job['id']}/retry")
    assert retry.status_code == 201
    assert wait(client, retry.json())["status"] == "done"
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "storyboard" and all(s["image"] for s in proj["scenes"])


def test_cancel_queued_job_never_runs_and_retry_guards(client, slow_images):
    a, b = new_planned(client, "A"), new_planned(client, "B")
    first = client.post(f"/api/projects/{a}/prepare").json()
    queued = client.post(f"/api/projects/{b}/prepare").json()                       # fica na fila atrás do primeiro
    res = client.post(f"/api/jobs/{queued['id']}/cancel").json()
    assert res["status"] == "cancelled"
    assert wait(client, first)["status"] == "done"
    assert client.get(f"/api/projects/{b}").json()["status"] == "planned"           # o job cancelado não rodou
    assert client.post(f"/api/jobs/{first['id']}/retry").status_code == 409         # retry só de job falho/cancelado
    # tentar de novo enquanto o projeto está ocupado é recusado
    again = client.post(f"/api/jobs/{queued['id']}/retry").json()
    assert client.post(f"/api/jobs/{queued['id']}/retry").status_code == 409
    wait(client, again)


def test_failed_job_settles_project_and_records_error(client, monkeypatch):
    pid = new_planned(client, "falha")
    monkeypatch.setattr(FakeBackend, "tts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("GPU sem memória (simulado)")))
    job = wait(client, client.post(f"/api/projects/{pid}/prepare").json())
    assert job["status"] == "failed" and "GPU sem memória" in job["message"]
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "planned" and "GPU sem memória" in proj["meta"]["last_error"]


# ----------------------------------------------------------------- recuperação no startup
def test_recover_stuck_rendering_project(client):
    pid = new_planned(client, "preso")
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    db.project_update(pid, status="rendering")                                      # estado deixado por um reinício no meio do render
    assert pid in recover_stuck()
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "storyboard" and "reinício" in proj["meta"]["last_error"]
    assert client.post(f"/api/projects/{pid}/render").status_code == 202           # dá para renderizar de novo


def test_recover_does_not_touch_projects_with_active_jobs(client, monkeypatch):
    pid = new_planned(client, "ativo")
    db.project_update(pid, status="rendering")
    monkeypatch.setattr(db, "project_busy", lambda p: True)
    assert pid not in recover_stuck()
    db.project_update(pid, status="planned")


# ----------------------------------------------------------------------- estimativa
def fake_project(n=119, wan=35, ready=False):
    scenes = [{"n": i, "est_seconds": 9.5, "duration": 10 if ready else None, "motion": "wan" if i < wan else "ken_burns",
               "audio": "a" if ready else None, "image": "i" if ready else None, "clip": None,
               "dirty_audio": not ready, "dirty_image": not ready} for i in range(n)]
    return {"scenes": scenes, "text": "x. " * n}


def test_estimate_scales_with_real_measurements(monkeypatch):
    monkeypatch.setattr(config, "MODE", "real")
    e = estimate.for_project(fake_project())
    assert e["clips"] == {"wan": 35, "ltx": 0} and e["scenes"] == 119
    assert 2 * 3600 < e["seconds"]["render"] < 3 * 3600                              # 35 clipes Wan ≈ 2,3 h
    assert 20 * 60 < e["seconds"]["prepare"] < 45 * 60                               # ~119 imagens + voz
    assert "h" in e["human"]["render"] and "min" in e["human"]["prepare"]
    ready = estimate.for_project(fake_project(ready=True))
    assert ready["seconds"]["prepare"] == 0                                          # nada a preparar


def test_estimate_endpoint(client):
    pid = new_planned(client, "estimativa")
    e = client.get(f"/api/projects/{pid}/estimate").json()
    assert e["scenes"] >= 4 and {"plan", "prepare", "render", "total", "metadata", "thumbnail"} <= set(e["human"])


# --------------------------------------------------------------------- aviso de fim
def test_webhook_notification_on_job_end(client, monkeypatch):
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "NOTIFY_URL", f"http://127.0.0.1:{srv.server_port}/")
    pid = client.post("/api/projects", json={"title": "Avisos", "text": TEXT, "profile_id": "cyber-mistico"}).json()["id"]
    wait(client, client.post(f"/api/projects/{pid}/plan").json())
    t0 = time.time()
    while not got and time.time() - t0 < 10:
        time.sleep(0.1)
    srv.shutdown()
    assert got and got[0]["event"] == "job_done" and got[0]["project"] == "Avisos" and got[0]["job"] == "plan"
    assert set(got[0]) == {"event", "project", "job", "message", "seconds"}           # nada além do combinado


# ------------------------------------- workflows do ComfyUI contra o retrato da andes
NODES = json.loads((pathlib.Path(__file__).parent / "fixtures" / "comfy_nodes.json").read_text())


def validate_workflow(wf):
    for nid, node in wf.items():
        spec = NODES[node["class_type"]]                                             # KeyError = nó que não existe no ComfyUI da andes
        inputs = set(node["inputs"])
        assert set(spec["required"]) <= inputs, (nid, node["class_type"], set(spec["required"]) - inputs)
        assert inputs <= set(spec["required"]) | set(spec["optional"]), (nid, node["class_type"], inputs - set(spec["required"]) - set(spec["optional"]))
        for k, v in node["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in wf, f"{nid}.{k} aponta para o nó inexistente {v[0]}"


@pytest.mark.parametrize("build", [
    lambda: Comfy.flux_workflow("a prompt", {"base_model": "flux1-schnell-fp8", "params": {}}, 1, "p"),
    lambda: Comfy.ltx_workflow("img.png", "move", 768, 416, 97, "p"),
    lambda: Comfy.wan_workflow("img.png", "move", 960, 544, 97, "p"),
], ids=["flux", "ltx", "wan"])
def test_comfy_workflows_match_nodes_on_andes(build):
    validate_workflow(build())


# ------------------------------------------------------------ clipe curto sem loop
def make_clip(path, frames):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s=160x90:r={assemble.FPS}", "-frames:v", str(frames),
                        "-pix_fmt", "yuv420p", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_short_clip_continues_with_zoom_instead_of_looping(tmp_path):
    clip = tmp_path / "c.mp4"
    make_clip(clip, 48)                                      # clipe de 2 s
    out = tmp_path / "seg.mp4"
    assemble.clip_segment(str(clip), 120, str(out), fade=0)  # cena de 5 s
    assert assemble._clip_frames(str(out)) == 120
    # a parte final vem do zoom sobre o último quadro, não do começo do clipe: o quadro 100 difere do quadro 4
    for name, idx in (("a", 4), ("b", 100)):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf", f"select=eq(n\\,{idx}),scale=8:8,format=gray", "-frames:v", "1",
                        "-f", "rawvideo", str(tmp_path / f"{name}.raw")], check=True)
    assert (tmp_path / "a.raw").read_bytes() != (tmp_path / "b.raw").read_bytes()


def test_long_clip_is_trimmed_to_scene_length(tmp_path):
    clip = tmp_path / "c.mp4"
    make_clip(clip, 96)
    out = tmp_path / "seg.mp4"
    assemble.clip_segment(str(clip), 60, str(out), fade=0)
    assert assemble._clip_frames(str(out)) == 60
