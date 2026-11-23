"""YouTube: login (OAuth com PKCE), envio em pedaços, miniatura, métricas, fila e piloto automático, tudo contra um YouTube falso."""
import base64
import datetime as dt
import hashlib
import json
import os
import stat
import time
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, db, scheduler, youtube, youtube_jobs
from app.main import app


class FakeYouTube:
    """Responde como o YouTube e guarda o que recebeu."""

    def __init__(self):
        self.received = bytearray()
        self.init_body = None
        self.thumb = None
        self.fail_once = False
        self.fail_filter = False
        self.quota = False
        self.calls = []
        self.challenge = None
        self.ctr_ratio = True
        self.privacy_back = None      # o que o "YouTube" diz ter gravado (simula o bloqueio de projeto não auditado)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        u, q = str(req.url), dict(req.url.params)
        self.calls.append((req.method, req.url.path))
        if u.startswith(youtube.TOKEN_URL):
            f = dict(urllib.parse.parse_qsl(req.content.decode()))
            if f["grant_type"] == "authorization_code":
                digest = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                if self.challenge and digest != self.challenge:
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
                return httpx.Response(200, json={"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": " ".join(youtube.SCOPES)})
            return httpx.Response(200, json={"access_token": "at2", "expires_in": 3600})
        if u.startswith(youtube.REVOKE_URL):
            return httpx.Response(200)
        if self.quota and req.url.path.endswith("/videos") and req.method == "POST":
            return httpx.Response(403, json={"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}})
        if req.url.path.endswith("/youtube/v3/channels"):
            return httpx.Response(200, json={"items": [{"id": "UC123", "snippet": {"title": "Arcano Digital", "thumbnails": {"default": {"url": "http://x/t.jpg"}}},
                                                        "statistics": {"subscriberCount": "321", "viewCount": "9876", "videoCount": "7"}}]})
        if req.url.path.endswith("/upload/youtube/v3/videos"):
            self.init_body = json.loads(req.content)
            self.size = int(req.headers["x-upload-content-length"])
            return httpx.Response(200, headers={"Location": "https://upload.example/session1"})
        if u.startswith("https://upload.example/session1"):
            if self.fail_once and len(self.received) >= 256 * 1024:
                self.fail_once = False
                return httpx.Response(503)
            cr = req.headers["content-range"]
            if cr.startswith("bytes */"):
                return httpx.Response(308, headers={"Range": f"bytes=0-{len(self.received) - 1}"} if self.received else {})
            start, rest = cr.split(" ")[1].split("-")
            assert int(start) == len(self.received), "offset fora de ordem"
            self.received += req.content
            if len(self.received) >= self.size:
                return httpx.Response(200, json={"id": "VID123", "status": {"privacyStatus": self.privacy_back or self.init_body["status"]["privacyStatus"]}})
            return httpx.Response(308, headers={"Range": f"bytes=0-{len(self.received) - 1}"})
        if req.url.path.endswith("/thumbnails/set"):
            self.thumb = (q["videoId"], len(req.content))
            return httpx.Response(200, json={})
        if req.url.path.endswith("/youtube/v3/videos"):
            ids = q["id"].split(",")
            return httpx.Response(200, json={"items": [{"id": i, "snippet": {"title": f"Título {i}", "publishedAt": "2026-11-24T21:00:00Z"}, "status": {"privacyStatus": self.privacy_back or "public"},
                                                       "statistics": {"viewCount": "100", "likeCount": "9", "commentCount": "2"}} for i in ids]})
        if u.startswith(youtube.ANALYTICS):
            return self.analytics(q)
        return httpx.Response(404)

    def analytics(self, q):
        m, d, flt = q["metrics"], q.get("dimensions", ""), q.get("filters", "")
        if self.fail_filter and flt:
            return httpx.Response(400, json={"error": {"message": "filtro inválido", "errors": [{"reason": "badRequest"}]}})
        hdr = lambda *names: [{"name": n} for n in names]  # noqa: E731
        if d == "day":
            return httpx.Response(200, json={"columnHeaders": hdr("day", "views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"),
                                             "rows": [["2026-12-01", 10, 30.0, 2, 0], ["2026-12-02", 20, 60.0, 3, 1]]})
        if d == "video" and "videoThumbnailImpressions" in m:
            return httpx.Response(200, json={"columnHeaders": hdr("video", "videoThumbnailImpressions", "videoThumbnailImpressionsClickRate"),
                                             "rows": [["VID1", 1000, 0.052 if self.ctr_ratio else 5.2], ["VID2", 800, 0.021 if self.ctr_ratio else 2.1]]})
        if d == "video":
            return httpx.Response(200, json={"columnHeaders": hdr("video", "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "comments", "subscribersGained"),
                                             "rows": [["VID1", 500, 1500.0, 180.0, 42.0, 30, 5, 8], ["VID2", 300, 400.0, 80.0, 22.0, 4, 0, 1]]})
        if "creatorContentType==SHORTS" in flt:
            return httpx.Response(200, json={"columnHeaders": hdr("views"), "rows": [[12345]]})
        return httpx.Response(200, json={"columnHeaders": hdr("estimatedMinutesWatched", "views"), "rows": [[7200.0, 800]]})


@pytest.fixture()
def yt(tmp_path, monkeypatch):
    fake = FakeYouTube()
    monkeypatch.setattr(youtube, "TRANSPORT", httpx.MockTransport(fake))
    d = config.DATA / "youtube"
    for f in d.glob("*") if d.exists() else []:
        f.unlink()
    youtube.save_client("cid.apps.googleusercontent.com", "segredo")
    yield fake
    for f in (config.DATA / "youtube").glob("*"):
        f.unlink()


def connect(cid="c1"):
    youtube._save_tokens(cid, {"access_token": "at1", "refresh_token": "rt1", "expires_at": time.time() + 3000, "yt_channel_id": "UC123", "yt_title": "Arcano Digital"})


# ------------------------------------------------------------------ login
def test_oauth_pkce_flow_and_private_token_files(yt):
    url = youtube.auth_url("c1")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert q["redirect_uri"] == "http://127.0.0.1:8765" and q["access_type"] == "offline" and q["prompt"] == "consent" and q["code_challenge_method"] == "S256"
    assert "yt-analytics.readonly" in q["scope"] and "youtube.upload" in q["scope"]
    yt.challenge = q["code_challenge"]
    info = youtube.finish_auth("c1", f"http://127.0.0.1:8765/?state={q['state']}&code=4/abc&scope=x")
    assert info["title"] == "Arcano Digital" and info["subs"] == 321 and youtube.is_connected("c1")
    for name in ("client.json", "token_c1.json"):
        assert stat.S_IMODE(os.stat(config.DATA / "youtube" / name).st_mode) == 0o600           # só o dono lê
    assert not (config.DATA / "youtube" / "pending_c1.json").exists()


def test_oauth_errors_are_in_portuguese(yt):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(youtube.auth_url("c1")).query))
    with pytest.raises(youtube.YouTubeError, match="não autorizou"):
        youtube.finish_auth("c1", "http://127.0.0.1:8765/?error=access_denied")
    with pytest.raises(youtube.YouTubeError, match="outra tentativa"):
        youtube.finish_auth("c1", "http://127.0.0.1:8765/?state=errado&code=x")
    with pytest.raises(youtube.YouTubeError, match="Não achei o código"):
        youtube.finish_auth("c1", "http://127.0.0.1:8765/?state=" + q["state"])
    with pytest.raises(youtube.YouTubeError, match="expirou"):
        youtube.finish_auth("outro", "x")
    for f in (config.DATA / "youtube").glob("client.json"):
        f.unlink()
    with pytest.raises(youtube.YouTubeError, match="cadastre primeiro"):
        youtube.auth_url("c1")


def test_expired_access_token_is_refreshed(yt):
    youtube._save_tokens("c1", {"access_token": "velho", "refresh_token": "rt1", "expires_at": time.time() - 10})
    assert youtube.access_token("c1") == "at2" and youtube._tokens("c1")["access_token"] == "at2" and youtube._tokens("c1")["refresh_token"] == "rt1"
    youtube.disconnect("c1")
    assert not youtube.is_connected("c1")


# ------------------------------------------------------------------ envio
def test_upload_in_chunks_with_metadata_and_progress(yt, tmp_path, monkeypatch):
    connect()
    monkeypatch.setattr(youtube, "CHUNK", 256 * 1024)
    f = tmp_path / "v.mp4"
    f.write_bytes(os.urandom(700 * 1024))
    seen = []
    res = youtube.upload_video("c1", f, title="T" * 150, description="d", tags=["a", "b"], privacy="public", synthetic=True, progress=seen.append)
    assert res["id"] == "VID123" and bytes(yt.received) == f.read_bytes() and seen == sorted(seen) and seen[-1] == 1.0
    b = yt.init_body
    assert len(b["snippet"]["title"]) == 100 and b["status"]["privacyStatus"] == "public" and b["status"]["selfDeclaredMadeForKids"] is False and b["status"]["containsSyntheticMedia"] is True
    assert b["snippet"]["categoryId"] == "27" and b["snippet"]["defaultLanguage"] == "pt-BR" and "publishAt" not in b["status"]


def test_scheduled_upload_goes_private_with_publish_at_and_survives_a_server_error(yt, tmp_path, monkeypatch):
    connect()
    monkeypatch.setattr(youtube, "CHUNK", 256 * 1024)
    f = tmp_path / "v.mp4"
    f.write_bytes(os.urandom(600 * 1024))
    yt.fail_once = True
    res = youtube.upload_video("c1", f, title="x", description="", tags=[], privacy="public", publish_at="2026-12-01T21:00:00Z")
    assert res["id"] == "VID123" and bytes(yt.received) == f.read_bytes()                   # retomou do ponto certo depois do erro 503
    assert yt.init_body["status"]["privacyStatus"] == "private" and yt.init_body["status"]["publishAt"] == "2026-12-01T21:00:00Z"


def test_youtube_errors_are_explained(yt, tmp_path):
    connect()
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 100)
    yt.quota = True
    with pytest.raises(youtube.YouTubeError, match="cota diária"):
        youtube.upload_video("c1", f, title="x", description="", tags=[])
    with pytest.raises(youtube.YouTubeError, match="privacidade inválida"):
        youtube.upload_video("c1", f, title="x", description="", tags=[], privacy="segredo")


