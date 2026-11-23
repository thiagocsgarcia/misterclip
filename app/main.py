"""API HTTP do MisterClip (FastAPI) + interface web estática."""
import contextlib
import datetime as dt
import hmac
import json
import pathlib
import random
import re
import shutil
import subprocess
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import idea_scripts, mailer, script_draft, channel_content_c, channel_plan, channel_rules, channels, youtube, youtube_jobs, config, db, estimate, metadata, profiles, scheduler, sceneops, scenes as scn, shorts as shorts_mod, shorts_plan, thumbnail, worker
from .pipeline import engine
from .pipeline.engine import project_dir, recover_stuck, scene_key, settle_status


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    recover_stuck()  # projetos que ficaram presos por um reinício no meio de um job
    worker.start()
    scheduler.start()
    yield
    scheduler.stop()
    worker.stop()


app = FastAPI(title="MisterClip", lifespan=lifespan)


# ------------------------------------------------------------------ auth
PUBLIC_PATHS = {"/api/health", "/api/auth/send-token"}


@app.middleware("http")
async def auth(request: Request, call_next):
    if config.TOKEN and (request.url.path.startswith("/api") or request.url.path.startswith("/media")) and request.url.path not in PUBLIC_PATHS:
        sent = request.cookies.get("mc_token") or request.query_params.get("token") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(sent.encode(), config.TOKEN.encode()):
            return JSONResponse({"detail": "não autorizado"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Arquivos da interface mudam a cada atualização: o navegador deve conferir se há versão nova (barato, via ETag)."""
    resp = await call_next(request)
    path = request.url.path
    if not path.startswith(("/api", "/media", "/previews")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.post("/api/auth/send-token")
def auth_send_token():
    """Tela de login: "Enviar o token para o meu e-mail". Sem autenticação por definição; só manda ao e-mail do dono configurado no servidor."""
    if not config.TOKEN:
        raise HTTPException(409, "este servidor não usa senha de acesso")
    try:
        r = mailer.send_token()
    except mailer.MailError as e:
        print("falha ao enviar o token por e-mail:", e)     # o motivo fica só no log do servidor
        raise HTTPException(502, "não foi possível enviar o e-mail agora; confira o servidor de e-mail da andes")
    if r == "unconfigured":
        raise HTTPException(503, "o envio por e-mail ainda não foi configurado no servidor (MC_TOKEN_EMAIL e MC_SMTP_*)")
    if r == "limited":
        raise HTTPException(429, "um e-mail já foi enviado há pouco; aguarde alguns minutos e olhe também o spam")
    return {"ok": True, "message": "Enviei o token para o e-mail cadastrado no servidor. Se não chegar em alguns minutos, olhe o spam."}


def _project(pid: str) -> dict:
    p = db.project_get(pid)
    if not p:
        raise HTTPException(404, "projeto não encontrado")
    return p


def _enqueue(kind: str, pid: str | None, payload: dict | None = None) -> dict:
    if pid and db.project_busy(pid):
        raise HTTPException(409, "este projeto já tem um job em andamento")
    return db.job_create(kind, pid, payload)


# ------------------------------------------------------------------ geral
@app.get("/api/health")
def health():
    return {"ok": True, "mode": config.MODE, "video_size": [config.VIDEO_W, config.VIDEO_H]}


@app.get("/api/config")
def get_config():
    return {"mode": config.MODE, "default_voice": config.DEFAULT_VOICE, "default_speed": config.DEFAULT_SPEED,
            "voices": VOICES, "video_size": [config.VIDEO_W, config.VIDEO_H]}


# ------------------------------------------------------------------ perfis
@app.get("/api/profiles")
def profiles_list():
    return profiles.list_profiles()


@app.post("/api/profiles", status_code=201)
def profiles_create(data: dict):
    try:
        return profiles.create(data)
    except profiles.ProfileError as e:
        raise HTTPException(422, str(e))


@app.put("/api/profiles/{pid}")
def profiles_update(pid: str, data: dict):
    try:
        return profiles.update(pid, data)
    except profiles.ProfileError as e:
        raise HTTPException(422, str(e))


@app.post("/api/profiles/{pid}/duplicate", status_code=201)
def profiles_duplicate(pid: str, data: dict | None = None):
    try:
        return profiles.duplicate(pid, (data or {}).get("name"))
    except profiles.ProfileError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/profiles/{pid}", status_code=204)
def profiles_delete(pid: str):
    try:
        profiles.delete(pid)
    except profiles.ProfileError as e:
        raise HTTPException(422, str(e))


class TestIn(BaseModel):
    text: str = "Um iniciado em uma câmara de pedra, diante de um livro selado, à luz de velas."


@app.post("/api/profiles/{pid}/test", status_code=202)
def profiles_test(pid: str, body: TestIn):
    if not profiles.get(pid):
        raise HTTPException(404, "perfil não encontrado")
    return db.job_create("profile_test", None, {"profile_id": pid, "text": body.text})


@app.get("/previews/{name}")
def preview(name: str):
    for base in (config.PROFILES_USER / "previews", config.PROFILES_BUILTIN / "previews"):
        f = base / pathlib.Path(name).name
        if f.is_file():
            return FileResponse(f)
    raise HTTPException(404)


@app.get("/media/profile_tests/{name}")
def profile_test_media(name: str):
    f = config.DATA / "profile_tests" / pathlib.Path(name).name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)



# ----------------------------------------------------- opções de vídeo / música
VOICES = ["pm_alex", "pm_santa", "pf_dora"]
TRANSITIONS = {"profile", "cut", "crossfade", "fade_black", "dissolve"}
MUSIC_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MUSIC_MAX_BYTES = 80 * 1024 * 1024


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _clean_options(o: dict) -> dict:
    t = o.get("transition", "profile")
    if t not in TRANSITIONS:
        raise HTTPException(422, f"transição inválida: {t}")
    try:
        seconds = _clamp(float(o.get("transition_seconds", 0.5)), 0.2, 2.0)
        m = o.get("music") or {}
        volume = _clamp(float(m.get("volume", 0.25)), 0.0, 1.0)
    except (TypeError, ValueError):
        raise HTTPException(422, "valor numérico inválido nas opções")
    fname = m.get("file") or None
    if fname and not (config.MUSIC_DIR / pathlib.Path(fname).name).is_file():
        raise HTTPException(422, "a música escolhida não existe mais")
    return {"transition": t, "transition_seconds": seconds,
            "music": {"file": pathlib.Path(fname).name if fname else None, "volume": volume, "duck": bool(m.get("duck", True))}}


def _audio_seconds(path: pathlib.Path) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return None


@app.get("/api/music")
def music_list():
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    return [{"name": f.name, "size": f.stat().st_size, "seconds": _audio_seconds(f)}
            for f in sorted(config.MUSIC_DIR.iterdir()) if f.suffix.lower() in MUSIC_EXT]


@app.post("/api/music", status_code=201)
async def music_upload(file: UploadFile = File(...)):
    name = re.sub(r"[^\w .()-]", "_", pathlib.Path(file.filename or "musica").name).strip() or "musica"
    if pathlib.Path(name).suffix.lower() not in MUSIC_EXT:
        raise HTTPException(422, f"formato não aceito (use {', '.join(sorted(MUSIC_EXT))})")
    config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.MUSIC_DIR / name
    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MUSIC_MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "arquivo maior que 80 MB")
            out.write(chunk)
    seconds = _audio_seconds(dest)
    if seconds is None:  # não é um áudio legível
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "o arquivo não parece ser um áudio válido")
    return {"name": name, "size": size, "seconds": seconds}


@app.delete("/api/music/{name}", status_code=204)
def music_delete(name: str):
    f = config.MUSIC_DIR / pathlib.Path(name).name
    if not f.is_file():
        raise HTTPException(404)
    f.unlink()


@app.get("/media/music/{name}")
def music_media(name: str):
    f = config.MUSIC_DIR / pathlib.Path(name).name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ---------------------------------------------------------------- projetos
class ProjectIn(BaseModel):
    title: str
    text: str
    profile_id: str | None = None      # em branco: o estilo padrão do canal (ou o primeiro estilo)
    voice: str | None = None           # em branco: a voz do canal
    speed: float | None = None         # em branco: a velocidade do canal
    channel_id: str | None = None
    plan_item: int | None = None


@app.get("/api/projects")
def projects_list():
    active = {x["project_id"]: x for x in db.schedules_list(200) if x["status"] in db.ACTIVE_SCHEDULE}
    out = db.project_list()
    running: dict[str, dict] = {}
    for j in db.active_jobs():
        if j["project_id"] and j["project_id"] not in running:
            running[j["project_id"]] = {"kind": j["kind"], "status": j["status"], "progress": j["progress"], "message": j["message"]}
    for p in out:
        sc = active.get(p["id"])
        p["schedule"] = {"run_at": sc["run_at"], "status": sc["status"]} if sc else None
        p["active_job"] = running.get(p["id"])
    return out


@app.post("/api/projects", status_code=201)
def projects_create(body: ProjectIn):
    ch = db.channel_get(body.channel_id) if body.channel_id else (db.channel_list() or [None])[0]
    rules = channel_rules.effective(ch)
    body.profile_id = body.profile_id or rules["visual"]["estilo_padrao"] or (profiles.list_profiles() or [{"id": ""}])[0]["id"]   # padrões vêm das regras do canal
    body.voice = body.voice or rules["narracao"]["voz"] or config.DEFAULT_VOICE
    body.speed = body.speed if body.speed is not None else (rules["narracao"]["velocidade"] or config.DEFAULT_SPEED)
    if not profiles.get(body.profile_id):
        raise HTTPException(422, "perfil inexistente")
    if not body.text.strip():
        raise HTTPException(422, "o roteiro está vazio")
    if body.channel_id and not db.channel_get(body.channel_id):
        raise HTTPException(422, "canal inexistente")
    p = db.project_create(body.title.strip() or "Sem título", body.text, body.profile_id, body.voice, body.speed, body.channel_id)
    v = rules["video"]                                                       # transição e música do canal já ficam nas opções do vídeo
    opts: dict = {"transition": v["transicao"]}
    if v["musica"]["arquivo"] and (config.MUSIC_DIR / pathlib.Path(v["musica"]["arquivo"]).name).is_file():
        opts["music"] = {"file": pathlib.Path(v["musica"]["arquivo"]).name, "volume": v["musica"]["volume"], "duck": v["musica"]["duck"]}
    p = db.project_update(p["id"], meta={**p["meta"], "options": {**(p["meta"].get("options") or {}), **opts}})
    if body.plan_item is not None:  # veio de um vídeo do calendário do canal: já fica ligado a ele
        ch = db.channel_get(p["channel_id"])
        item = next((v for v in ch["plan"].get("videos", []) if v["n"] == body.plan_item), None) if ch else None
        if item:
            item["project_id"] = p["id"]
            if item["status"] == "planejado":
                item["status"] = "roteiro"
            db.channel_update(ch["id"], plan=ch["plan"])
    return p


@app.get("/api/projects/{pid}")
def projects_get(pid: str, slim: bool = False):
    """`slim=1` tira os tempos por palavra (a maior parte do JSON): a interface não precisa deles."""
    p = _project(pid)
    p["jobs"] = db.jobs_for_project(pid, 5)
    p["busy"] = db.project_busy(pid)
    if slim:
        for s in p["scenes"]:
            s["has_words"] = bool(s.pop("words", None))
    return p


@app.get("/api/projects/{pid}/scenes-state")
def scenes_state(pid: str):
    """Estado minúsculo de cada cena para o roteiro ao vivo: [n, voz, tempos, imagem, animação, movimento]."""
    p = _project(pid)
    jobs = db.jobs_for_project(pid, 1)
    j = jobs[0] if jobs else None
    current = (j["stages"] or {}).get("current") if j and j["status"] in ("queued", "running", "cancelling") and j["stages"] else None
    return {"updated": p["updated"], "current": current,
            "scenes": [[s["n"], int(bool(s.get("audio") and not s["dirty_audio"])), int(bool(s.get("words"))),
                        int(bool(s.get("image") and not s["dirty_image"])), int(bool(s.get("clip"))), s["motion"]] for s in p["scenes"]]}


@app.post("/api/projects/{pid}/run-all", status_code=202)
def run_all(pid: str):
    """Prepara o que faltar e cria o vídeo, tudo sozinho no servidor: dá para fechar a página e até desligar o computador."""
    p = _project(pid)
    if not p["scenes"] and not p["text"].strip():
        raise HTTPException(422, "o roteiro está vazio")
    if db.project_busy(pid):
        raise HTTPException(409, "este vídeo já está ocupado com outra tarefa")
    cur = db.schedule_for_project(pid)
    if cur and cur["status"] == "running":
        raise HTTPException(409, "este vídeo já está sendo criado por um agendamento")
    sc = db.schedule_create(pid, time.time())  # vence agora: entra na fila e começa assim que a andes estiver livre
    scheduler.tick()
    return _schedule_view(db.schedule_get(sc["id"]))


@app.get("/api/projects/{pid}/status")
def projects_status(pid: str):
    """Resposta minúscula para o polling: a interface só busca o projeto inteiro quando algo mudou."""
    p = db.project_get(pid)
    if not p:
        raise HTTPException(404, "projeto não encontrado")
    jobs = db.jobs_for_project(pid, 1)
    j = jobs[0] if jobs else None
    sc = db.schedule_for_project(pid)
    return {"status": p["status"], "updated": p["updated"], "busy": db.project_busy(pid),
            "schedule": {k: sc[k] for k in ("id", "status", "run_at", "step", "message")} if sc and sc["status"] in db.ACTIVE_SCHEDULE else None,
            "job": {k: j[k] for k in ("id", "kind", "status", "progress", "message", "started", "stages")} if j else None}


@app.put("/api/projects/{pid}")
def projects_update(pid: str, data: dict):
    p = _project(pid)
    allowed = {k: data[k] for k in ("title", "text", "profile_id", "voice", "speed") if k in data}
    if "profile_id" in allowed and not profiles.get(allowed["profile_id"]):
        raise HTTPException(422, "perfil inexistente")
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    # mudar voz/velocidade invalida a narração; mudar o perfil invalida as imagens sem perfil próprio
    scenes = p["scenes"]
    meta = dict(p["meta"])
    if {"voice", "speed"} & allowed.keys() and (allowed.get("voice", p["voice"]) != p["voice"] or allowed.get("speed", p["speed"]) != p["speed"]):
        _mark_voice_change(p, scenes, meta, allowed)
    if "profile_id" in allowed and allowed["profile_id"] != p["profile_id"]:
        _mark_style_change(p, scenes, meta, allowed["profile_id"])
    if "options" in data:
        meta["options"] = _clean_options(data["options"] or {})
    return db.project_update(pid, scenes=scenes, meta=meta, **allowed)


def _mark_style_change(p: dict, scenes: list[dict], meta: dict, new: str) -> None:
    """Trocar o estilo marca as imagens como desatualizadas, mas registra a mudança para poder voltar atrás."""
    prev = meta.get("style_change") or {}
    origin = prev.get("from", p["profile_id"])
    marked = set(prev.get("scenes", []))
    for s in scenes:
        if s["profile_id"]:
            continue  # cenas com estilo próprio não dependem do estilo do vídeo
        if s.get("image") and s.get("image_profile") == new:
            if scene_key(s) in marked:
                s["dirty_image"] = False  # a imagem já foi feita nesse estilo
            continue
        if s.get("image") and not s["dirty_image"]:
            marked.add(scene_key(s))
        s["dirty_image"] = True
    if new == origin:  # voltou ao estilo original: só as imagens que continuam nele deixam de estar desatualizadas
        for s in scenes:
            if scene_key(s) in marked and s.get("image") and s.get("image_profile") in (None, origin):
                s["dirty_image"] = False
        meta.pop("style_change", None)
    else:
        meta["style_change"] = {"from": origin, "to": new, "scenes": sorted(marked), "at": time.time()}


def _mark_voice_change(p: dict, scenes: list[dict], meta: dict, allowed: dict) -> None:
    prev = meta.get("voice_change") or {}
    origin = {"voice": prev.get("from_voice", p["voice"]), "speed": prev.get("from_speed", p["speed"])}
    marked = set(prev.get("scenes", []))
    for s in scenes:
        if s.get("audio") and s.get("words") and not s["dirty_audio"]:
            marked.add(scene_key(s))
        s["dirty_audio"] = True
    new_voice, new_speed = allowed.get("voice", p["voice"]), allowed.get("speed", p["speed"])
    if (new_voice, new_speed) == (origin["voice"], origin["speed"]):  # voltou à voz original
        for s in scenes:
            if scene_key(s) in marked and s.get("audio") and s.get("words"):
                s["dirty_audio"] = False
        meta.pop("voice_change", None)
    else:
        meta["voice_change"] = {"from_voice": origin["voice"], "from_speed": origin["speed"], "scenes": sorted(marked), "at": time.time()}


def _restore_status(pid: str) -> dict:
    """Depois de aceitar/desfazer pendências: se nada mais falta, o vídeo volta a "pronto" (ou "revisar", se nunca foi criado)."""
    p = db.project_get(pid)
    if p["status"] == "planned" and settle_status(p) == "storyboard":
        has_video = bool(p["meta"].get("video")) and (project_dir(pid) / p["meta"]["video"]).is_file()
        p = db.project_update(pid, status="done" if has_video else "storyboard")
    return p


def _slim_project(p: dict) -> dict:
    p["busy"] = db.project_busy(p["id"])
    for s in p["scenes"]:
        s["has_words"] = bool(s.pop("words", None))
    return p


class KeepIn(BaseModel):
    kind: str = "image"          # image | audio
    scenes: list[int] | None = None


@app.post("/api/projects/{pid}/stale/keep")
def stale_keep(pid: str, body: KeepIn):
    """"Manter como está": aceita as imagens (ou narrações) atuais, sem gerar nada de novo."""
    p = _project(pid)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    if body.kind not in ("image", "audio"):
        raise HTTPException(422, "tipo inválido")
    flag, asset = ("dirty_image", "image") if body.kind == "image" else ("dirty_audio", "audio")
    for s in p["scenes"]:
        if (body.scenes is None or s["n"] in body.scenes) and s[flag] and s.get(asset) and (body.kind == "image" or s.get("words")):
            s[flag] = False
    meta = dict(p["meta"])
    key = "style_change" if body.kind == "image" else "voice_change"
    if body.scenes is None:
        meta.pop(key, None)
    db.project_update(pid, scenes=p["scenes"], meta=meta)
    return _slim_project(_restore_status(pid))


class StyleRevert(BaseModel):
    profile_id: str


@app.post("/api/projects/{pid}/style/revert")
def style_revert(pid: str, body: StyleRevert):
    """Volta o estilo do vídeo para `profile_id` e aceita as imagens atuais (que foram feitas nesse estilo)."""
    p = _project(pid)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    if not profiles.get(body.profile_id):
        raise HTTPException(422, "estilo inexistente")
    for s in p["scenes"]:
        if not s["profile_id"] and s.get("image") and s["dirty_image"]:
            s["dirty_image"] = False
    meta = {k: v for k, v in p["meta"].items() if k != "style_change"}
    db.project_update(pid, scenes=p["scenes"], meta=meta, profile_id=body.profile_id)
    return _slim_project(_restore_status(pid))


class VoiceRevert(BaseModel):
    voice: str
    speed: float


@app.post("/api/projects/{pid}/voice/revert")
def voice_revert(pid: str, body: VoiceRevert):
    p = _project(pid)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    if body.voice not in VOICES:
        raise HTTPException(422, "voz desconhecida")
    for s in p["scenes"]:
        if s["dirty_audio"] and s.get("audio") and s.get("words"):
            s["dirty_audio"] = False
    meta = {k: v for k, v in p["meta"].items() if k != "voice_change"}
    db.project_update(pid, scenes=p["scenes"], meta=meta, voice=body.voice, speed=round(_clamp(body.speed, 0.6, 1.3), 2))
    return _slim_project(_restore_status(pid))


@app.delete("/api/projects/{pid}", status_code=204)
def projects_delete(pid: str):
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    db.project_delete(pid)
    import shutil

    shutil.rmtree(config.DATA / "projects" / pid, ignore_errors=True)


@app.patch("/api/projects/{pid}/scenes/{n}")
def scene_patch(pid: str, n: int, data: dict):
    p = _project(pid)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    s = next((x for x in p["scenes"] if x["n"] == n), None)
    if s is None:
        raise HTTPException(404, "cena não encontrada")
    if "text" in data and data["text"].strip() != s["text"]:
        if p["meta"].get("kind") == "clip":  # letra da cena: não há narração para refazer
            s.update(text=data["text"].strip())
        else:
            s.update(text=data["text"].strip(), est_seconds=scn.est_seconds(data["text"]), dirty_audio=True, words=None)
    for k in ("visual_prompt", "profile_id", "seed"):
        if k in data and data[k] != s[k]:
            if k == "profile_id" and data[k] and not profiles.get(data[k]):
                raise HTTPException(422, "perfil inexistente")
            s[k] = data[k] or None if k == "profile_id" else data[k]
            s["dirty_image"] = True
    if "pause" in data:  # silêncio depois da fala desta cena: muda o ritmo e o tamanho do vídeo (o vídeo precisa ser montado de novo)
        try:
            val = None if data["pause"] in (None, "") else float(data["pause"])
        except (TypeError, ValueError):
            raise HTTPException(422, "pausa inválida")
        if val is not None and not 0 <= val <= 3:
            raise HTTPException(422, "a pausa vai de 0 a 3 segundos")
        before = s.get("duration")
        engine.set_pause(s, val)
        if s.get("duration") != before and p["meta"].get("video"):
            db.project_update(pid, meta={**p["meta"], "render_stale": True})
    if data.get("redo_clip"):  # animação ruim: apaga o clipe e sorteia outra semente; ao criar o vídeo de novo só esta cena é animada outra vez
        s["clip"], s["clip_seed"] = None, random.randint(1, 2**31 - 1)
        s.pop("clip_error", None)
    if "motion" in data:
        if data["motion"] not in ("ken_burns", "ltx", "wan"):
            raise HTTPException(422, "motion inválido")
        if data["motion"] != s["motion"]:
            s["motion"], s["clip"] = data["motion"], None
    db.project_update(pid, scenes=p["scenes"])
    return s


# ----------------------------------------------------------- operações de cena
def _scene_op(pid: str, fn):
    p = _project(pid)
    if p["meta"].get("kind") == "clip":
        raise HTTPException(409, "no clipe musical as cenas seguem o ritmo da música: edite a imagem e o movimento de cada cena")
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    items = p["scenes"]
    try:
        removed = fn(items) or []
    except sceneops.OpError as e:
        raise HTTPException(422, str(e))
    base = project_dir(pid)
    for rel in removed:  # arquivos que deixaram de ser usados
        (base / rel).unlink(missing_ok=True)
    p = db.project_update(pid, scenes=items)
    p = db.project_update(pid, status=settle_status(p))
    p["busy"] = False
    for s in p["scenes"]:
        s["has_words"] = bool(s.pop("words", None))
    return p


class AddScene(BaseModel):
    after: int = 0
    text: str


class SplitScene(BaseModel):
    at: int


@app.post("/api/projects/{pid}/scenes", status_code=201)
def scene_add(pid: str, body: AddScene):
    return _scene_op(pid, lambda items: sceneops.add(items, body.after, body.text))


@app.delete("/api/projects/{pid}/scenes/{n}")
def scene_delete(pid: str, n: int):
    return _scene_op(pid, lambda items: sceneops.delete(items, n))


@app.post("/api/projects/{pid}/scenes/{n}/merge")
def scene_merge(pid: str, n: int):
    return _scene_op(pid, lambda items: sceneops.merge_next(items, n))


@app.post("/api/projects/{pid}/scenes/{n}/split")
def scene_split(pid: str, n: int, body: SplitScene):
    return _scene_op(pid, lambda items: sceneops.split(items, n, body.at))


class VoiceSampleIn(BaseModel):
    voice: str = config.DEFAULT_VOICE
    speed: float = config.DEFAULT_SPEED


@app.post("/api/voice-sample", status_code=202)
def voice_sample(body: VoiceSampleIn):
    if body.voice not in VOICES:
        raise HTTPException(422, "voz desconhecida")
    return db.job_create("voice_sample", None, {"voice": body.voice, "speed": round(_clamp(body.speed, 0.6, 1.3), 2)})


@app.get("/media/voice_samples/{name}")
def voice_sample_media(name: str):
    f = config.DATA / "voice_samples" / pathlib.Path(name).name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ------------------------------------------------------------ agendamentos
class ScheduleIn(BaseModel):
    run_at: float | str  # epoch em segundos, ou ISO 8601 com fuso (ex.: 2026-11-22T02:00:00-03:00)


def _parse_run_at(v) -> float:
    if isinstance(v, (int, float)):
        ts = float(v)
    else:
        try:
            d = dt.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "data/hora inválida")
        if d.tzinfo is None:
            raise HTTPException(422, "inclua o fuso horário na data/hora (ex.: -03:00)")
        ts = d.timestamp()
    now = time.time()
    if ts < now + 10:
        raise HTTPException(422, "escolha um horário no futuro")
    if ts > now + scheduler.MAX_HORIZON_SECONDS:
        raise HTTPException(422, "o horário está longe demais (máximo de 1 ano)")
    return ts


def _schedule_view(sc: dict) -> dict:
    p = db.project_get(sc["project_id"])
    out = {**sc, "project_title": p["title"] if p else None, "eta_seconds": None}
    if p and sc["status"] in db.ACTIVE_SCHEDULE:
        sec = estimate.for_project(p)["seconds"]
        out["eta_seconds"] = sec["prepare"] + sec["render"]
    return out


@app.get("/api/schedules")
def schedules_all():
    return [_schedule_view(x) for x in db.schedules_list(100)]


@app.get("/api/projects/{pid}/schedule")
def schedule_get(pid: str):
    _project(pid)
    sc = db.schedule_for_project(pid)
    return _schedule_view(sc) if sc else None


@app.put("/api/projects/{pid}/schedule")
def schedule_put(pid: str, body: ScheduleIn):
    p = _project(pid)
    if not p["scenes"]:
        raise HTTPException(422, "planeje as cenas do projeto antes de agendar")
    current = db.schedule_for_project(pid)
    if current and current["status"] == "running":
        raise HTTPException(409, "este projeto já está sendo renderizado por um agendamento")
    return _schedule_view(db.schedule_create(pid, _parse_run_at(body.run_at)))


@app.delete("/api/projects/{pid}/schedule")
def schedule_delete(pid: str):
    _project(pid)
    sc = db.schedule_for_project(pid)
    if not sc or sc["status"] not in db.ACTIVE_SCHEDULE:
        raise HTTPException(404, "não há agendamento ativo neste projeto")
    return _schedule_view(scheduler.cancel(sc))


# ------------------------------------------------- publicação (título, descrição, tags, miniatura)
def _publish_view(p: dict) -> dict:
    yt = p["meta"].get("youtube")
    out = {"youtube": None, "description_final": None, "chapters_resolved": [], "thumbnail": p["meta"].get("thumbnail"),
           "estimate": estimate.for_project(p)["human"]}
    if yt:
        out["youtube"] = yt
        out["description_final"] = metadata.final_description(yt, p["scenes"], channel_rules.editorial_footer(db.channel_get(p.get("channel_id") or "")))
        starts, _ = metadata.timeline(p["scenes"])
        index = {metadata.scene_key(sc): i for i, sc in enumerate(p["scenes"])}
        rows = []
        for k, c in enumerate(yt.get("chapters", [])):
            i = index.get(c["scene"])
            t = 0 if k == 0 else (starts[i] if i is not None else None)
            rows.append({"scene": c["scene"], "title": c["title"], "t": metadata.fmt_ts(t) if t is not None else "—"})
        out["chapters_resolved"] = rows
        out["chapters_in_description"] = len(metadata.resolve_chapters(yt.get("chapters", []), p["scenes"])) >= 3
    return out


@app.get("/api/projects/{pid}/publish")
def publish_get(pid: str):
    return _publish_view(_project(pid))


@app.post("/api/projects/{pid}/metadata/generate", status_code=202)
def metadata_generate(pid: str):
    _project(pid)
    return _enqueue("metadata", pid)


@app.put("/api/projects/{pid}/metadata")
def metadata_put(pid: str, data: dict):
    p = _project(pid)
    yt = p["meta"].get("youtube")
    if not yt:
        raise HTTPException(409, "gere as sugestões antes de editar")
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    try:
        yt = metadata.apply_edit(yt, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _publish_view(db.project_update(pid, meta={**p["meta"], "youtube": yt}))


class ThumbGen(BaseModel):
    count: int = 3


class ThumbCompose(BaseModel):
    index: int
    text: str = ""


def _thumb_state(p: dict) -> dict:
    th = p["meta"].get("thumbnail")
    if not th:
        raise HTTPException(409, "gere as miniaturas primeiro")
    return th


class ShortsGen(BaseModel):
    count: int = 3
    layout: str = "blur"


@app.get("/api/projects/{pid}/shorts")
def shorts_get(pid: str):
    p = _project(pid)
    return {**(p["meta"].get("shorts") or {"items": [], "layout": "blur", "ver": 0}), "layouts": shorts_mod.LAYOUTS,
            "ready": p["status"] == "done"}


@app.post("/api/projects/{pid}/shorts/generate", status_code=202)
def shorts_generate(pid: str, body: ShortsGen):
    p = _project(pid)
    if p["status"] != "done":
        raise HTTPException(409, "termine o vídeo antes de criar os Shorts")
    if body.layout not in shorts_mod.LAYOUTS:
        raise HTTPException(422, "formato inválido")
    return _enqueue("shorts", pid, {"count": int(_clamp(body.count, 1, 5)), "layout": body.layout})


@app.get("/api/projects/{pid}/shorts/{i}/download")
def shorts_download(pid: str, i: int):
    p = _project(pid)
    it = next((x for x in (p["meta"].get("shorts") or {}).get("items", []) if x["i"] == i), None)
    f = project_dir(pid) / it["file"] if it else None
    if not f or not f.is_file():
        raise HTTPException(404, "Short não encontrado")
    name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p["title"]).strip() or "video"
    return FileResponse(f, media_type="video/mp4", filename=f"{name} - Short {i}.mp4")


@app.post("/api/projects/{pid}/thumbnail/generate", status_code=202)
def thumbnail_generate(pid: str, body: ThumbGen):
    _project(pid)
    return _enqueue("thumbnail", pid, {"count": int(_clamp(body.count, 1, 6))})


@app.post("/api/projects/{pid}/thumbnail/compose")
def thumbnail_compose(pid: str, body: ThumbCompose):
    p = _project(pid)
    th = _thumb_state(p)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    v = next((x for x in th["variants"] if x["i"] == body.index), None)
    if v is None:
        raise HTTPException(422, "miniatura inexistente")
    base = project_dir(pid) / v["base"]
    if not base.is_file():
        raise HTTPException(409, "a imagem base desta miniatura não existe mais; gere de novo")
    thumbnail.compose(str(base), body.text, str(project_dir(pid) / v["file"]))
    v["text"] = " ".join(body.text.split())[:40]
    th["ver"] = th.get("ver", 0) + 1
    return _publish_view(db.project_update(pid, meta={**p["meta"], "thumbnail": th}))


@app.post("/api/projects/{pid}/thumbnail/select")
def thumbnail_select(pid: str, body: ThumbCompose):
    p = _project(pid)
    th = _thumb_state(p)
    if not any(x["i"] == body.index for x in th["variants"]):
        raise HTTPException(422, "miniatura inexistente")
    th["selected"] = body.index
    return _publish_view(db.project_update(pid, meta={**p["meta"], "thumbnail": th}))


@app.get("/api/projects/{pid}/thumbnail/download")
def thumbnail_download(pid: str):
    p = _project(pid)
    th = _thumb_state(p)
    v = next(x for x in th["variants"] if x["i"] == th.get("selected", 1))
    f = project_dir(pid) / v["file"]
    if not f.is_file():
        raise HTTPException(404, "arquivo da miniatura não encontrado")
    name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p["title"]).strip() or "miniatura"
    return FileResponse(f, media_type="image/jpeg", filename=f"{name} - miniatura.jpg")


# ------------------------------------------------------------------ calendário
@app.get("/api/calendar")
def calendar_month(month: str):
    """Itens de um mês para o calendário: agendamentos (com horário estimado de término) e execuções manuais.

    A janela vai 2 dias além do mês nas duas pontas; quem separa por dia é o navegador (fuso do usuário)."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", month or "")
    if not m or not 1 <= int(m[2]) <= 12 or not 2020 <= int(m[1]) <= 2100:
        raise HTTPException(422, "mês inválido (use AAAA-MM)")
    y, mo = int(m[1]), int(m[2])
    utc = dt.timezone.utc
    first = dt.datetime(y, mo, 1, tzinfo=utc)
    nxt = dt.datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=utc)
    t0, t1 = (first - dt.timedelta(days=2)).timestamp(), (nxt + dt.timedelta(days=2)).timestamp()
    now = time.time()
    titles: dict[str, str | None] = {}
    etas: dict[str, float] = {}

    def title(pid: str) -> str | None:
        if pid not in titles:
            p = db.project_get(pid)
            titles[pid] = p["title"] if p else None
            if p:
                sec = estimate.for_project(p)["seconds"]
                etas[pid] = sec["prepare"] + sec["render"]
        return titles[pid]

    items = []
    for sc in db.schedules_between(t0, t1):
        t = title(sc["project_id"])
        active = sc["status"] in db.ACTIVE_SCHEDULE
        start = sc["started"] if sc["status"] == "running" and sc["started"] else sc["run_at"]
        end = start + etas.get(sc["project_id"], 0) if active else (sc["finished"] or start)
        items.append({"id": f"s:{sc['id']}", "origem": "agendamento", "tipo": "completo", "status": sc["status"], "project_id": sc["project_id"],
                      "project_title": t, "inicio": start, "fim": max(end, start + 60), "fim_estimado": active, "mensagem": sc["message"], "cancelavel": active})
    for j in db.jobs_between(("prepare", "render"), t0, t1):
        if (j["payload"] or {}).get("schedule"):
            continue  # já aparece como parte do agendamento
        start = j["started"] or j["created"]
        running = j["status"] in ("running", "cancelling")
        items.append({"id": f"j:{j['id']}", "origem": "manual", "tipo": "preparar" if j["kind"] == "prepare" else "renderizar",
                      "status": "running" if running else j["status"], "project_id": j["project_id"], "project_title": title(j["project_id"]) if j["project_id"] else None,
                      "inicio": start, "fim": max(now if running else (j["finished"] or start), start + 60), "fim_estimado": running,
                      "mensagem": j["message"] if j["status"] == "failed" else None, "cancelavel": False})
    items.sort(key=lambda x: x["inicio"])
    return {"month": month, "itens": items}


