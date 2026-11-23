"""Cálculos de um canal: dia do plano, vídeos do calendário, progresso e projeção de horas. Sem acesso a banco."""
import datetime as dt

from . import channel_plan

STATUS = ["planejado", "roteiro", "produzindo", "pronto", "publicado"]
SHORT_STATUS = ["ideia", "agendado", "gravado", "publicado"]
YPP_HOURS, YPP_SUBS = 4000, 1000
CUTOFF = dt.date(2027, 2, 1)  # novas regras do Programa de Parcerias


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def goal_at(curve: list[float], week_float: float) -> float:
    """Meta acumulada no meio de uma semana (interpola entre o fim da semana anterior e o fim desta)."""
    if week_float <= 0:
        return 0.0
    i = int(week_float)
    if i >= len(curve):
        return float(curve[-1])
    prev = curve[i - 1] if i >= 1 else 0.0
    return prev + (curve[i] - prev) * (week_float - i)


def projection(metrics: list[dict], today: dt.date) -> dict:
    """Ritmo recente (últimas duas leituras com pelo menos 3 dias de distância) e quando chegaria a 4.000 h."""
    out = {"ritmo_dia": None, "horas_31jan": None, "data_4000": None, "dias_para_4000": None, "base_de": None, "base_ate": None}
    pts = sorted(((_d(m["day"]), float(m["hours"] or 0)) for m in metrics), key=lambda x: x[0])
    if len(pts) < 2:
        return out
    last = pts[-1]
    prev = next((p for p in reversed(pts[:-1]) if (last[0] - p[0]).days >= 3), None)
    if prev is None:
        return out
    rate = (last[1] - prev[1]) / (last[0] - prev[0]).days
    out.update(ritmo_dia=round(rate, 2), base_de=prev[0].isoformat(), base_ate=last[0].isoformat())
    days_to_cut = max(0, (dt.date(2027, 1, 31) - last[0]).days)
    out["horas_31jan"] = round(last[1] + max(rate, 0) * days_to_cut)
    if last[1] >= YPP_HOURS:
        out["dias_para_4000"], out["data_4000"] = 0, last[0].isoformat()
    elif rate > 0:
        days = int((YPP_HOURS - last[1]) / rate) + 1
        out["dias_para_4000"], out["data_4000"] = days, (last[0] + dt.timedelta(days=days)).isoformat()
    return out


def view(ch: dict, projects: list[dict], metrics: list[dict], today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    plan = ch["plan"]
    start = _d(ch["start_date"])
    by_id = {p["id"]: p for p in projects}
    videos = []
    for v in plan.get("videos", []):
        v = dict(v)
        v["data"] = channel_plan.item_date(start, v).isoformat()
        p = by_id.get(v.get("project_id"))
        v["projeto"] = {"id": p["id"], "titulo": p["title"], "status": p["status"]} if p else None
        v["status_auto"] = v["status"]
        if p and v["status"] in ("planejado", "roteiro", "produzindo"):
            v["status_auto"] = "pronto" if p["status"] == "done" else ("produzindo" if p["status"] not in ("draft",) else "roteiro")
        videos.append(v)
    cal = []
    for v in videos:
        for sh in v.get("shorts", []):
            if sh.get("dia") is not None:
                d = _d(v["data"]) + dt.timedelta(days=int(sh["dia"]))
                cal.append({"id": sh["id"], "video_n": v["n"], "video": v["titulo"], "data": d.isoformat(), "semana": (d - start).days // 7 + 1,
                            "tipo": sh["tipo"], "nome": sh["nome"], "gancho": sh["gancho"], "duracao": sh["duracao"], "final": sh["final"],
                            "visual": sh.get("visual", ""), "status": sh["status"], "origem": sh.get("origem", "modelo")})
    cal.sort(key=lambda x: (x["data"], x["video_n"]))
    all_sh = [sh for v in videos for sh in v.get("shorts", [])]
    shorts_resumo = {"ideias": len(all_sh), "agendados": len(cal), "publicados": sum(1 for x in all_sh if x["status"] == "publicado"),
                     "gravados": sum(1 for x in all_sh if x["status"] in ("gravado", "publicado")), "do_roteiro": sum(1 for x in all_sh if x.get("origem") == "roteiro")}
    day = (today - start).days + 1
    week = min(13, max(1, (day - 1) // 7 + 1)) if day >= 1 else 0
    due = [v for v in videos if _d(v["data"]) <= today]
    published = [v for v in videos if v["status"] == "publicado"]
    curve = plan.get("curva") or {}
    wf = max(0.0, (day - 1) / 7.0 + (1 / 7)) if day >= 1 else 0.0
    last = metrics[-1] if metrics else None
    horas = float(last["hours"]) if last else 0.0
    subs = int(last["subs"]) if last else 0
    goal_h = goal_at(curve["horas"], wf) if curve else None
    goal_s = goal_at(curve["inscritos"], wf) if curve else None
    floor = curve.get("piso", 0.25) if curve else 0.25
    proj = projection(metrics, today)
    days_to_cut = (dt.date(2027, 1, 31) - today).days
    marcos = []
    for m in plan.get("marcos", []):
        d = start + dt.timedelta(days=m["dia"] - 1)
        n_pub = sum(1 for v in videos if v["status"] == "publicado" and _d(v["data"]) <= d)
        marcos.append({**m, "data": d.isoformat(), "dias_restantes": (d - today).days,
                       "atual": {"videos": len(published), "inscritos": subs, "horas": horas}, "videos_planejados": m["videos"], "publicados_ate_la": n_pub})
    return {
        "id": ch["id"], "name": ch["name"], "niche": ch["niche"], "start_date": ch["start_date"], "created": ch["created"],
        "plan": {k: v for k, v in plan.items() if k not in ("videos", "marcos")},
        "videos": videos, "marcos": marcos, "metricas": metrics, "shorts_cal": cal, "shorts_resumo": shorts_resumo,
        "hoje": {
            "data": today.isoformat(), "dia": day, "semana": week, "comeca_em": (-day + 1) if day < 1 else 0, "fim_do_plano": day > 91,
            "videos_publicados": len(published), "videos_previstos_ate_hoje": len(due), "videos_total": len(videos),
            "horas": horas, "inscritos": subs, "meta_horas": round(goal_h) if goal_h is not None else None,
            "meta_inscritos": round(goal_s) if goal_s is not None else None,
            "piso_horas": round(goal_h * floor) if goal_h is not None else None, "piso_inscritos": round(goal_s * floor) if goal_s is not None else None,
            "faltam_horas": max(0, YPP_HOURS - horas), "faltam_inscritos": max(0, YPP_SUBS - subs),
            "dias_ate_31jan": days_to_cut, "antes_das_novas_regras": days_to_cut >= 0,
            "ypp_ok": horas >= YPP_HOURS and subs >= YPP_SUBS,
        },
        "projecao": proj,
        "projetos": [{"id": p["id"], "title": p["title"], "status": p["status"]} for p in projects],
    }