def test_rfc3339_conversion_from_brazil_time():
    assert youtube.to_rfc3339("2026-11-24T18:00") == "2026-11-24T21:00:00Z"
    assert youtube.to_rfc3339("2026-11-24T18:00:00-03:00", "UTC") == "2026-11-24T21:00:00Z"


def test_thumbnail_upload(yt, tmp_path):
    connect()
    img = tmp_path / "t.jpg"
    img.write_bytes(b"\xff\xd8" + b"0" * 5000)
    youtube.set_thumbnail("c1", "VID123", img)
    assert yt.thumb == ("VID123", 5002)


# ------------------------------------------------------------------ métricas
def test_snapshot_reads_series_hours_videos_and_normalizes_ctr(yt):
    connect()
    s = youtube.sync_snapshot("c1", today=dt.date(2026, 12, 3))
    assert s["canal"]["subs"] == 321 and s["horas_longos_365"] == 120.0 and s["horas_inclui_shorts"] is False and s["shorts_views_90d"] == 12345
    assert [r["inscritos_ganhos"] for r in s["serie_90d"]] == [2, 3] and s["avisos"] == []
    v = {x["id"]: x for x in s["videos"]}
    assert v["VID1"]["views"] == 500 and v["VID1"]["ctr"] == 5.2 and v["VID2"]["ctr"] == 2.1 and v["VID1"]["titulo"] == "Título VID1"      # CTR em proporção vira %
    yt.ctr_ratio = False
    assert {x["id"]: x["ctr"] for x in youtube.sync_snapshot("c1")["videos"]}["VID1"] == 5.2                                          # já em %: não multiplica