# ------------------------------------------------------------- pipeline
@app.post("/api/projects/{pid}/plan", status_code=202)
def project_plan(pid: str):
    _project(pid)
    return _enqueue("plan", pid)


@app.post("/api/projects/{pid}/prepare", status_code=202)
def project_prepare(pid: str):
    if not _project(pid)["scenes"]:
        raise HTTPException(409, "planeje as cenas primeiro")
    return _enqueue("prepare", pid)


class RegenIn(BaseModel):
    profile_id: str | None = None
    prompt: str | None = None
    new_seed: bool = True


@app.post("/api/projects/{pid}/scenes/{n}/regenerate", status_code=202)
def scene_regenerate(pid: str, n: int, body: RegenIn):
    p = _project(pid)
    if not any(s["n"] == n for s in p["scenes"]):
        raise HTTPException(404, "cena não encontrada")
    if body.profile_id and not profiles.get(body.profile_id):
        raise HTTPException(422, "perfil inexistente")
    return _enqueue("regen_image", pid, {"n": n, **body.model_dump(exclude_none=True)})


@app.post("/api/projects/{pid}/scenes/{n}/animate", status_code=202)
def scene_animate(pid: str, n: int):
    """Gera só a animação desta cena (depois de trocar a imagem, por exemplo). Para o vídeo final sair com ela, crie o vídeo de novo."""
    p = _project(pid)
    s = next((x for x in p["scenes"] if x["n"] == n), None)
    if not s:
        raise HTTPException(404, "cena não encontrada")
    if not s.get("image") or s.get("dirty_image"):
        raise HTTPException(409, "gere a imagem desta cena antes de animar")
    if s["motion"] not in ("ltx", "wan"):
        raise HTTPException(409, "esta cena usa zoom suave; escolha uma animação no efeito da imagem")
    return _enqueue("scene_clip", pid, {"n": n})


