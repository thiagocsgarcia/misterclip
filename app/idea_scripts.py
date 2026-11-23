"""Roteiros por ideia (aba Ideias do canal): um arquivo por ideia, fora do plano (que ficaria pesado com ~100 roteiros)."""
import hashlib
import json
import re
import time

from . import config


def _dir(cid: str):
    d = config.DATA / "idea_scripts" / re.sub(r"[^\w-]", "", cid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(cid: str, n: int) -> dict | None:
    f = _dir(cid) / f"{int(n)}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except (OSError, ValueError):
        return None


def save(cid: str, n: int, entry: dict) -> dict:
    entry = {**entry, "n": int(n), "atualizado": time.time()}
    f = _dir(cid) / f"{int(n)}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    return entry


def item_id(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]


def items(entry: dict, achados: list[dict] | None = None) -> list[dict]:
    """O que conferir antes de gerar o vídeo: as incertezas da pesquisa e os avisos das regras do canal, cada um com o seu estado (feito ou não).
    O id vem do texto: se o texto muda, o item volta a pendente."""
    done = set(entry.get("conferido") or [])
    wanted = ([("pesquisa", t) for t in (entry.get("notas") or {}).get("incertezas") or []] + [("pesquisa", t) for t in (entry.get("rascunho") or {}).get("incertezas") or []]
              + [("regras", a["mensagem"]) for a in (achados or []) if a.get("nivel") in ("aviso", "erro")])
    out, seen = [], set()
    for origem, texto in wanted:
        i = item_id(texto)
        if texto and i not in seen:
            seen.add(i)
            out.append({"id": i, "texto": texto, "origem": origem, "feito": i in done})
    return out


def index(cid: str, lint=None) -> dict[int, dict]:
    """Resumo de cada roteiro existente (sem o texto), para marcar as ideias na lista. `lint(entry)` devolve os achados das regras do canal."""
    out = {}
    for f in _dir(cid).glob("*.json"):
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        it = items(e, lint(e) if lint else None)
        out[int(e["n"])] = {"palavras": e.get("palavras", 0), "minutos": e.get("minutos", 0), "rascunho": bool(e.get("rascunho")), "editado": bool(e.get("editado")),
                            "total": len(it), "pendentes": sum(1 for x in it if not x["feito"])}
    return out