def test_snapshot_falls_back_when_the_long_form_filter_is_refused(yt):
    connect()
    yt.fail_filter = True
    s = youtube.sync_snapshot("c1")
    assert s["horas_inclui_shorts"] is True and s["horas_longos_365"] == 120.0 and s["shorts_views_90d"] is None
    assert any("só de vídeos longos" in a for a in s["avisos"])


def test_worst_videos_diagnosis():
    vids = [{"id": "a", "titulo": "A", "views": 500, "ctr": 2.0, "assistido_pct": 40}, {"id": "b", "titulo": "B", "views": 300, "ctr": 6.0, "assistido_pct": 20},
            {"id": "c", "titulo": "C", "views": 200, "ctr": 7.0, "assistido_pct": 50}, {"id": "d", "titulo": "D", "views": 10, "ctr": 0.1, "assistido_pct": 5}]
    w = youtube.worst_videos(vids)
    assert [x["id"] for x in w] == ["a", "b", "c"] and "CTR baixo" in w[0]["diagnostico"] and "abertura" in w[1]["diagnostico"]   # 'd' tem poucas visitas para julgar


# ------------------------------------------------------------------ fila, API e piloto automático
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def wait(client, job, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job não terminou")


@pytest.fixture(scope="module")
def done_project(client):
    prof = client.get("/api/profiles").json()[0]["id"]
    cid = client.get("/api/channels").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do vídeo de teste para o YouTube." for i in range(1, 12))
    pid = client.post("/api/projects", json={"title": "Vídeo para o YouTube", "text": text, "profile_id": prof, "channel_id": cid, "plan_item": 1}).json()["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert wait(client, client.post(f"/api/projects/{pid}/metadata/generate").json())["status"] == "done"      # as regras do canal exigem título e descrição antes de enviar
    assert wait(client, client.post(f"/api/projects/{pid}/thumbnail/generate", json={"count": 1}).json())["status"] == "done"
    assert client.get(f"/api/projects/{pid}/checks").json()["pode_enviar"], client.get(f"/api/projects/{pid}/checks").json()["achados"]
    return {"pid": pid, "cid": cid}


def test_config_endpoint_never_returns_the_secret(client, yt):
    r = client.get("/api/youtube/config").json()
    assert r["configured"] is True and "segredo" not in json.dumps(r) and r["redirect_uri"] == "http://127.0.0.1:8765"
    assert client.put("/api/youtube/config", json={"client_id": " ", "client_secret": "x"}).status_code == 422
    assert client.put("/api/youtube/config", json={"client_id": "novo", "client_secret": "s2"}).json() == {"configured": True}
    assert "s2" not in client.get("/api/youtube/config").text


def test_connect_status_and_disconnect_via_api(client, yt, done_project):
    cid = done_project["cid"]
    s = client.get(f"/api/channels/{cid}/youtube").json()
    assert s["cliente_configurado"] and not s["conectado"] and s["snapshot"] is None and s["config"]["hora"] == "18:00"
    assert client.post(f"/api/channels/{cid}/youtube/sync").status_code == 409
    u = client.post(f"/api/channels/{cid}/youtube/auth-url").json()["url"]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(u).query))
    yt.challenge = q["code_challenge"]
    r = client.post(f"/api/channels/{cid}/youtube/auth-finish", json={"pasted": f"http://127.0.0.1:8765/?state={q['state']}&code=ok"}).json()
    assert r["conectado"] and r["canal"]["title"] == "Arcano Digital"
    assert client.get(f"/api/channels/{cid}/youtube").json()["conectado"] is True and "at1" not in client.get(f"/api/channels/{cid}/youtube").text
    assert client.delete(f"/api/channels/{cid}/youtube").status_code == 204
    assert client.get(f"/api/channels/{cid}/youtube").json()["conectado"] is False