class CaptionLine(BaseModel):
    start: float
    end: float
    text: str


class CaptionsIn(BaseModel):
    items: list[CaptionLine]


@app.get("/api/projects/{pid}/captions")
def captions_get(pid: str):
    """Linhas de legenda do vídeo (as editadas à mão, se valem, ou as automáticas)."""
    p = _project(pid)
    st = engine.caption_state(p)
    return {"items": [{"start": a, "end": b, "text": t} for a, b, t in st["events"]], "edited": st["edited"], "stale_edit": st["stale_edit"], "total": st["total"],
            "applied": bool(p["meta"].get("captions_applied")), "pode_aplicar": p["status"] == "done"}


@app.put("/api/projects/{pid}/captions")
def captions_put(pid: str, body: CaptionsIn):
    """Guarda as legendas editadas. Para o vídeo mostrá-las, use /captions/apply (só legendas, leva segundos)."""
    p = _project(pid)
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    st = engine.caption_state(p)
    ev, last = [], 0.0
    if not body.items or len(body.items) > 3000:
        raise HTTPException(422, "informe de 1 a 3000 linhas de legenda")
    for i, it in enumerate(body.items, 1):
        text = " ".join(it.text.split())
        if not text:
            raise HTTPException(422, f"a linha {i} está vazia (apague a linha em vez de deixá-la em branco)")
        if len(text) > 160:
            raise HTTPException(422, f"a linha {i} tem {len(text)} letras; o máximo é 160")
        if not 0 <= it.start < it.end <= st["total"] + 1:
            raise HTTPException(422, f"a linha {i} tem tempo inválido (o vídeo dura {st['total']:.1f} s)")
        if it.start < last - 0.001:
            raise HTTPException(422, f"a linha {i} começa antes de a anterior terminar")
        ev.append([round(it.start, 2), round(it.end, 2), text])
        last = it.end
    meta = {**p["meta"], "captions_edit": {"events": ev, "total": st["total"], "n": len(p["scenes"]), "at": time.time()}}
    db.project_update(pid, meta=meta)
    return captions_get(pid)


