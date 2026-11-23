"""Tarefas do YouTube que rodam na fila da andes (envio de vídeo e leitura de métricas) e o piloto automático do calendário."""
import datetime as dt
import threading
import time

from . import channel_plan, channel_rules, channels, db, metadata, youtube
from .pipeline.engine import project_dir

PRIV = {"privado": "private", "nao_listado": "unlisted", "publico": "public", "agendado": "agendado"}
MIN_LEAD = 20 * 60         # agendar com menos de 20 minutos de folga não funciona bem: vai privado
SYNC_EVERY = 20 * 3600
AUTO_EVERY = 300
MAX_ERRORS_PER_VIDEO = 3


def cfg_of(ch: dict) -> dict:
    return {**channel_plan.YT_DEFAULT, **(ch["plan"].get("youtube_config") or {})}


def _link_item(ch: dict, pid: str, data: dict) -> None:
    """Põe no item do calendário o que se sabe do vídeo no YouTube (link, privacidade, hora marcada)."""
    fresh = db.channel_get(ch["id"])
    for v in fresh["plan"].get("videos", []):
        if v.get("project_id") == pid:
            v["youtube"] = {**(v.get("youtube") or {}), **data}
            if v["status"] in ("planejado", "roteiro", "produzindo"):
                v["status"] = "pronto"
            if data.get("privacy_now") == "public":
                v["status"] = "publicado"
    db.channel_update(ch["id"], plan=fresh["plan"])


def run_upload(pid: str, payload: dict, progress) -> dict:
    project = db.project_get(pid)
    ch = db.channel_get(project["channel_id"]) if project else None
    if not project or not ch:
        raise ValueError("projeto ou canal não encontrado")
    cid = ch["id"]
    final = project_dir(pid) / "final.mp4"
    if project["status"] != "done" or not final.is_file():
        raise ValueError("o vídeo precisa estar pronto para ir ao YouTube")
    if not youtube.is_connected(cid):
        raise ValueError("conecte o canal ao YouTube antes de enviar")
    cfg = cfg_of(ch)
    mode = PRIV.get(payload.get("privacidade") or cfg["privacidade"], "agendado")
    publish_at, privacy = None, "private" if mode == "agendado" else mode
    if mode == "agendado":
        if not payload.get("publish_at"):
            raise ValueError("escolha a data e a hora da publicação")
        publish_at = youtube.to_rfc3339(payload["publish_at"], cfg["fuso"])
        when = dt.datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        if when < dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=MIN_LEAD):
            raise ValueError("a data de publicação precisa ser pelo menos 20 minutos no futuro")
    if db.yt_uploads_today(cid) >= youtube.MAX_UPLOADS_PER_DAY:
        raise ValueError(f"limite de {youtube.MAX_UPLOADS_PER_DAY} envios por dia (cota da API do YouTube); tente amanhã")
    yt = project["meta"].get("youtube") or {}
    title = (yt.get("title") or project["title"]).strip()
    description = metadata.final_description(yt, project["scenes"], channel_rules.editorial_footer(ch)) if yt else project["title"]
    row = db.yt_upload_create(channel_id=cid, project_id=pid, title=title, privacy=privacy, publish_at=publish_at, item_n=payload.get("item_n"))
    _stages = getattr(progress, "init_stages", None)
    if _stages:
        _stages([("send", "Enviar o vídeo ao YouTube", 1), ("thumb", "Enviar a miniatura", 1)])
    progress(0.03, "abrindo o envio ao YouTube")
    try:
        res = youtube.upload_video(cid, final, title=title, description=description, tags=yt.get("tags") or [], privacy=privacy, publish_at=publish_at, category=str(cfg["categoria"]),
                                   synthetic=bool(payload.get("conteudo_sintetico", cfg["conteudo_sintetico"])),
                                   progress=lambda f: progress(0.05 + 0.85 * f, f"enviando o vídeo ({int(f * 100)}%)"))
    except Exception as e:
        db.yt_upload_update(row, status="erro", error=str(e)[:500])
        raise
    vid = res["id"]
    actual, wanted = (res.get("status") or {}).get("privacyStatus"), "private" if publish_at else privacy
    warn = None
    if actual and actual != wanted:
        warn = f"O YouTube deixou o vídeo como “{actual}” e não como “{wanted}”. Projetos de API ainda não auditados só enviam vídeos privados: publique pelo YouTube Studio."
    elif publish_at or privacy != "private":
        warn = ("Se na hora marcada o vídeo continuar privado, o projeto de API ainda não foi auditado pelo Google: publique pelo YouTube Studio."
                if publish_at else "Confira no YouTube Studio se o vídeo ficou público.")
    sel = project["meta"].get("thumbnail") or {}
    variant = next((v for v in sel.get("variants", []) if v["i"] == sel.get("selected")), None)
    if variant and (project_dir(pid) / variant["file"]).is_file():
        _stage = getattr(progress, "set_stage", None)
        if _stage:
            _stage("send", 1)
        progress(0.93, "enviando a miniatura")
        try:
            youtube.set_thumbnail(cid, vid, project_dir(pid) / variant["file"])
        except youtube.YouTubeError as e:
            warn = f"{warn + ' ' if warn else ''}Miniatura não enviada: {e}"
    db.yt_upload_update(row, status="enviado", video_id=vid, warning=warn)
    _link_item(ch, pid, {"video_id": vid, "url": f"https://youtu.be/{vid}", "privacy_now": actual or wanted, "publish_at": publish_at})
    progress(1.0, "vídeo enviado ao YouTube")
    return {"video_id": vid, "url": f"https://youtu.be/{vid}", "aviso": warn}


