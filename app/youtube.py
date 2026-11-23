"""Integração com o YouTube (Data API v3 e Analytics API v2), uma conexão por canal do MisterClip.

Login: OAuth2 de "aplicativo para computador" com PKCE e redirecionamento local (http://127.0.0.1:8765). O navegador de quem autoriza vai tentar abrir
esse endereço e mostrar um erro de conexão; o código vem no endereço da página, e a pessoa cola esse endereço no MisterClip (o fluxo "copiar e colar" antigo
do Google foi desligado em 2023). As chaves do projeto Google e os tokens ficam em data/youtube, com permissão 600.

Limites reais que este módulo respeita (documentação do YouTube):
- projetos de API NÃO auditados só enviam vídeos como PRIVADOS (o agendamento público só funciona depois da auditoria do Google);
- videos.insert custa 1.600 unidades da cota diária de 10.000 (no máximo uns 6 envios por dia);
- app do Google em modo "Teste" emite permissões que expiram em 7 dias: publique o app ("Em produção") e autorize de novo.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import time
import urllib.parse

import httpx

from . import config

SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/yt-analytics.readonly"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
REDIRECT_URI = "http://127.0.0.1:8765"
CHUNK = 8 * 1024 * 1024        # múltiplo de 256 KiB, como a API exige
PENDING_TTL = 30 * 60
MAX_UPLOADS_PER_DAY = 5        # 5 x 1.600 = 8.000 unidades de 10.000
TRANSPORT = None               # os testes trocam por httpx.MockTransport


class YouTubeError(RuntimeError):
    """Erro já em português, pronto para mostrar ao usuário."""


# --------------------------------------------------------------------------- arquivos privados
def _dir():
    d = config.DATA / "youtube"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_private(path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(path, 0o600)


def _read(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_client(client_id: str, client_secret: str) -> None:
    if not client_id.strip() or not client_secret.strip():
        raise YouTubeError("informe o ID do cliente e a chave secreta")
    _write_private(_dir() / "client.json", {"client_id": client_id.strip(), "client_secret": client_secret.strip()})


def client_config() -> dict | None:
    c = _read(_dir() / "client.json")
    return c if c and c.get("client_id") and c.get("client_secret") else None


def _tokens(cid: str) -> dict | None:
    return _read(_dir() / f"token_{cid}.json")


def _save_tokens(cid: str, data: dict) -> None:
    _write_private(_dir() / f"token_{cid}.json", data)


def is_connected(cid: str) -> bool:
    t = _tokens(cid)
    return bool(t and t.get("refresh_token"))


# --------------------------------------------------------------------------- HTTP
def _http(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(transport=TRANSPORT, timeout=timeout) if TRANSPORT else httpx.Client(timeout=timeout)


def _explain(r: httpx.Response) -> str:
    try:
        j = r.json()
    except ValueError:
        j = {}
    err = j.get("error")
    msg = err.get("message", "") if isinstance(err, dict) else str(err or j.get("error_description") or "")
    reasons = " ".join(str(e.get("reason", "")) for e in (err.get("errors", []) if isinstance(err, dict) else []))
    low = f"{msg} {reasons} {j.get('error_description', '')}".lower()
    if r.status_code == 401 or "invalid_grant" in low or "invalid_token" in low:
        return "A permissão do YouTube expirou ou foi revogada. Conecte o canal de novo."
    if "quotaexceeded" in low or "quota" in low and r.status_code == 403:
        return "A cota diária da API do YouTube acabou. Tente de novo amanhã."
    if "uploadlimitexceeded" in low or "exceeded the number of videos" in low:
        return "O YouTube limitou os envios deste canal por hoje. Tente amanhã."
    if "insufficientpermissions" in low or "insufficient authentication scopes" in low:
        return "Faltou uma permissão. Conecte o canal de novo e aceite todas as caixas."
    if "invalidpublishat" in low or "publishat" in low:
        return "A data de publicação precisa ser no futuro."
    if "youtubesignuprequired" in low:
        return "A conta Google não tem um canal do YouTube."
    if "forbidden" in low and "thumbnail" in low:
        return "O YouTube só libera miniaturas personalizadas em canais verificados por telefone."
    return f"O YouTube recusou o pedido ({r.status_code}): {msg or 'sem detalhes'}"


# --------------------------------------------------------------------------- login (OAuth com PKCE)
def auth_url(cid: str) -> str:
    c = client_config()
    if not c:
        raise YouTubeError("cadastre primeiro o ID do cliente e a chave secreta do projeto Google")
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _write_private(_dir() / f"pending_{cid}.json", {"verifier": verifier, "state": state, "created": time.time()})
    q = {"client_id": c["client_id"], "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
         "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def _parse_pasted(pasted: str) -> tuple[str, str | None]:
    text = pasted.strip()
    if text.startswith("http"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
        if q.get("error"):
            raise YouTubeError("Você não autorizou o acesso. Tente de novo e toque em Permitir.")
        if not q.get("code"):
            raise YouTubeError("Não achei o código no endereço colado. Copie o endereço inteiro da página de erro.")
        return q["code"][0], (q.get("state") or [None])[0]
    if not text:
        raise YouTubeError("cole o endereço da página que apareceu depois de autorizar")
    return text, None


def finish_auth(cid: str, pasted: str) -> dict:
    c = client_config()
    pending = _read(_dir() / f"pending_{cid}.json")
    if not c or not pending or time.time() - pending["created"] > PENDING_TTL:
        raise YouTubeError("a autorização expirou. Toque em Conectar de novo.")
    code, state = _parse_pasted(pasted)
    if state is not None and state != pending["state"]:
        raise YouTubeError("o endereço colado é de outra tentativa. Toque em Conectar de novo.")
    with _http() as h:
        r = h.post(TOKEN_URL, data={"code": code, "client_id": c["client_id"], "client_secret": c["client_secret"], "redirect_uri": REDIRECT_URI,
                                    "grant_type": "authorization_code", "code_verifier": pending["verifier"]})
    if r.status_code >= 400:
        raise YouTubeError(_explain(r))
    t = r.json()
    if not t.get("refresh_token"):
        raise YouTubeError("o Google não devolveu a permissão permanente. Remova o acesso do MisterClip em myaccount.google.com/permissions e conecte de novo.")
    _save_tokens(cid, {"access_token": t["access_token"], "refresh_token": t["refresh_token"], "expires_at": time.time() + int(t.get("expires_in", 3600)),
                       "scope": t.get("scope", ""), "connected_at": time.time()})
    (_dir() / f"pending_{cid}.json").unlink(missing_ok=True)
    info = channel_info(cid)
    _save_tokens(cid, {**_tokens(cid), "yt_channel_id": info["id"], "yt_title": info["title"]})
    return info


def _refresh(cid: str) -> str:
    c, t = client_config(), _tokens(cid)
    if not c or not t or not t.get("refresh_token"):
        raise YouTubeError("este canal ainda não está conectado ao YouTube")
    with _http() as h:
        r = h.post(TOKEN_URL, data={"client_id": c["client_id"], "client_secret": c["client_secret"], "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code >= 400:
        raise YouTubeError(_explain(r))
    j = r.json()
    t.update(access_token=j["access_token"], expires_at=time.time() + int(j.get("expires_in", 3600)))
    _save_tokens(cid, t)
    return t["access_token"]


def access_token(cid: str) -> str:
    t = _tokens(cid)
    if not t:
        raise YouTubeError("este canal ainda não está conectado ao YouTube")
    return t["access_token"] if t.get("expires_at", 0) - 60 > time.time() else _refresh(cid)


def disconnect(cid: str) -> None:
    t = _tokens(cid)
    if t and t.get("refresh_token"):
        try:
            with _http(15) as h:
                h.post(REVOKE_URL, params={"token": t["refresh_token"]})
        except httpx.HTTPError:
            pass  # sem internet: o arquivo local é apagado do mesmo jeito
    for name in (f"token_{cid}.json", f"pending_{cid}.json"):
        (_dir() / name).unlink(missing_ok=True)


def _api(cid: str, method: str, url: str, *, params=None, json_body=None, content=None, headers=None, timeout: float = 60.0) -> httpx.Response:
    """Chamada autenticada; se o token vencer no meio, renova uma vez e repete."""
    for attempt in (0, 1):
        h = {"Authorization": f"Bearer {access_token(cid) if attempt == 0 else _refresh(cid)}", **(headers or {})}
        try:
            with _http(timeout) as c:
                r = c.request(method, url, params=params, json=json_body, content=content, headers=h)
        except httpx.HTTPError as e:
            raise YouTubeError("Não consegui falar com o YouTube. Confira a internet da andes.") from e
        if r.status_code != 401 or attempt:
            break
    if r.status_code >= 400:
        raise YouTubeError(_explain(r))
    return r


# --------------------------------------------------------------------------- canal e vídeos
def channel_info(cid: str) -> dict:
    items = _api(cid, "GET", f"{API}/channels", params={"part": "snippet,statistics", "mine": "true"}).json().get("items") or []
    if not items:
        raise YouTubeError("a conta Google conectada não tem um canal do YouTube")
    it = items[0]
    st, sn = it.get("statistics", {}), it.get("snippet", {})
    return {"id": it["id"], "title": sn.get("title", ""), "thumb": ((sn.get("thumbnails") or {}).get("default") or {}).get("url", ""),
            "subs": int(st.get("subscriberCount", 0)), "subs_hidden": bool(st.get("hiddenSubscriberCount")), "views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0))}


def videos_info(cid: str, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        r = _api(cid, "GET", f"{API}/videos", params={"part": "snippet,status,statistics", "id": ",".join(ids[i:i + 50])}).json()
        for it in r.get("items", []):
            st, sn, stat = it.get("status", {}), it.get("snippet", {}), it.get("statistics", {})
            out[it["id"]] = {"title": sn.get("title", ""), "published_at": sn.get("publishedAt"), "privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt"),
                             "upload_status": st.get("uploadStatus"), "rejection": st.get("rejectionReason"), "views": int(stat.get("viewCount", 0)),
                             "likes": int(stat.get("likeCount", 0)), "comments": int(stat.get("commentCount", 0))}
    return out


def to_rfc3339(local_iso: str, tz_name: str = "America/Sao_Paulo") -> str:
    """'2026-11-24T18:00' (hora do Brasil) -> '2026-11-24T21:00:00Z' (o formato que o YouTube pede)."""
    from zoneinfo import ZoneInfo
    d = dt.datetime.fromisoformat(local_iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo(tz_name))
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- envio (resumable)
def _query_offset(c: httpx.Client, session: str, size: int):
    r = c.put(session, content=b"", headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"})
    if r.status_code in (200, 201):
        return r
    rng = r.headers.get("Range")
    return int(rng.split("-")[1]) + 1 if rng else 0


def upload_video(cid: str, path, *, title: str, description: str, tags: list[str], privacy: str = "private", publish_at: str | None = None, category: str = "27",
                 language: str = "pt-BR", synthetic: bool = False, progress=None) -> dict:
    """Envia o MP4 em pedaços e devolve o recurso do vídeo. Com `publish_at`, o vídeo vai privado e o YouTube o publica na hora marcada."""
    size = os.path.getsize(path)
    if privacy not in ("private", "unlisted", "public"):
        raise YouTubeError("privacidade inválida")
    body = {"snippet": {"title": title[:100], "description": description[:5000], "tags": tags, "categoryId": category, "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": {"privacyStatus": "private" if publish_at else privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": bool(synthetic)}}
    if publish_at:
        body["status"]["publishAt"] = publish_at
    init = _api(cid, "POST", f"{UPLOAD_API}/videos", params={"uploadType": "resumable", "part": "snippet,status"}, json_body=body,
                headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"})
    session = init.headers.get("Location")
    if not session:
        raise YouTubeError("o YouTube não abriu a sessão de envio")
    offset, fails = 0, 0
    with open(path, "rb") as f, _http(600) as c:
        while True:
            f.seek(offset)
            chunk = f.read(CHUNK)
            end = offset + len(chunk) - 1
            try:
                r = c.put(session, content=chunk, headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{size}", "Content-Type": "video/mp4"})
            except httpx.HTTPError:
                r = None
            if r is not None and r.status_code in (200, 201):
                if progress:
                    progress(1.0)
                return r.json()
            if r is not None and r.status_code == 308:
                rng = r.headers.get("Range")
                offset = int(rng.split("-")[1]) + 1 if rng else 0
                fails = 0
                if progress:
                    progress(min(0.99, offset / size))
                continue
            if r is not None and r.status_code < 500:
                raise YouTubeError(_explain(r))
            fails += 1                     # rede caiu ou erro 5xx: pergunta até onde o YouTube recebeu e continua dali
            if fails > 5:
                raise YouTubeError("o envio falhou várias vezes seguidas. Tente de novo mais tarde.")
            time.sleep(min(30, 2 ** fails) if TRANSPORT is None else 0)
            res = _query_offset(c, session, size)
            if isinstance(res, httpx.Response):
                return res.json()
            offset = res


def set_thumbnail(cid: str, video_id: str, path) -> None:
    with open(path, "rb") as f:
        data = f.read()
    _api(cid, "POST", f"{UPLOAD_API}/thumbnails/set", params={"videoId": video_id, "uploadType": "media"}, content=data, headers={"Content-Type": "image/jpeg"}, timeout=120)


# --------------------------------------------------------------------------- métricas (Analytics API)
def report(cid: str, start: str, end: str, metrics: str, dimensions: str = "", filters: str = "", sort: str = "", max_results: int | None = None) -> list[dict]:
    p = {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": metrics}
    for k, v in (("dimensions", dimensions), ("filters", filters), ("sort", sort), ("maxResults", max_results)):
        if v:
            p[k] = v
    j = _api(cid, "GET", ANALYTICS, params=p).json()
    names = [h["name"] for h in j.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in j.get("rows", [])]


def _try(fn, avisos: list, texto: str):
    try:
        return fn()
    except YouTubeError as e:
        avisos.append(f"{texto}: {e}")
        return None


def sync_snapshot(cid: str, today: dt.date | None = None) -> dict:
    """Lê o canal e junta o que o dashboard mostra. O que a API recusar vira um aviso, não derruba a leitura inteira."""
    today = today or dt.date.today()
    iso = lambda d: d.isoformat()  # noqa: E731
    avisos: list[str] = []
    info = channel_info(cid)
    base = "views,estimatedMinutesWatched,subscribersGained,subscribersLost"
    serie = report(cid, iso(today - dt.timedelta(days=89)), iso(today), base, dimensions="day", sort="day")
    longos = _try(lambda: report(cid, iso(today - dt.timedelta(days=364)), iso(today), "estimatedMinutesWatched,views", filters="creatorContentType==VIDEO_ON_DEMAND"), avisos, "Horas só de vídeos longos")
    inclui_shorts = longos is None
    if longos is None:
        longos = report(cid, iso(today - dt.timedelta(days=364)), iso(today), "estimatedMinutesWatched,views")
    shorts = _try(lambda: report(cid, iso(today - dt.timedelta(days=89)), iso(today), "views", filters="creatorContentType==SHORTS"), avisos, "Visualizações de Shorts")
    vids = report(cid, iso(today - dt.timedelta(days=89)), iso(today), "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
                  dimensions="video", sort="-views", max_results=50)
    ctr = _try(lambda: report(cid, iso(today - dt.timedelta(days=89)), iso(today), "videoThumbnailImpressions,videoThumbnailImpressionsClickRate", dimensions="video",
                              sort="-videoThumbnailImpressions", max_results=50), avisos, "Taxa de cliques")
    rate = {r["video"]: r for r in (ctr or [])}
    mx = max([float(r.get("videoThumbnailImpressionsClickRate") or 0) for r in rate.values()] or [0])
    scale = 100.0 if 0 < mx <= 1.0 else 1.0                         # a API pode devolver proporção ou porcentagem: normaliza para %
    meta = videos_info(cid, [v["video"] for v in vids]) if vids else {}
    videos = []
    for v in vids:
        m, k = meta.get(v["video"], {}), rate.get(v["video"], {})
        videos.append({"id": v["video"], "titulo": m.get("title", v["video"]), "privacidade": m.get("privacy"), "publicado_em": m.get("published_at"), "views": int(v.get("views") or 0),
                       "minutos": float(v.get("estimatedMinutesWatched") or 0), "duracao_media_s": float(v.get("averageViewDuration") or 0), "assistido_pct": float(v.get("averageViewPercentage") or 0),
                       "curtidas": int(v.get("likes") or 0), "comentarios": int(v.get("comments") or 0), "inscritos": int(v.get("subscribersGained") or 0),
                       "impressoes": int(k.get("videoThumbnailImpressions") or 0) if k else None,
                       "ctr": round(float(k.get("videoThumbnailImpressionsClickRate") or 0) * scale, 2) if k else None})
    return {"taken": time.time(), "canal": info, "serie_90d": [{"dia": r["day"], "views": int(r["views"]), "minutos": float(r["estimatedMinutesWatched"]), "inscritos_ganhos": int(r["subscribersGained"]),
                                                                  "inscritos_perdidos": int(r["subscribersLost"])} for r in serie],
            "horas_longos_365": round(float((longos[0].get("estimatedMinutesWatched") if longos else 0) or 0) / 60, 1), "horas_inclui_shorts": inclui_shorts,
            "shorts_views_90d": int(shorts[0].get("views") or 0) if shorts else None, "videos": videos, "avisos": avisos}


def worst_videos(videos: list[dict], n: int = 3, min_views: int = 50) -> list[dict]:
    """Os piores vídeos com público mínimo, com o diagnóstico da revisão semanal: CTR baixo = título e miniatura; retenção baixa = abertura."""
    pool = [v for v in videos if v["views"] >= min_views and v.get("privacidade") in (None, "public")] or [v for v in videos if v["views"] >= min_views] or videos
    out = []
    for v in sorted(pool, key=lambda x: (x["ctr"] if x.get("ctr") is not None else 99, x["assistido_pct"]))[:n]:
        if v.get("ctr") is not None and v["ctr"] < 4:
            dx = "CTR baixo: gere novos títulos e miniaturas."
        elif v["assistido_pct"] < 30:
            dx = "Pouca gente assiste até o fim: reescreva a abertura e corte enrolação."
        else:
            dx = "Bom número, mas poucas visitas: o tema pode ter pouca procura."
        out.append({**v, "diagnostico": dx})
    return out