@app.delete("/api/projects/{pid}/captions")
def captions_reset(pid: str):
    """Volta às legendas automáticas."""
    p = _project(pid)
    meta = {k: v for k, v in p["meta"].items() if k != "captions_edit"}
    db.project_update(pid, meta=meta)
    return captions_get(pid)


@app.post("/api/projects/{pid}/captions/apply", status_code=202)
def captions_apply(pid: str):
    p = _project(pid)
    if p["status"] != "done" or not (project_dir(pid) / "video_raw.mp4").is_file():
        raise HTTPException(409, "crie o vídeo antes de trocar as legendas")
    if p["meta"].get("render_stale"):
        raise HTTPException(409, "a duração das cenas mudou; crie o vídeo de novo (reaproveita as animações) e depois ajuste as legendas")
    return _enqueue("recaption", pid)


@app.post("/api/projects/{pid}/render", status_code=202)
def project_render(pid: str):
    p = _project(pid)
    if p["status"] not in ("storyboard", "done"):
        raise HTTPException(409, "gere a voz e as imagens e revise as cenas antes de criar o vídeo")
    stale = [s["n"] for s in p["scenes"] if s["dirty_image"] or s["dirty_audio"] or not s["image"] or not s["audio"]]
    if stale:  # recusa aqui: um job que falha depois rebaixaria o status do vídeo
        raise HTTPException(409, f"há imagens ou narrações desatualizadas (cenas {stale[:8]}{'…' if len(stale) > 8 else ''}). "
                                 "Escolha: voltar ao estilo/voz anterior, manter como está ou gerar de novo.")
    return _enqueue("render", pid)


@app.get("/api/jobs/{jid}")
def job_get(jid: str):
    j = db.job_get(jid)
    if not j:
        raise HTTPException(404)
    return j