def test_sync_job_saves_snapshot_and_a_metrics_row(client, yt, done_project):
    cid = done_project["cid"]
    youtube._save_tokens(cid, {"access_token": "at1", "refresh_token": "rt1", "expires_at": time.time() + 3000, "yt_channel_id": "UC123", "yt_title": "Arcano Digital"})
    j = wait(client, client.post(f"/api/channels/{cid}/youtube/sync").json())
    assert j["status"] == "done" and j["result"]["inscritos"] == 321 and j["result"]["horas_longos_365"] == 120.0
    s = client.get(f"/api/channels/{cid}/youtube").json()
    assert s["snapshot"]["canal"]["subs"] == 321 and s["ypp"]["horas_meta"] in (4000, 8000) and s["ypp"]["inscritos"] == 321 and len(s["piores"]) >= 1
    row = [m for m in client.get(f"/api/channels/{cid}").json()["metricas"] if m["note"].startswith("YouTube")]
    assert len(row) == 1 and row[0]["subs"] == 321 and row[0]["hours"] == 120.0
    wait(client, client.post(f"/api/channels/{cid}/youtube/sync").json())                       # de novo no mesmo dia: substitui, não duplica
    assert len([m for m in client.get(f"/api/channels/{cid}").json()["metricas"] if m["note"].startswith("YouTube")]) == 1