def run_sync(cid: str, progress) -> dict:
    ch = db.channel_get(cid)
    if not ch or not youtube.is_connected(cid):
        raise ValueError("o canal não está conectado ao YouTube")
    getattr(progress, "init_stages", lambda s: None)([("read", "Ler os números do YouTube", 1)])
    progress(0.1, "lendo os números do canal no YouTube")
    snap = youtube.sync_snapshot(cid)
    db.snapshot_save(cid, snap)
    # situação dos vídeos que o MisterClip enviou (um vídeo agendado vira público sozinho)
    ups = [u for u in db.yt_uploads(channel_id=cid) if u["video_id"]]
    if ups:
        info = youtube.videos_info(cid, [u["video_id"] for u in ups])
        for u in ups:
            m = info.get(u["video_id"])
            if m:
                db.yt_upload_update(u["id"], status="publicado" if m["privacy"] == "public" else "enviado")
                if u["project_id"]:
                    _link_item(ch, u["project_id"], {"privacy_now": m["privacy"], "views": m["views"]})
    # uma linha por dia na aba Métricas do canal
    today = dt.date.today().isoformat()
    serie = snap["serie_90d"][-28:]
    views28 = sum(r["views"] for r in serie)
    vs = [v for v in snap["videos"] if v.get("ctr") is not None and v.get("impressoes")]
    ctr = round(sum(v["ctr"] * v["impressoes"] for v in vs) / sum(v["impressoes"] for v in vs), 2) if vs else None
    tot = sum(v["views"] for v in snap["videos"]) or 0
    avd = round(sum(v["assistido_pct"] * v["views"] for v in snap["videos"]) / tot, 1) if tot else None
    for m in db.metrics_list(cid):
        if m["day"] == today and (m["note"] or "").startswith("YouTube"):
            db.metric_delete(cid, m["id"])
    db.metric_add(cid, today, snap["canal"]["subs"], snap["horas_longos_365"], views28, ctr, avd, "YouTube (sincronizado)")
    progress(1.0, "números atualizados")
    return {"inscritos": snap["canal"]["subs"], "horas_longos_365": snap["horas_longos_365"], "views_28d": views28, "avisos": snap["avisos"]}