@app.post("/api/jobs/{jid}/cancel", status_code=202)
def job_cancel(jid: str):
    j = db.job_get(jid)
    if not j:
        raise HTTPException(404)
    if j["status"] not in ("queued", "running"):
        raise HTTPException(409, f"o job já terminou ({j['status']})")
    return db.job_cancel(jid)


@app.post("/api/jobs/{jid}/retry", status_code=201)
def job_retry(jid: str):
    j = db.job_get(jid)
    if not j:
        raise HTTPException(404)
    if j["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, "só dá para tentar de novo um job que falhou ou foi cancelado")
    return _enqueue(j["kind"], j["project_id"], j["payload"])


@app.get("/api/projects/{pid}/estimate")
def project_estimate(pid: str):
    return estimate.for_project(_project(pid))


# ------------------------------------------------------------------ mídia
@app.get("/media/{pid}/{path:path}")
def media(pid: str, path: str):
    base = (config.DATA / "projects" / pathlib.Path(pid).name).resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404)
    # arquivos de cena são versionados pela interface (?v=); o MP4 final muda de conteúdo sob o mesmo nome
    cache = "no-store" if path == "final.mp4" else "private, max-age=3600"
    return FileResponse(f, headers={"Cache-Control": cache})


@app.get("/api/projects/{pid}/download")
def download(pid: str):
    p = _project(pid)
    f = project_dir(pid) / "final.mp4"
    if p["status"] != "done" or not f.is_file():
        raise HTTPException(404, "vídeo ainda não foi renderizado")
    name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p["title"]).strip() or "video"
    return FileResponse(f, media_type="video/mp4", filename=f"{name}.mp4")




# --------------------------------------------------------------------------- canais
class ChannelIn(BaseModel):
    name: str
    niche: str = ""
    template: str = channel_plan.TEMPLATE_ID  # "vazio" cria o canal sem calendário
    start_date: str | None = None


class ChannelEdit(BaseModel):
    name: str | None = None
    niche: str | None = None
    start_date: str | None = None


class MetricIn(BaseModel):
    day: str | None = None
    subs: int
    hours: float
    views: int = 0
    ctr: float | None = None
    avd: float | None = None
    note: str = ""


class VideoEdit(BaseModel):
    titulo: str | None = None
    status: str | None = None
    project_id: str | None = None
    unlink: bool = False
    nota: str | None = None


class VideoNew(BaseModel):
    titulo: str
    semana: int = 1
    dia: str = "ter"
    pilar: str = ""
    formato: str = "ensaio"


def _iso(day: str | None, field: str = "data") -> str:
    try:
        return dt.date.fromisoformat(day).isoformat() if day else dt.date.today().isoformat()
    except ValueError:
        raise HTTPException(422, f"{field} inválida (use AAAA-MM-DD)")


def _channel_or_404(cid: str) -> dict:
    ch = db.channel_get(cid)
    if not ch:
        raise HTTPException(404, "canal não encontrado")
    return ch


def _channel_view(ch: dict) -> dict:
    v = channels.view(ch, [p for p in db.project_list() if p.get("channel_id") == ch["id"]], db.metrics_list(ch["id"]))
    ideas = (v.get("plan") or {}).get("ideias")
    if ideas:   # marca cada ideia que já tem roteiro (o texto fica em arquivo, fora do plano)
        rules = channel_rules.effective(ch)
        idx = idea_scripts.index(ch["id"], lambda e: channel_rules.lint_script(channel_content_c.narracao_limpa(e.get("marcado", "")), rules, "ensaio")["achados"])
        v["plan"] = {**v["plan"], "ideias": [{**i, "roteiro": idx.get(i.get("n"))} for i in ideas]}
    return v


@app.get("/api/channels")
def channels_list():
    projs = db.project_list()
    out = []
    for ch in db.channel_list():
        v = channels.view(ch, [p for p in projs if p.get("channel_id") == ch["id"]], db.metrics_list(ch["id"]))
        h = v["hoje"]
        out.append({"id": ch["id"], "name": ch["name"], "niche": ch["niche"], "start_date": ch["start_date"],
                    "projetos": len(v["projetos"]), "dia": h["dia"], "semana": h["semana"], "horas": h["horas"], "inscritos": h["inscritos"],
                    "videos_publicados": h["videos_publicados"], "videos_total": h["videos_total"], "tem_plano": bool(v["videos"])})
    return out


@app.post("/api/channels", status_code=201)
def channels_create(body: ChannelIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "dê um nome ao canal")
    start = _iso(body.start_date, "data de início") if body.start_date else channel_plan.next_monday().isoformat()
    if body.template == channel_plan.TEMPLATE_ID:
        plan = channel_plan.build()
    elif body.template == "vazio":
        plan = channel_plan.skeleton()
    else:
        t = db.template_get(body.template)
        if not t:
            raise HTTPException(422, "modelo inexistente")
        plan = channel_plan.clone_plan(t["plan"])
    return db.channel_create(name[:80], body.niche.strip()[:200], start, plan)


@app.get("/api/channels/{cid}")
def channels_get(cid: str):
    return _channel_view(_channel_or_404(cid))


@app.put("/api/channels/{cid}")
def channels_edit(cid: str, body: ChannelEdit):
    _channel_or_404(cid)
    f: dict = {}
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(422, "o nome não pode ficar vazio")
        f["name"] = body.name.strip()[:80]
    if body.niche is not None:
        f["niche"] = body.niche.strip()[:200]
    if body.start_date is not None:
        f["start_date"] = _iso(body.start_date, "data de início")
    return _channel_view(db.channel_update(cid, **f) if f else db.channel_get(cid))


@app.delete("/api/channels/{cid}")
def channels_delete(cid: str):
    _channel_or_404(cid)
    if len(db.channel_list()) <= 1:
        raise HTTPException(409, "este é o único canal; crie outro antes de apagar")
    if any(p.get("channel_id") == cid for p in db.project_list()):
        raise HTTPException(409, "o canal ainda tem vídeos; mova-os para outro canal antes de apagar")
    db.channel_delete(cid)
    return {"ok": True}


@app.post("/api/channels/{cid}/metrics", status_code=201)
def channels_metric_add(cid: str, body: MetricIn):
    _channel_or_404(cid)
    if body.subs < 0 or body.hours < 0 or body.views < 0:
        raise HTTPException(422, "os números não podem ser negativos")
    for name, val, hi in (("CTR", body.ctr, 100), ("tempo médio assistido", body.avd, 100)):
        if val is not None and not 0 <= val <= hi:
            raise HTTPException(422, f"{name} deve ficar entre 0 e {hi}")
    return db.metric_add(cid, _iso(body.day, "data"), body.subs, body.hours, body.views, body.ctr, body.avd, body.note.strip()[:200])


@app.delete("/api/channels/{cid}/metrics/{mid}")
def channels_metric_delete(cid: str, mid: str):
    _channel_or_404(cid)
    db.metric_delete(cid, mid)
    return {"ok": True}


@app.patch("/api/channels/{cid}/videos/{n}")
def channels_video_edit(cid: str, n: int, body: VideoEdit):
    ch = _channel_or_404(cid)
    item = next((v for v in ch["plan"].get("videos", []) if v["n"] == n), None)
    if not item:
        raise HTTPException(404, "vídeo do calendário não encontrado")
    if body.titulo is not None:
        if not body.titulo.strip():
            raise HTTPException(422, "o título não pode ficar vazio")
        item["titulo"] = body.titulo.strip()[:150]
    if body.status is not None:
        if body.status not in channels.STATUS:
            raise HTTPException(422, "situação inválida")
        item["status"] = body.status
    if body.nota is not None:
        item["nota"] = body.nota.strip()[:500]
    if body.unlink:
        item["project_id"] = None
    elif body.project_id:
        p = db.project_get(body.project_id)
        if not p:
            raise HTTPException(422, "vídeo (projeto) inexistente")
        item["project_id"] = p["id"]
        if p.get("channel_id") != cid:
            db.project_update(p["id"], channel_id=cid)
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


@app.post("/api/channels/{cid}/videos", status_code=201)
def channels_video_add(cid: str, body: VideoNew):
    ch = _channel_or_404(cid)
    if not body.titulo.strip() or body.dia not in ("ter", "sex") or not 1 <= body.semana <= 13:
        raise HTTPException(422, "informe título, semana (1 a 13) e dia (ter ou sex)")
    vids = ch["plan"].setdefault("videos", [])
    vids.append({"n": max([v["n"] for v in vids] + [0]) + 1, "semana": body.semana, "dia": body.dia, "titulo": body.titulo.strip()[:150],
                 "pilar": body.pilar, "formato": body.formato, "serie": None, "status": "planejado", "project_id": None, "nota": ""})
    vids[-1]["shorts"] = shorts_plan.ideas_for(vids[-1])
    vids.sort(key=lambda v: (v["semana"], 0 if v["dia"] == "ter" else 1, v["n"]))
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


@app.delete("/api/channels/{cid}/videos/{n}")
def channels_video_delete(cid: str, n: int):
    ch = _channel_or_404(cid)
    ch["plan"]["videos"] = [v for v in ch["plan"].get("videos", []) if v["n"] != n]
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


class ProjectChannel(BaseModel):
    channel_id: str


@app.put("/api/projects/{pid}/channel")
def project_set_channel(pid: str, body: ProjectChannel):
    if not db.project_get(pid):
        raise HTTPException(404, "projeto não encontrado")
    _channel_or_404(body.channel_id)
    return db.project_update(pid, channel_id=body.channel_id)




# --------------------------------------------------------------------------- plano de Shorts do canal
class ShortEdit(BaseModel):
    dia: int | None = None        # dias depois da publicação do vídeo longo (0 a 14)
    agendar: bool | None = None   # False tira do calendário
    status: str | None = None
    nota: str | None = None
    gancho: str | None = None


def _find_short(ch: dict, n: int, sid: str):
    v = next((x for x in ch["plan"].get("videos", []) if x["n"] == n), None)
    if not v:
        raise HTTPException(404, "vídeo do calendário não encontrado")
    sh = next((x for x in v.get("shorts", []) if x["id"] == sid), None)
    if not sh:
        raise HTTPException(404, "ideia de Short não encontrada")
    return v, sh