def test_upload_job_validation_thumbnail_link_and_duplicates(client, yt, done_project):
    pid, cid = done_project["pid"], done_project["cid"]
    for f in (config.DATA / "youtube").glob("token_*"):
        f.unlink()
    assert client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "privado"}).status_code == 409          # não conectado
    connect(cid)
    assert client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "xyz"}).status_code == 422
    past = wait(client, client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "agendado", "publish_at": "2020-01-01T10:00"}).json())
    assert past["status"] == "failed" and "20 minutos no futuro" in past["message"]
    soon = (dt.datetime.now() + dt.timedelta(days=3)).strftime("%Y-%m-%dT18:00")
    ok = wait(client, client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "agendado", "publish_at": soon, "conteudo_sintetico": True}).json())
    assert ok["status"] == "done" and ok["result"]["video_id"] == "VID123" and ok["result"]["url"] == "https://youtu.be/VID123"
    assert yt.init_body["status"]["privacyStatus"] == "private" and "publishAt" in yt.init_body["status"] and yt.init_body["status"]["containsSyntheticMedia"] is True
    assert yt.thumb and yt.thumb[0] == "VID123"                                                 # a miniatura escolhida foi junto
    rows = client.get(f"/api/projects/{pid}/youtube").json()["envios"]
    assert rows[0]["status"] == "enviado" and rows[0]["video_id"] == "VID123" and rows[0]["warning"]
    item = next(v for v in client.get(f"/api/channels/{cid}").json()["videos"] if v["project_id"] == pid)
    assert item["youtube"]["url"] == "https://youtu.be/VID123" and item["status"] in ("pronto", "publicado")
    assert client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "privado"}).status_code == 409          # já enviado


def test_private_lock_of_unaudited_projects_is_reported(client, yt, done_project):
    pid, cid = done_project["pid"], done_project["cid"]
    connect(cid)
    for u in db.yt_uploads(project_id=pid):
        db.yt_upload_update(u["id"], status="erro")
    yt.privacy_back = "private"                                                                   # o YouTube grava privado, mesmo pedindo público
    j = wait(client, client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "publico"}).json())
    assert j["status"] == "done" and "não auditados" in j["result"]["aviso"]