# --------------------------------------------------------------------------- piloto automático
def due_uploads(view: dict, uploads: list[dict], cfg: dict, now: dt.datetime | None = None) -> list[dict]:
    """Vídeos do calendário que já estão prontos e ainda não foram ao YouTube, com a privacidade e a hora de cada um."""
    from zoneinfo import ZoneInfo
    now = now or dt.datetime.now(dt.timezone.utc)
    tz = ZoneInfo(cfg["fuso"])
    by_proj: dict[str, list[dict]] = {}
    for u in uploads:
        by_proj.setdefault(u["project_id"], []).append(u)
    out = []
    for v in view["videos"]:
        p = v.get("projeto")
        if not p or p["status"] != "done" or v["status"] == "publicado":
            continue
        rows = by_proj.get(p["id"], [])
        if any(r["status"] in ("enviando", "enviado", "publicado") for r in rows) or sum(1 for r in rows if r["status"] == "erro") >= MAX_ERRORS_PER_VIDEO:
            continue
        mode = cfg["privacidade"]
        local = dt.datetime.combine(dt.date.fromisoformat(v["data"]), dt.time.fromisoformat(cfg["hora"]), tzinfo=tz)
        item = {"project_id": p["id"], "item_n": v["n"], "titulo": v["titulo"]}
        if mode == "agendado":
            if local.astimezone(dt.timezone.utc) > now + dt.timedelta(seconds=MIN_LEAD):
                item.update(privacidade="agendado", publish_at=local.strftime("%Y-%m-%dT%H:%M"))
            else:
                item.update(privacidade="privado", aviso="o horário do calendário já passou: foi como privado")
        else:
            item.update(privacidade=mode)
        out.append(item)
    return out


def effective_block(ch: dict) -> bool:
    return bool(channel_rules.effective(ch)["publicacao"]["bloquear_envio_automatico_com_erros"])


def _passes_rules(ch: dict, todo_item: dict) -> bool:
    p = db.project_get(todo_item["project_id"])
    res = channel_rules.project_checks(p, ch)
    msgs = [x["mensagem"] for x in res["achados"] if x["nivel"] == "erro"]
    fresh = db.channel_get(ch["id"])
    for v in fresh["plan"].get("videos", []):
        if v.get("project_id") == p["id"] and (v.get("revisar") or []) != msgs:
            v["revisar"] = msgs
            db.channel_update(ch["id"], plan=fresh["plan"])
    return res["pode_enviar"]


_lock = threading.Lock()
_last = {"auto": 0.0}


def tick(now: float | None = None) -> None:
    """Chamado pelo agendador. A cada 5 minutos: manda o próximo vídeo pronto (um por vez) e atualiza os números de quem passou de 20 h sem leitura."""
    now = now or time.time()
    if now - _last["auto"] < AUTO_EVERY or not _lock.acquire(blocking=False):
        return
    try:
        _last["auto"] = now
        if not youtube.client_config():
            return
        active = {(j["kind"], (j.get("payload") or {}).get("channel_id") or j["project_id"]) for j in db.active_jobs()}
        for ch in db.channel_list():
            cid = ch["id"]
            if not youtube.is_connected(cid):
                continue
            snap = db.snapshot_latest(cid)
            if (not snap or now - snap["taken"] > SYNC_EVERY) and ("youtube_sync", cid) not in active:
                db.job_create("youtube_sync", None, {"channel_id": cid})
                continue
            cfg = cfg_of(ch)
            if not cfg["envio_automatico"] or any(k == "youtube_upload" for k, _ in active) or db.yt_uploads_today(cid) >= youtube.MAX_UPLOADS_PER_DAY:
                continue
            view = channels.view(ch, [p for p in db.project_list() if p.get("channel_id") == cid], db.metrics_list(cid))
            todo = due_uploads(view, db.yt_uploads(channel_id=cid), cfg)
            if effective_block(ch):
                todo = [t for t in todo if _passes_rules(ch, t)]       # vídeo com erro nas regras do canal NÃO sobe sozinho: fica marcado para revisar
            if todo:
                t = todo[0]
                db.job_create("youtube_upload", t["project_id"], {k: t[k] for k in ("privacidade", "publish_at", "item_n") if k in t})
                active.add(("youtube_upload", t["project_id"]))
    finally:
        _lock.release()