@app.patch("/api/channels/{cid}/videos/{n}/shorts/{sid}")
def channels_short_edit(cid: str, n: int, sid: str, body: ShortEdit):
    ch = _channel_or_404(cid)
    _, sh = _find_short(ch, n, sid)
    if body.status is not None:
        if body.status not in channels.SHORT_STATUS:
            raise HTTPException(422, "situação inválida")
        sh["status"] = body.status
    if body.agendar is False:
        sh["dia"] = None
        if sh["status"] == "agendado":
            sh["status"] = "ideia"
    elif body.dia is not None:
        if not 0 <= body.dia <= 14:
            raise HTTPException(422, "escolha de 0 a 14 dias depois do vídeo longo")
        sh["dia"] = body.dia
        if sh["status"] == "ideia":
            sh["status"] = "agendado"
    if body.nota is not None:
        sh["nota"] = body.nota.strip()[:500]
    if body.gancho is not None:
        if not body.gancho.strip():
            raise HTTPException(422, "o gancho não pode ficar vazio")
        sh["gancho"] = " ".join(body.gancho.split())[:220]
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


@app.post("/api/channels/{cid}/videos/{n}/shorts/generate", status_code=202)
def channels_shorts_ideas(cid: str, n: int):
    """Pede ao LLM da andes ideias de Short escritas a partir do roteiro do vídeo (ou do título, se ainda não há roteiro)."""
    ch = _channel_or_404(cid)
    if not any(x["n"] == n for x in ch["plan"].get("videos", [])):
        raise HTTPException(404, "vídeo do calendário não encontrado")
    return db.job_create("shorts_ideas", None, {"channel_id": cid, "n": n})


class IdeaScriptsIn(BaseModel):
    ns: list[int] | None = None       # ideias pedidas; sem lista, as próximas ideias sem roteiro (por potencial)
    count: int = 5
    force: bool = False


IDEA_SCRIPTS_MAX = 10


@app.post("/api/channels/{cid}/ideas/scripts", status_code=202)
def channels_idea_scripts(cid: str, body: IdeaScriptsIn):
    """Escreve os roteiros (marcados, com o prompt de roteiro do playbook) de várias ideias, em fila, na andes. Cada roteiro fica salvo assim que sai."""
    ch = _channel_or_404(cid)
    ideas = ch["plan"].get("ideias", [])
    valid = {i["n"] for i in ideas}
    have = set(idea_scripts.index(cid))
    if body.ns:
        ns = [n for n in dict.fromkeys(body.ns) if n in valid]
        if not body.force:
            ns = [n for n in ns if n not in have]
    else:
        ns = [i["n"] for i in sorted(ideas, key=lambda x: -x.get("potencial", 0)) if i["n"] not in have and i.get("status") != "descartada"]
    ns = ns[:max(1, min(IDEA_SCRIPTS_MAX, body.count if not body.ns else IDEA_SCRIPTS_MAX))]
    if not ns:
        raise HTTPException(409, "nenhuma ideia precisa de roteiro (as pedidas já têm um)")
    if db.jobs_active("idea_scripts"):
        raise HTTPException(409, "já há roteiros sendo escritos; espere terminar ou cancele")
    return db.job_create("idea_scripts", None, {"channel_id": cid, "ns": ns, "force": body.force})


def _script_view(cid: str, n: int, e: dict) -> dict:
    rules = channel_rules.effective(db.channel_get(cid))
    narr = channel_content_c.narracao_limpa(e.get("marcado", ""))
    lint = channel_rules.lint_script(narr, rules, "ensaio")
    return {**e, "narracao": narr, "palavras": lint["palavras"], "minutos": lint["minutos"], "achados": lint["achados"], "conferir": idea_scripts.items(e, lint["achados"])}


@app.get("/api/channels/{cid}/ideas/{n}/script")
def channels_idea_script_get(cid: str, n: int):
    _channel_or_404(cid)
    e = idea_scripts.load(cid, n)
    if not e:
        raise HTTPException(404, "esta ideia ainda não tem roteiro")
    return _script_view(cid, n, e)


class ConferirIn(BaseModel):
    id: str
    feito: bool = True


@app.post("/api/channels/{cid}/ideas/{n}/conferir")
def channels_idea_conferir(cid: str, n: int, body: ConferirIn):
    """Marca (ou desmarca) um item de “o que conferir antes de gerar o vídeo” desta ideia."""
    _channel_or_404(cid)
    e = idea_scripts.load(cid, n)
    if not e:
        raise HTTPException(404, "esta ideia ainda não tem roteiro")
    view = _script_view(cid, n, e)
    if body.id not in {x["id"] for x in view["conferir"]}:
        raise HTTPException(404, "item não encontrado (o texto pode ter mudado; recarregue)")
    done = set(e.get("conferido") or [])
    (done.add if body.feito else done.discard)(body.id)
    e["conferido"] = sorted(done)
    return _script_view(cid, n, idea_scripts.save(cid, n, e))


class IdeaScriptIn(BaseModel):
    marcado: str
    revisado: bool = False        # tira a marca de rascunho
    notas: dict | None = None     # tese, fontes e incertezas de um roteiro escrito de fora (por exemplo pelo Claude)


@app.put("/api/channels/{cid}/ideas/{n}/script")
def channels_idea_script_put(cid: str, n: int, body: IdeaScriptIn):
    """Salva o roteiro editado por você. Um roteiro editado nunca é refeito pela IA sem `force`."""
    ch = _channel_or_404(cid)
    idea = next((i for i in ch["plan"].get("ideias", []) if i["n"] == n), None)
    if not idea:
        raise HTTPException(404, "ideia não encontrada")
    text = body.marcado.replace("\r\n", "\n").strip()
    if len(text.split()) < 30:
        raise HTTPException(422, "o roteiro está curto demais para salvar (menos de 30 palavras)")
    if len(text) > 120_000:
        raise HTTPException(422, "o roteiro passa de 120 mil letras")
    old = idea_scripts.load(cid, n) or {"titulo": idea["titulo"], "quebra_de_padrao_a_cada_s": 60}
    narr = channel_content_c.narracao_limpa(text)
    words = len(narr.split())
    e = {**old, "marcado": text, "palavras": words, "minutos": round(words / 125, 1), "duracao_min": round(words / 125, 1), "editado": True,
         "pontos_de_saida": script_draft.exit_points(text) or old.get("pontos_de_saida", [])}      # lidos das marcações [SAÍDA: risco | solução]
    if body.notas:
        nt = body.notas
        e["notas"] = {"tese": str(nt.get("tese", ""))[:600], "origem": str(nt.get("origem", ""))[:200],
                      "fontes": [str(x)[:300] for x in (nt.get("fontes") or [])][:30], "incertezas": [str(x)[:400] for x in (nt.get("incertezas") or [])][:30]}
    if body.revisado:
        e.pop("rascunho", None)
    return _script_view(cid, n, idea_scripts.save(cid, n, e))


class DraftIn(BaseModel):
    force: bool = False


@app.post("/api/channels/{cid}/videos/{n}/draft", status_code=202)
def channels_script_draft(cid: str, n: int, body: DraftIn | None = None):
    """Pede à andes um RASCUNHO de roteiro para um vídeo do calendário (esboço + seções, dentro das regras do canal). Nunca substitui um roteiro seu sem `force`."""
    ch = _channel_or_404(cid)
    if not any(x["n"] == n for x in ch["plan"].get("videos", [])):
        raise HTTPException(404, "vídeo do calendário não encontrado")
    old = next((r for r in ch["plan"].get("roteiros", []) if r.get("video_n") == n), None)
    force = bool(body and body.force)
    if old and not old.get("rascunho") and not force:
        raise HTTPException(409, "este vídeo já tem um roteiro; o rascunho não o substitui")
    if any((j.get("payload") or {}).get("channel_id") == cid for j in db.jobs_active("script_draft")):
        raise HTTPException(409, "já há um rascunho sendo escrito para este canal")
    return db.job_create("script_draft", None, {"channel_id": cid, "n": n, "force": force})


# --------------------------------------------------------------------------- clipe musical
CLIP_MAX_SECONDS = 600
CLIP_MIN_SECONDS = 20


@app.get("/api/clips/options")
def clip_options():
    from . import musicclip
    return {"ritmos": musicclip.RITMO_NOME, "animacoes": musicclip.ANIMACOES, "max_seconds": CLIP_MAX_SECONDS}


def _check_upload_id(uid: str) -> pathlib.Path:
    if not re.fullmatch(r"[0-9a-f]{12}", uid or ""):
        raise HTTPException(404, "música enviada não encontrada")
    d = config.CLIP_UPLOADS / uid
    if not d.is_dir():
        raise HTTPException(404, "a música enviada não está mais no servidor; envie de novo")
    return d


def _clean_old_uploads(max_age: float = 24 * 3600) -> None:
    if config.CLIP_UPLOADS.is_dir():
        for d in config.CLIP_UPLOADS.iterdir():
            if d.is_dir() and time.time() - d.stat().st_mtime > max_age:
                shutil.rmtree(d, ignore_errors=True)


@app.post("/api/clips/upload", status_code=201)
async def clips_upload(file: UploadFile = File(...)):
    """Recebe a música assim que ela é escolhida e já pede a transcrição da letra, para o usuário revisar antes de criar o clipe."""
    ext = pathlib.Path(file.filename or "musica").suffix.lower()
    if ext not in MUSIC_EXT:
        raise HTTPException(422, f"formato não aceito (use {', '.join(sorted(MUSIC_EXT))})")
    _clean_old_uploads()
    uid = uuid.uuid4().hex[:12]
    d = config.CLIP_UPLOADS / uid
    d.mkdir(parents=True, exist_ok=True)
    dest, size = d / f"song{ext}", 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MUSIC_MAX_BYTES:
                    raise HTTPException(413, "arquivo maior que 80 MB")
                out.write(chunk)
        seconds = _audio_seconds(dest)
        if seconds is None:
            raise HTTPException(422, "o arquivo não parece ser um áudio válido")
        if not CLIP_MIN_SECONDS <= seconds <= CLIP_MAX_SECONDS:
            raise HTTPException(422, f"a música deve ter entre {CLIP_MIN_SECONDS} segundos e {CLIP_MAX_SECONDS // 60} minutos")
    except HTTPException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    (d / "info.json").write_text(json.dumps({"arquivo": pathlib.Path(file.filename or "").name, "seconds": round(seconds, 1)}), encoding="utf-8")
    job = db.job_create("transcribe_lyrics", None, {"upload_id": uid})
    return {"upload_id": uid, "seconds": round(seconds, 1), "arquivo": pathlib.Path(file.filename or "").name, "job": job}


