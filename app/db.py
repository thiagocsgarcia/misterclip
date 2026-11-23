"""Persistência em SQLite: projetos (com as cenas em JSON) e fila de jobs."""
import json
import sqlite3
import threading
import time
import uuid

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, title TEXT, text TEXT, profile_id TEXT,
  voice TEXT, speed REAL, status TEXT, scenes TEXT, meta TEXT,
  created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY, project_id TEXT, run_at REAL, status TEXT, step TEXT, job_id TEXT,
  message TEXT, cancel INTEGER DEFAULT 0, retries INTEGER DEFAULT 0, created REAL, started REAL, finished REAL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, project_id TEXT, kind TEXT, payload TEXT,
  status TEXT, progress REAL, message TEXT, result TEXT,
  created REAL, started REAL, finished REAL
);
CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY, name TEXT, niche TEXT, start_date TEXT, plan TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS plan_templates (
  id TEXT PRIMARY KEY, name TEXT, description TEXT, plan TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS prompts (
  id TEXT PRIMARY KEY, titulo TEXT, ordem INTEGER, data TEXT, builtin INTEGER, updated REAL
);
CREATE TABLE IF NOT EXISTS youtube_uploads (
  id TEXT PRIMARY KEY, channel_id TEXT, project_id TEXT, video_id TEXT, title TEXT, privacy TEXT, publish_at TEXT, status TEXT,
  warning TEXT, error TEXT, item_n INTEGER, created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS youtube_snapshots (
  id TEXT PRIMARY KEY, channel_id TEXT, taken REAL, data TEXT
);
CREATE TABLE IF NOT EXISTS channel_metrics (
  id TEXT PRIMARY KEY, channel_id TEXT, day TEXT, subs INTEGER, hours REAL, views INTEGER, ctr REAL, avd REAL, note TEXT, created REAL
);
"""
_JSON_PROJECT = ("scenes", "meta")
FIRST_CHANNEL_NAME = "Arcano Digital"
FIRST_CHANNEL_NICHE = "Filosofia, ocultismo, tecnologia e futurismo"


def init(path=None) -> None:
    global _conn
    config.DATA.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = sqlite3.connect(path or config.DATA / "misterclip.db", check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    ensure_first_channel()
    ensure_prompts()
    resume_interrupted()


def _migrate(conn: sqlite3.Connection) -> None:
    """Acrescenta as colunas novas de `jobs` em bancos criados por versões anteriores."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    for name, ddl in (("stages", "TEXT"), ("attempts", "INTEGER DEFAULT 0")):
        if name not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
    if pcols and "channel_id" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN channel_id TEXT")
    conn.commit()


def ensure_first_channel() -> None:
    """Garante o primeiro canal e põe nele todo vídeo que ainda não pertence a um canal."""
    from . import channel_plan
    with _lock:
        row = _c().execute("SELECT id FROM channels ORDER BY created LIMIT 1").fetchone()
        if row is None:
            cid, now = new_id(), time.time()
            _c().execute("INSERT INTO channels VALUES (?,?,?,?,?,?)", (cid, FIRST_CHANNEL_NAME, FIRST_CHANNEL_NICHE,
                         channel_plan.next_monday().isoformat(), json.dumps(channel_plan.build(), ensure_ascii=False), now))
        else:
            cid = row[0]
        _c().execute("UPDATE projects SET channel_id=? WHERE channel_id IS NULL OR channel_id=''", (cid,))
        for r in _c().execute("SELECT id, plan FROM channels").fetchall():  # planos salvos por versões antigas ganham as novidades
            plan = json.loads(r[1]) if r[1] else {}
            if channel_plan.upgrade(plan):
                _c().execute("UPDATE channels SET plan=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), r[0]))
        _c().commit()


def _c() -> sqlite3.Connection:
    if _conn is None:
        init()
    return _conn  # type: ignore[return-value]


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _project(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in _JSON_PROJECT:
        d[k] = json.loads(d[k]) if d[k] else ([] if k == "scenes" else {})
    return d


def project_create(title, text, profile_id, voice, speed, channel_id=None) -> dict:
    pid, now = new_id(), time.time()
    with _lock:
        if not channel_id:
            r = _c().execute("SELECT id FROM channels ORDER BY created LIMIT 1").fetchone()
            channel_id = r[0] if r else None
        _c().execute(
            "INSERT INTO projects (id,title,text,profile_id,voice,speed,status,scenes,meta,created,updated,channel_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, title, text, profile_id, voice, speed, "draft", "[]", "{}", now, now, channel_id),
        )
        _c().commit()
    return project_get(pid)


def project_get(pid: str) -> dict | None:
    with _lock:
        return _project(_c().execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())


def project_list() -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM projects ORDER BY created DESC").fetchall()
    out = []
    for r in rows:
        p = _project(r)
        p["scene_count"] = len(p["scenes"])
        p.pop("scenes")
        out.append(p)
    return out


def project_update(pid: str, **fields) -> dict:
    for k in _JSON_PROJECT:
        if k in fields:
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    fields["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _c().execute(f"UPDATE projects SET {cols} WHERE id=?", (*fields.values(), pid))
        _c().commit()
    return project_get(pid)


def project_delete(pid: str) -> None:
    with _lock:
        _c().execute("DELETE FROM projects WHERE id=?", (pid,))
        _c().execute("DELETE FROM jobs WHERE project_id=?", (pid,))
        _c().execute("DELETE FROM schedules WHERE project_id=?", (pid,))
        _c().commit()


# ---------------------------------------------------------------- jobs
def _job(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
    d["result"] = json.loads(d["result"]) if d["result"] else None
    d["stages"] = json.loads(d["stages"]) if d.get("stages") else None
    return d


def job_create(kind: str, project_id: str | None = None, payload: dict | None = None) -> dict:
    jid = new_id()
    with _lock:
        _c().execute(
            "INSERT INTO jobs (id, project_id, kind, payload, status, progress, message, result, created, started, finished, stages, attempts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, project_id, kind, json.dumps(payload or {}), "queued", 0.0, "na fila", None, time.time(), None, None, None, 0),
        )
        _c().commit()
    return job_get(jid)


def job_get(jid: str) -> dict | None:
    with _lock:
        return _job(_c().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())


def job_update(jid: str, **fields) -> None:
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
    if "stages" in fields:
        fields["stages"] = json.dumps(fields["stages"], ensure_ascii=False)
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _c().execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), jid))
        _c().commit()


def job_next_queued() -> dict | None:
    with _lock:
        return _job(_c().execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone())


def jobs_for_project(pid: str, limit: int = 20) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created DESC LIMIT ?", (pid, limit)).fetchall()
    return [_job(r) for r in rows]


def jobs_active(kind: str) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM jobs WHERE kind=? AND status IN ('queued','running','cancelling')", (kind,)).fetchall()
    return [_job(r) for r in rows]


def project_busy(pid: str) -> bool:
    with _lock:
        r = _c().execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running','cancelling') LIMIT 1", (pid,)).fetchone()
    return r is not None


def job_cancel(jid: str) -> dict | None:
    """Fila: cancela na hora. Em execução: marca 'cancelling' e o worker para no próximo ponto de checagem."""
    with _lock:
        job = job_get(jid)
        if job is None:
            return None
        if job["status"] == "queued":
            job_update(jid, status="cancelled", message="cancelado antes de começar", finished=time.time())
        elif job["status"] == "running":
            job_update(jid, status="cancelling", message="cancelando…")
        return job_get(jid)


# ------------------------------------------------------------ agendamentos
ACTIVE_SCHEDULE = ("pending", "running")


def schedule_create(project_id: str, run_at: float) -> dict:
    """Um agendamento pendente por projeto: criar outro substitui o anterior."""
    sid, now = new_id(), time.time()
    with _lock:
        _c().execute("UPDATE schedules SET status='cancelled', message='substituído por outro horário', finished=? WHERE project_id=? AND status='pending'",
                     (now, project_id))
        _c().execute("INSERT INTO schedules VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, project_id, run_at, "pending", None, None, None, 0, 0, now, None, None))
        _c().commit()
    return schedule_get(sid)


def schedule_get(sid: str) -> dict | None:
    with _lock:
        r = _c().execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def schedule_for_project(project_id: str) -> dict | None:
    """O agendamento ativo do projeto; se não houver, o mais recente."""
    with _lock:
        r = _c().execute("SELECT * FROM schedules WHERE project_id=? ORDER BY (status IN ('pending','running')) DESC, created DESC LIMIT 1",
                         (project_id,)).fetchone()
    return dict(r) if r else None


def schedules_list(limit: int = 100) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM schedules ORDER BY (status IN ('pending','running')) DESC, "
                            "CASE WHEN status IN ('pending','running') THEN run_at END ASC, created DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def schedules_by_status(status: str) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM schedules WHERE status=? ORDER BY run_at", (status,)).fetchall()
    return [dict(r) for r in rows]


def schedule_update(sid: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _c().execute(f"UPDATE schedules SET {cols} WHERE id=?", (*fields.values(), sid))
        _c().commit()


def worker_busy() -> bool:
    """Há algum job (de qualquer projeto) na fila ou em execução? A GPU é uma só."""
    with _lock:
        return _c().execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','cancelling') LIMIT 1").fetchone() is not None


def schedules_between(a: float, b: float) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM schedules WHERE run_at BETWEEN ? AND ? ORDER BY run_at", (a, b)).fetchall()
    return [dict(r) for r in rows]


def jobs_between(kinds: tuple[str, ...], a: float, b: float) -> list[dict]:
    """Jobs que começaram (ou foram criados) na janela, já com o payload decodificado."""
    marks = ",".join("?" for _ in kinds)
    with _lock:
        rows = _c().execute(
            f"SELECT * FROM jobs WHERE kind IN ({marks}) AND COALESCE(started, created) BETWEEN ? AND ? "
            "AND status IN ('running','cancelling','done','failed','cancelled') ORDER BY COALESCE(started, created)",
            (*kinds, a, b)).fetchall()
    return [_job(r) for r in rows]


# ------------------------------------------------- retomar o que um reinício interrompeu
MAX_ATTEMPTS = 3  # tentativas por job; evita laço infinito se o próprio job derruba o serviço


def resume_interrupted() -> dict:
    """Ao iniciar: jobs que estavam rodando voltam para a fila (preparar, criar o vídeo etc. retomam de onde pararam).

    Quem já tentou MAX_ATTEMPTS vezes é marcado como falho; quem estava sendo cancelado é dado como cancelado."""
    out = {"requeued": 0, "failed": 0, "cancelled": 0}
    with _lock:
        for r in _c().execute("SELECT id, status, attempts FROM jobs WHERE status IN ('running','cancelling')").fetchall():
            if r["status"] == "cancelling":
                _c().execute("UPDATE jobs SET status='cancelled', message='cancelado', finished=? WHERE id=?", (time.time(), r["id"]))
                out["cancelled"] += 1
            elif (r["attempts"] or 0) >= MAX_ATTEMPTS:
                _c().execute("UPDATE jobs SET status='failed', message='interrompido por reinício (já tentou %d vezes)', finished=? WHERE id=?" % MAX_ATTEMPTS,
                             (time.time(), r["id"]))
                out["failed"] += 1
            else:
                _c().execute("UPDATE jobs SET status='queued', message='retomando depois de um reinício', started=NULL WHERE id=?", (r["id"],))
                out["requeued"] += 1
        _c().commit()
    return out


def active_jobs() -> list[dict]:
    """Jobs na fila ou em execução, de todos os projetos (para mostrar o andamento na lista)."""
    with _lock:
        rows = _c().execute("SELECT project_id, kind, status, progress, message, payload FROM jobs WHERE status IN ('queued','running','cancelling') "
                            "ORDER BY (status='queued'), created").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        except ValueError:
            d["payload"] = {}
        out.append(d)
    return out


# --------------------------------------------------------------------------- canais
def _channel(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["plan"] = json.loads(d["plan"]) if d["plan"] else {}
    return d


def channel_list() -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM channels ORDER BY created").fetchall()
    return [_channel(r) for r in rows]


def channel_get(cid: str) -> dict | None:
    with _lock:
        return _channel(_c().execute("SELECT * FROM channels WHERE id=?", (cid,)).fetchone())


def channel_create(name: str, niche: str, start_date: str, plan: dict) -> dict:
    cid = new_id()
    with _lock:
        _c().execute("INSERT INTO channels VALUES (?,?,?,?,?,?)", (cid, name, niche, start_date, json.dumps(plan, ensure_ascii=False), time.time()))
        _c().commit()
    return channel_get(cid)


def channel_update(cid: str, **fields) -> dict:
    if "plan" in fields:
        fields["plan"] = json.dumps(fields["plan"], ensure_ascii=False)
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _c().execute(f"UPDATE channels SET {cols} WHERE id=?", (*fields.values(), cid))
        _c().commit()
    return channel_get(cid)


def channel_delete(cid: str) -> None:
    """Só se o canal não tiver vídeos; o chamador confere."""
    with _lock:
        _c().execute("DELETE FROM channel_metrics WHERE channel_id=?", (cid,))
        _c().execute("DELETE FROM channels WHERE id=?", (cid,))
        _c().commit()


def metrics_list(cid: str) -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM channel_metrics WHERE channel_id=? ORDER BY day, created", (cid,)).fetchall()
    return [dict(r) for r in rows]


def metric_add(cid: str, day: str, subs: int, hours: float, views: int, ctr: float | None, avd: float | None, note: str) -> dict:
    mid = new_id()
    with _lock:
        _c().execute("INSERT INTO channel_metrics VALUES (?,?,?,?,?,?,?,?,?,?)", (mid, cid, day, subs, hours, views, ctr, avd, note, time.time()))
        _c().commit()
        return dict(_c().execute("SELECT * FROM channel_metrics WHERE id=?", (mid,)).fetchone())


def metric_delete(cid: str, mid: str) -> None:
    with _lock:
        _c().execute("DELETE FROM channel_metrics WHERE id=? AND channel_id=?", (mid, cid))
        _c().commit()


# --------------------------------------------------------------------------- modelos de canal e biblioteca de prompts
def template_list() -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM plan_templates ORDER BY created").fetchall()
    return [{**dict(r), "plan": json.loads(r["plan"]) if r["plan"] else {}} for r in rows]


def template_get(tid: str) -> dict | None:
    with _lock:
        r = _c().execute("SELECT * FROM plan_templates WHERE id=?", (tid,)).fetchone()
    return {**dict(r), "plan": json.loads(r["plan"]) if r["plan"] else {}} if r else None


def template_create(name: str, description: str, plan: dict) -> dict:
    tid = new_id()
    with _lock:
        _c().execute("INSERT INTO plan_templates VALUES (?,?,?,?,?)", (tid, name, description, json.dumps(plan, ensure_ascii=False), time.time()))
        _c().commit()
    return template_get(tid)


def template_delete(tid: str) -> None:
    with _lock:
        _c().execute("DELETE FROM plan_templates WHERE id=?", (tid,))
        _c().commit()


def ensure_prompts() -> None:
    """Põe na biblioteca os prompts de fábrica que ainda não estão lá (nunca sobrescreve o que o usuário editou)."""
    from . import prompt_library
    with _lock:
        have = {r[0] for r in _c().execute("SELECT id FROM prompts").fetchall()}
        for p in prompt_library.PROMPTS:
            if p["id"] not in have:
                _c().execute("INSERT INTO prompts VALUES (?,?,?,?,?,?)", (p["id"], p["titulo"], p["ordem"], json.dumps(p, ensure_ascii=False), 1, time.time()))
        _c().commit()


def _prompt(row) -> dict:
    d = json.loads(row["data"]) if row["data"] else {}
    d.update(id=row["id"], titulo=row["titulo"], ordem=row["ordem"], builtin=bool(row["builtin"]), updated=row["updated"])
    return d


def prompt_list() -> list[dict]:
    with _lock:
        rows = _c().execute("SELECT * FROM prompts ORDER BY ordem, titulo").fetchall()
    return [_prompt(r) for r in rows]


def prompt_get(pid: str) -> dict | None:
    with _lock:
        r = _c().execute("SELECT * FROM prompts WHERE id=?", (pid,)).fetchone()
    return _prompt(r) if r else None


def prompt_save(pid: str, data: dict, *, builtin: int | None = None) -> dict:
    cur = prompt_get(pid)
    merged = {**(cur or {}), **data}
    titulo, ordem = str(merged.get("titulo") or pid), int(merged.get("ordem") or 99)
    payload = {k: v for k, v in merged.items() if k not in ("id", "builtin", "updated")}
    with _lock:
        if cur:
            _c().execute("UPDATE prompts SET titulo=?, ordem=?, data=?, updated=? WHERE id=?", (titulo, ordem, json.dumps(payload, ensure_ascii=False), time.time(), pid))
        else:
            _c().execute("INSERT INTO prompts VALUES (?,?,?,?,?,?)", (pid, titulo, ordem, json.dumps(payload, ensure_ascii=False), 0 if builtin is None else builtin, time.time()))
        _c().commit()
    return prompt_get(pid)


def prompt_delete(pid: str) -> None:
    with _lock:
        _c().execute("DELETE FROM prompts WHERE id=?", (pid,))
        _c().commit()


# --------------------------------------------------------------------------- YouTube: envios e fotografias das métricas
def yt_upload_create(**f) -> str:
    uid, now = new_id(), time.time()
    row = {"channel_id": None, "project_id": None, "video_id": None, "title": "", "privacy": "private", "publish_at": None, "status": "enviando", "warning": None, "error": None,
           "item_n": None, **f}
    with _lock:
        _c().execute("INSERT INTO youtube_uploads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (uid, row["channel_id"], row["project_id"], row["video_id"], row["title"], row["privacy"], row["publish_at"], row["status"], row["warning"], row["error"],
                      row["item_n"], now, now))
        _c().commit()
    return uid


def yt_upload_update(uid: str, **f) -> None:
    f["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in f)
    with _lock:
        _c().execute(f"UPDATE youtube_uploads SET {cols} WHERE id=?", (*f.values(), uid))
        _c().commit()


def yt_uploads(channel_id: str | None = None, project_id: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM youtube_uploads WHERE 1=1", []
    for col, v in (("channel_id", channel_id), ("project_id", project_id)):
        if v:
            q, a = q + f" AND {col}=?", a + [v]
    with _lock:
        rows = _c().execute(q + " ORDER BY created DESC", a).fetchall()
    return [dict(r) for r in rows]


def yt_uploads_today(channel_id: str) -> int:
    start = time.time() - 24 * 3600
    with _lock:
        return _c().execute("SELECT COUNT(*) FROM youtube_uploads WHERE channel_id=? AND created>? AND status IN ('enviado','publicado','enviando')", (channel_id, start)).fetchone()[0]


def snapshot_save(cid: str, data: dict) -> None:
    with _lock:
        _c().execute("INSERT INTO youtube_snapshots VALUES (?,?,?,?)", (new_id(), cid, data.get("taken", time.time()), json.dumps(data, ensure_ascii=False)))
        _c().execute("DELETE FROM youtube_snapshots WHERE channel_id=? AND id NOT IN (SELECT id FROM youtube_snapshots WHERE channel_id=? ORDER BY taken DESC LIMIT 40)", (cid, cid))
        _c().commit()


def snapshot_latest(cid: str) -> dict | None:
    with _lock:
        r = _c().execute("SELECT data FROM youtube_snapshots WHERE channel_id=? ORDER BY taken DESC LIMIT 1", (cid,)).fetchone()
    return json.loads(r[0]) if r else None