def test_upload_failure_is_recorded_without_touching_the_project_status(client, yt, done_project):
    pid, cid = done_project["pid"], done_project["cid"]
    connect(cid)
    for u in db.yt_uploads(project_id=pid):
        db.yt_upload_update(u["id"], status="erro")
    yt.quota = True
    j = wait(client, client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "privado"}).json())
    assert j["status"] == "failed" and "cota diária" in j["message"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "done"
    assert db.yt_uploads(project_id=pid)[0]["status"] == "erro" and "cota" in db.yt_uploads(project_id=pid)[0]["error"]


def test_due_uploads_picks_ready_unsent_videos_with_schedule_rules():
    now = dt.datetime(2026, 12, 1, 12, 0, tzinfo=dt.timezone.utc)
    cfg = {**youtube_jobs.channel_plan.YT_DEFAULT, "envio_automatico": True}
    mk = lambda n, data, st="done", s="planejado": {"n": n, "titulo": f"V{n}", "data": data, "status": s, "projeto": {"id": f"p{n}", "status": st}}  # noqa: E731
    view = {"videos": [mk(1, "2026-12-08"), mk(2, "2026-11-30"), mk(3, "2026-12-09", st="draft"), mk(4, "2026-12-10", s="publicado"), mk(5, "2026-12-11"), mk(6, "2026-12-12"),
                       {"n": 7, "titulo": "sem projeto", "data": "2026-12-13", "status": "planejado", "projeto": None}]}
    uploads = [{"project_id": "p5", "status": "enviado"}, {"project_id": "p6", "status": "erro"}, {"project_id": "p6", "status": "erro"}, {"project_id": "p6", "status": "erro"}]
    todo = {t["project_id"]: t for t in youtube_jobs.due_uploads(view, uploads, cfg, now)}
    assert set(todo) == {"p1", "p2"}                                                          # p3 não está pronto, p4 já publicado, p5 já enviado, p6 falhou 3 vezes, p7 sem vídeo
    assert todo["p1"]["privacidade"] == "agendado" and todo["p1"]["publish_at"] == "2026-12-08T18:00"
    assert todo["p2"]["privacidade"] == "privado" and "já passou" in todo["p2"]["aviso"]        # a data passou: vai privado para você publicar
    assert youtube_jobs.due_uploads(view, uploads, {**cfg, "privacidade": "publico"}, now)[0]["privacidade"] == "publico"


def test_autopilot_queues_a_sync_first_then_one_upload_and_respects_throttle(client, yt, done_project, monkeypatch):
    pid, cid = done_project["pid"], done_project["cid"]
    connect(cid)
    with db._lock:
        db._c().execute("DELETE FROM youtube_uploads WHERE project_id=?", (pid,))
        db._c().execute("DELETE FROM youtube_snapshots WHERE channel_id=?", (cid,))
        db._c().commit()
    plan = db.channel_get(cid)["plan"]
    plan["youtube_config"] = {**plan.get("youtube_config", {}), "envio_automatico": True, "privacidade": "privado"}
    db.channel_update(cid, plan=plan)
    calls = []
    monkeypatch.setattr(db, "job_create", lambda kind, project_id, payload=None: calls.append((kind, project_id, payload)) or {"id": "x"})
    youtube_jobs._last["auto"] = 0
    youtube_jobs.tick(1000.0)
    assert calls == [("youtube_sync", None, {"channel_id": cid})]                         # sem números ainda: primeiro lê o canal
    db.snapshot_save(cid, {"taken": 1000.0, "canal": {"subs": 1}, "videos": []})
    calls.clear()
    youtube_jobs.tick(1100.0)                                                             # menos de 5 minutos depois: não faz nada
    assert calls == []
    youtube_jobs.tick(1400.0)
    assert [c[0] for c in calls] == ["youtube_upload"] and calls[0][1] == pid and calls[0][2]["privacidade"] == "privado" and calls[0][2]["item_n"] == 1
    calls.clear()
    monkeypatch.setattr(db, "active_jobs", lambda: [{"kind": "youtube_upload", "project_id": "outro", "payload": {}}])
    youtube_jobs.tick(2000.0)
    assert calls == []                                                                    # já há um envio na fila: um de cada vez
    plan["youtube_config"]["envio_automatico"] = False
    db.channel_update(cid, plan=plan)
    monkeypatch.undo()
    youtube_jobs._last["auto"] = 0
    calls2 = []
    monkeypatch.setattr(db, "job_create", lambda kind, project_id, payload=None: calls2.append(kind) or {"id": "x"})
    youtube_jobs.tick(3000.0)
    assert calls2 == []                                                                   # envio automático desligado: só lê números, e eles são recentes