@app.post("/api/clips/upload/{uid}/transcribe", status_code=202)
def clips_retranscribe(uid: str):
    _check_upload_id(uid)
    return db.job_create("transcribe_lyrics", None, {"upload_id": uid})


@app.delete("/api/clips/upload/{uid}", status_code=204)
def clips_upload_delete(uid: str):
    d = _check_upload_id(uid)
    shutil.rmtree(d, ignore_errors=True)


@app.post("/api/clips", status_code=201)
async def clips_create(file: UploadFile | None = File(None), upload_id: str = Form(""), title: str = Form(""), lyrics: str = Form(""), concept: str = Form(""),
                       profile_id: str = Form(...), ritmo: str = Form("normal"), animacao: str = Form("total"), legendas: str = Form("true"), channel_id: str = Form("")):
    """Cria um clipe musical: a música enviada vira o áudio e a letra (ou o conceito) vira a história contada em imagens animadas."""
    from . import musicclip
    if not profiles.get(profile_id):
        raise HTTPException(422, "estilo visual inexistente")
    if ritmo not in musicclip.RITMOS or animacao not in musicclip.ANIMACOES:
        raise HTTPException(422, "escolha o ritmo dos cortes e o nível de animação")
    if not lyrics.strip() and not concept.strip():
        raise HTTPException(422, "conte a história da música: cole a letra ou descreva o que o clipe deve mostrar")
    if channel_id and not db.channel_get(channel_id):
        raise HTTPException(422, "canal inexistente")
    up_dir, up_info = None, {}
    if upload_id:
        up_dir = _check_upload_id(upload_id)
        try:
            up_info = json.loads((up_dir / "info.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            up_info = {}
        src = next((f for f in up_dir.glob("song.*")), None)
        if src is None:
            raise HTTPException(404, "a música enviada não está mais no servidor; envie de novo")
        ext, orig_name = src.suffix.lower(), up_info.get("arquivo") or src.name
    elif file is not None:
        ext, orig_name = pathlib.Path(file.filename or "musica").suffix.lower(), pathlib.Path(file.filename or "").name
        if ext not in MUSIC_EXT:
            raise HTTPException(422, f"formato não aceito (use {', '.join(sorted(MUSIC_EXT))})")
    else:
        raise HTTPException(422, "envie a música do clipe")
    p = db.project_create((title.strip() or pathlib.Path(orig_name or "Clipe").stem)[:120], lyrics.strip() or concept.strip(), profile_id,
                          config.DEFAULT_VOICE, config.DEFAULT_SPEED, channel_id or None)
    pid, d = p["id"], project_dir(p["id"])
    dest, size = d / f"song{ext}", 0
    try:
        if up_dir is not None:
            shutil.move(str(src), str(dest))
            shutil.rmtree(up_dir, ignore_errors=True)
        else:
            with open(dest, "wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MUSIC_MAX_BYTES:
                        raise HTTPException(413, "arquivo maior que 80 MB")
                    out.write(chunk)
        seconds = _audio_seconds(dest)
        if seconds is None:
            raise HTTPException(422, "o arquivo não parece ser um áudio válido")
        if not CLIP_MIN_SECONDS <= seconds <= CLIP_MAX_SECONDS:
            raise HTTPException(422, f"a música deve ter entre {CLIP_MIN_SECONDS} segundos e {CLIP_MAX_SECONDS // 60} minutos")
    except HTTPException:
        shutil.rmtree(d, ignore_errors=True)
        db.project_delete(pid)
        raise
    meta = {"kind": "clip", "options": {"transition": "cut"},
            "clip": {"audio": dest.name, "arquivo": orig_name, "seconds": round(seconds, 1), "ritmo": ritmo, "animacao": animacao,
                     "legendas": legendas.lower() in ("1", "true", "sim", "on"), "conceito": concept.strip(), "tem_letra": bool(lyrics.strip())}}
    return db.project_update(pid, meta=meta)


class LyricsIn(BaseModel):
    lyrics: str = ""
    concept: str | None = None


@app.put("/api/projects/{pid}/lyrics")
def clips_set_lyrics(pid: str, body: LyricsIn):
    """Muda a letra (ou o conceito) de um clipe. Para valer, é preciso planejar o clipe de novo."""
    p = _project(pid)
    if p["meta"].get("kind") != "clip":
        raise HTTPException(409, "só clipes musicais têm letra")
    if db.project_busy(pid):
        raise HTTPException(409, "projeto ocupado")
    concept = p["meta"]["clip"].get("conceito", "") if body.concept is None else body.concept.strip()
    if not body.lyrics.strip() and not concept:
        raise HTTPException(422, "a letra não pode ficar vazia sem uma descrição da história")
    clip = {**p["meta"]["clip"], "conceito": concept, "tem_letra": bool(body.lyrics.strip())}
    return db.project_update(pid, text=body.lyrics.strip() or concept, meta={**p["meta"], "clip": clip})


# --------------------------------------------------------------------------- planejamento editável, clonagem, modelos e prompts
class SectionIn(BaseModel):
    value: object


class ImportIn(BaseModel):
    sections: dict
    videos: list[dict] | None = None


class CloneIn(BaseModel):
    name: str
    niche: str | None = None
    start_date: str | None = None
    keep_videos: bool = True


class TemplateIn(BaseModel):
    name: str
    description: str = ""


MAX_SECTION_BYTES = 400_000


def _check_section(cur, new):
    """O tipo de uma seção não muda (objeto continua objeto, lista continua lista) e o tamanho tem limite."""
    if len(json.dumps(new, ensure_ascii=False)) > MAX_SECTION_BYTES:
        raise HTTPException(413, "a seção ficou grande demais")
    if cur is not None and type(cur) is not type(new) and not (isinstance(cur, (int, float)) and isinstance(new, (int, float))):
        raise HTTPException(422, "o formato da seção não pode mudar (texto, lista ou objeto)")


def _mark_edited(plan: dict, key: str) -> None:
    ed = plan.setdefault("_edited", [])
    if key not in ed:
        ed.append(key)


@app.put("/api/channels/{cid}/plan/{section}")
def channels_plan_section(cid: str, section: str, body: SectionIn):
    """Troca uma seção inteira do plano (posicionamento, pilares, ideias, revisão...). O que você edita não é sobrescrito nas atualizações do modelo."""
    ch = _channel_or_404(cid)
    if section in channel_plan.PROTECTED:
        raise HTTPException(422, "esta parte do plano tem edição própria (calendário e vídeos)")
    value = body.value
    if section == "ideias" and isinstance(value, list):
        value = [{k: x[k] for k in x if k != "roteiro"} if isinstance(x, dict) else x for x in value]   # o resumo do roteiro é só de leitura
    _check_section(ch["plan"].get(section), value)
    ch["plan"][section] = value
    _mark_edited(ch["plan"], section)
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


@app.post("/api/channels/{cid}/plan/import")
def channels_plan_import(cid: str, body: ImportIn):
    """Grava várias seções de uma vez (é o que o Claude usa ao executar um prompt da biblioteca) e, se vier, a lista de vídeos do calendário."""
    ch = _channel_or_404(cid)
    for k, v in body.sections.items():
        if k in channel_plan.PROTECTED:
            raise HTTPException(422, f"a seção '{k}' não pode ser importada por aqui")
        _check_section(ch["plan"].get(k), v)
    for k, v in body.sections.items():
        ch["plan"][k] = v
        _mark_edited(ch["plan"], k)
    if body.videos is not None:
        vids = []
        for i, v in enumerate(body.videos, start=1):
            if not str(v.get("titulo", "")).strip() or v.get("dia") not in ("ter", "sex") or not 1 <= int(v.get("semana", 0)) <= 13:
                raise HTTPException(422, f"vídeo {i}: informe titulo, semana (1 a 13) e dia (ter ou sex)")
            item = {"n": i, "semana": int(v["semana"]), "dia": v["dia"], "titulo": str(v["titulo"]).strip()[:150], "pilar": v.get("pilar", ""), "formato": v.get("formato", "ensaio"),
                    "serie": v.get("serie"), "status": "planejado", "project_id": None, "nota": ""}
            item["shorts"] = v.get("shorts") or shorts_plan.ideas_for(item)
            vids.append(item)
        ch["plan"]["videos"] = vids
    return _channel_view(db.channel_update(cid, plan=ch["plan"]))


@app.post("/api/channels/{cid}/clone", status_code=201)
def channels_clone(cid: str, body: CloneIn):
    """Cria outro canal com a mesma estrutura de planejamento (seções, calendário e ideias), sem vídeos, métricas nem ligação com projetos."""
    ch = _channel_or_404(cid)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "dê um nome ao novo canal")
    start = _iso(body.start_date, "data de início") if body.start_date else channel_plan.next_monday().isoformat()
    plan = channel_plan.clone_plan(ch["plan"], keep_videos=body.keep_videos)
    plan["template_nome"] = f"Cópia de {ch['name']}"
    return db.channel_create(name[:80], (body.niche if body.niche is not None else ch["niche"]).strip()[:200], start, plan)


@app.post("/api/channels/{cid}/save-template", status_code=201)
def channels_save_template(cid: str, body: TemplateIn):
    ch = _channel_or_404(cid)
    if not body.name.strip():
        raise HTTPException(422, "dê um nome ao modelo")
    t = db.template_create(body.name.strip()[:80], body.description.strip()[:300], channel_plan.clone_plan(ch["plan"]))
    return {k: t[k] for k in ("id", "name", "description", "created")}


@app.get("/api/channel-templates")
def channel_templates():
    built_in = [{"id": channel_plan.TEMPLATE_ID, "name": channel_plan.TEMPLATE_NAME, "description": "Plano completo do Arcano Digital: nicho, concorrentes, 100 ideias, calendário de 26 vídeos, Shorts, produção, monetização e revisão.", "builtin": True},
                {"id": "vazio", "name": "Em branco, com todas as seções para preencher", "description": "Estrutura vazia. Preencha à mão ou peça ao Claude para executar o playbook de prompts.", "builtin": True}]
    saved = [{"id": t["id"], "name": t["name"], "description": t["description"], "builtin": False} for t in db.template_list()]
    return built_in + saved


@app.delete("/api/channel-templates/{tid}", status_code=204)
def channel_template_delete(tid: str):
    if not db.template_get(tid):
        raise HTTPException(404, "modelo não encontrado")
    db.template_delete(tid)


@app.get("/api/channels/{cid}/roteiros/{n}/narracao")
def channels_roteiro_narracao(cid: str, n: int):
    """Só o texto falado de um roteiro (sem as marcações de B-roll, tela e som), pronto para colar em Novo vídeo."""
    ch = _channel_or_404(cid)
    r = next((x for x in ch["plan"].get("roteiros", []) if x.get("video_n") == n), None)
    if not r:
        raise HTTPException(404, "roteiro não encontrado")
    text = channel_content_c.narracao_limpa(r.get("marcado", ""))
    return {"video_n": n, "titulo": r.get("titulo", ""), "narracao": text, "palavras": len(text.split()), "minutos": round(len(text.split()) / 125, 1)}


class PromptIn(BaseModel):
    titulo: str
    body: str
    quando_usar: str = ""
    por_que_funciona: str = ""
    variaveis: list[str] = []
    secoes_geradas: list[str] = []
    ordem: int = 50


@app.get("/api/prompts")
def prompts_list():
    return db.prompt_list()


@app.post("/api/prompts", status_code=201)
def prompts_create(body: PromptIn):
    if not body.titulo.strip() or not body.body.strip():
        raise HTTPException(422, "informe o título e o texto do prompt")
    pid = channel_slug(body.titulo)
    if db.prompt_get(pid):
        pid = f"{pid}-{uuid.uuid4().hex[:4]}"
    return db.prompt_save(pid, {**body.model_dump(), "original": ""}, builtin=0)


@app.put("/api/prompts/{pid}")
def prompts_update(pid: str, body: PromptIn):
    if not db.prompt_get(pid):
        raise HTTPException(404, "prompt não encontrado")
    return db.prompt_save(pid, body.model_dump())


@app.post("/api/prompts/{pid}/restore")
def prompts_restore(pid: str):
    """Volta um prompt de fábrica ao texto original do sistema."""
    from . import prompt_library
    fab = next((p for p in prompt_library.PROMPTS if p["id"] == pid), None)
    if not fab or not db.prompt_get(pid):
        raise HTTPException(404, "só prompts de fábrica podem ser restaurados")
    return db.prompt_save(pid, fab)


@app.delete("/api/prompts/{pid}", status_code=204)
def prompts_delete(pid: str):
    cur = db.prompt_get(pid)
    if not cur:
        raise HTTPException(404, "prompt não encontrado")
    if cur["builtin"]:
        raise HTTPException(409, "prompts de fábrica não são apagados; edite ou restaure")
    db.prompt_delete(pid)


def channel_slug(text: str) -> str:
    from . import profiles as _p
    return _p.slugify(text)[:60]


# --------------------------------------------------------------------------- YouTube (API): conexão, envio, agendamento e métricas
class YtClientIn(BaseModel):
    client_id: str
    client_secret: str


class YtPasteIn(BaseModel):
    pasted: str


class YtUploadIn(BaseModel):
    ignorar_regras: bool = False          # enviar mesmo com erros nas regras do canal
    privacidade: str | None = None        # privado | nao_listado | publico | agendado
    publish_at: str | None = None         # '2026-11-24T18:00' em hora do Brasil
    conteudo_sintetico: bool | None = None


def _yt_wrap(fn):
    try:
        return fn()
    except youtube.YouTubeError as e:
        raise HTTPException(422, str(e))


@app.get("/api/youtube/config")
def yt_config():
    return {"configured": youtube.client_config() is not None, "redirect_uri": youtube.REDIRECT_URI, "scopes": youtube.SCOPES, "max_uploads_per_day": youtube.MAX_UPLOADS_PER_DAY}


@app.put("/api/youtube/config")
def yt_config_save(body: YtClientIn):
    """Guarda o ID e a chave do projeto Google (só escrita: a chave nunca volta pela API)."""
    _yt_wrap(lambda: youtube.save_client(body.client_id, body.client_secret))
    return {"configured": True}


@app.post("/api/channels/{cid}/youtube/auth-url")
def yt_auth_url(cid: str):
    _channel_or_404(cid)
    return {"url": _yt_wrap(lambda: youtube.auth_url(cid))}


@app.post("/api/channels/{cid}/youtube/auth-finish")
def yt_auth_finish(cid: str, body: YtPasteIn):
    _channel_or_404(cid)
    info = _yt_wrap(lambda: youtube.finish_auth(cid, body.pasted))
    return {"conectado": True, "canal": info}


@app.delete("/api/channels/{cid}/youtube", status_code=204)
def yt_disconnect(cid: str):
    _channel_or_404(cid)
    youtube.disconnect(cid)


def _ypp_progress(snap: dict | None) -> dict | None:
    if not snap:
        return None
    novas = dt.date.today() >= dt.date(2027, 2, 1)
    horas_meta = 8000 if novas else 4000
    return {"horas": snap["horas_longos_365"], "horas_meta": horas_meta, "inscritos": snap["canal"]["subs"], "inscritos_meta": 1000, "inclui_shorts": snap["horas_inclui_shorts"],
            "shorts_views_90d": snap["shorts_views_90d"], "shorts_meta": 20_000_000 if novas else 10_000_000, "regras_novas_valem": novas}


@app.get("/api/channels/{cid}/youtube")
def yt_status(cid: str):
    ch = _channel_or_404(cid)
    snap = db.snapshot_latest(cid)
    t = youtube._tokens(cid) or {}
    return {"cliente_configurado": youtube.client_config() is not None, "conectado": youtube.is_connected(cid), "conta": {"id": t.get("yt_channel_id"), "titulo": t.get("yt_title")},
            "config": youtube_jobs.cfg_of(ch), "snapshot": snap, "ypp": _ypp_progress(snap), "piores": youtube.worst_videos(snap["videos"]) if snap else [],
            "envios": db.yt_uploads(channel_id=cid)[:30], "envios_hoje": db.yt_uploads_today(cid), "max_envios_dia": youtube.MAX_UPLOADS_PER_DAY, "redirect_uri": youtube.REDIRECT_URI}


@app.post("/api/channels/{cid}/youtube/sync", status_code=202)
def yt_sync(cid: str):
    _channel_or_404(cid)
    if not youtube.is_connected(cid):
        raise HTTPException(409, "conecte o canal ao YouTube primeiro")
    return db.job_create("youtube_sync", None, {"channel_id": cid})


@app.get("/api/projects/{pid}/youtube")
def yt_project(pid: str):
    p = _project(pid)
    ch = db.channel_get(p.get("channel_id") or "")
    return {"conectado": bool(ch and youtube.is_connected(ch["id"])), "envios": db.yt_uploads(project_id=pid), "config": youtube_jobs.cfg_of(ch) if ch else None}


@app.post("/api/projects/{pid}/youtube/upload", status_code=202)
def yt_upload(pid: str, body: YtUploadIn):
    p = _project(pid)
    ch = db.channel_get(p.get("channel_id") or "")
    if not ch or not youtube.is_connected(ch["id"]):
        raise HTTPException(409, "conecte o canal ao YouTube primeiro (aba YouTube do canal)")
    if p["status"] != "done":
        raise HTTPException(409, "termine o vídeo antes de enviar ao YouTube")
    if body.privacidade and body.privacidade not in youtube_jobs.PRIV:
        raise HTTPException(422, "privacidade inválida")
    if any(u["status"] in ("enviado", "publicado", "enviando") for u in db.yt_uploads(project_id=pid)):
        raise HTTPException(409, "este vídeo já foi enviado ao YouTube (veja o link abaixo)")
    checks = channel_rules.project_checks(p, ch)
    if not checks["pode_enviar"] and not body.ignorar_regras:
        first = next(x for x in checks["achados"] if x["nivel"] == "erro")
        raise HTTPException(409, f"as regras do canal barram este envio: {first['mensagem']} (corrija, ou envie mesmo assim)")
    return _enqueue("youtube_upload", pid, {k: v for k, v in body.model_dump().items() if v is not None and k != "ignorar_regras"})


# --------------------------------------------------------------------------- regras do canal: o plano comanda a geração
class LintIn(BaseModel):
    kind: str                      # roteiro | titulo | miniatura | descricao
    text: str = ""
    formato: str | None = None


@app.get("/api/channels/{cid}/rules")
def channel_rules_get(cid: str):
    ch = _channel_or_404(cid)
    r = channel_rules.effective(ch)
    return {"regras": r, "contexto": channel_rules.context_text(ch), "descricao": channel_rules.DESCRICAO,
            "padroes": {"profile_id": r["visual"]["estilo_padrao"], "voice": r["narracao"]["voz"], "speed": r["narracao"]["velocidade"]}}


@app.post("/api/channels/{cid}/lint")
def channel_lint(cid: str, body: LintIn):
    """Verifica um texto contra as regras do canal (rápido, sem IA): roteiro, título, miniatura ou descrição."""
    rules = channel_rules.effective(_channel_or_404(cid))
    if body.kind == "roteiro":
        return channel_rules.lint_script(body.text, rules, body.formato)
    achados = {"titulo": lambda: channel_rules.lint_title(body.text, rules), "miniatura": lambda: channel_rules.lint_thumb(body.text, rules),
               "descricao": lambda: channel_rules.lint_description(body.text, rules, 10, True)}.get(body.kind)
    if not achados:
        raise HTTPException(422, "tipo inválido (roteiro, titulo, miniatura ou descricao)")
    return {"achados": achados()}


@app.get("/api/projects/{pid}/checks")
def project_checks(pid: str):
    p = _project(pid)
    return channel_rules.project_checks(p, db.channel_get(p.get("channel_id") or ""))


@app.post("/api/projects/{pid}/review-script", status_code=202)
def project_review_script(pid: str):
    p = _project(pid)
    if p["meta"].get("kind") == "clip":
        raise HTTPException(409, "a revisão de roteiro é só para vídeos narrados")
    return _enqueue("script_review", pid)


# O mount de arquivos estáticos fica SEMPRE por último: qualquer rota escrita depois dele seria engolida por ele.
if config.WEB.exists():
    app.mount("/", StaticFiles(directory=config.WEB, html=True), name="web")
