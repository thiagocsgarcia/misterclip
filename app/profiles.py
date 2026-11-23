"""Perfis de estilo visual: embutidos (somente leitura) + os criados pelo usuário."""
import copy
import json
import re
import unicodedata

from . import config

REQUIRED = ("name", "style_prompt")


class ProfileError(ValueError):
    pass


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "perfil"


def _read_dir(path, builtin: bool) -> dict[str, dict]:
    out = {}
    if not path.exists():
        return out
    for f in sorted(path.glob("*.json")):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        p["id"] = p.get("id") or f.stem
        p["builtin"] = builtin
        out[p["id"]] = p
    return out


def all_profiles() -> dict[str, dict]:
    profiles = _read_dir(config.PROFILES_BUILTIN, True)
    profiles.update(_read_dir(config.PROFILES_USER, False))
    return profiles


def list_profiles() -> list[dict]:
    return list(all_profiles().values())


def get(profile_id: str) -> dict | None:
    return all_profiles().get(profile_id)


def require(profile_id: str) -> dict:
    p = get(profile_id)
    if p is None:
        raise ProfileError(f"perfil inexistente: {profile_id}")
    return p


def validate(p: dict) -> dict:
    for k in REQUIRED:
        if not str(p.get(k, "")).strip():
            raise ProfileError(f"campo obrigatório ausente: {k}")
    params = p.setdefault("params", {})
    params.setdefault("width", 1344)
    params.setdefault("height", 768)
    params.setdefault("steps", 4)
    params.setdefault("cfg", 1.0)
    if params["width"] % 16 or params["height"] % 16:
        raise ProfileError("width e height devem ser múltiplos de 16")
    p.setdefault("base_model", "flux1-schnell-fp8")
    motion = p.setdefault("motion", {})
    motion.setdefault("default", "ken_burns")
    motion.setdefault("animated_ratio", 0.35)
    motion.setdefault("clip_engine", "ltx")
    if motion["clip_engine"] not in ("ltx", "wan"):
        raise ProfileError("motion.clip_engine deve ser 'ltx' ou 'wan'")
    if not 0 <= float(motion["animated_ratio"]) <= 1:
        raise ProfileError("motion.animated_ratio deve estar entre 0 e 1")
    p.setdefault("finishing", {})
    p.setdefault("captions", {})
    return p


def _save(p: dict) -> dict:
    config.PROFILES_USER.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in p.items() if k != "builtin"}
    (config.PROFILES_USER / f"{p['id']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    p["builtin"] = False
    return p


def create(data: dict) -> dict:
    p = validate(copy.deepcopy(data))
    base = slugify(p.get("id") or p["name"])
    pid, i = base, 2
    existing = all_profiles()
    while pid in existing:
        pid, i = f"{base}-{i}", i + 1
    p["id"] = pid
    p.setdefault("description", "")
    return _save(p)


def update(profile_id: str, data: dict) -> dict:
    cur = require(profile_id)
    if cur["builtin"]:
        raise ProfileError("perfis embutidos não podem ser editados; duplique-o primeiro")
    p = validate({**cur, **data, "id": profile_id})
    return _save(p)


def duplicate(profile_id: str, new_name: str | None = None) -> dict:
    src = copy.deepcopy(require(profile_id))
    src.pop("id", None)
    src.pop("builtin", None)
    src["name"] = new_name or f"{src['name']} (cópia)"
    return create(src)


def delete(profile_id: str) -> None:
    cur = require(profile_id)
    if cur["builtin"]:
        raise ProfileError("perfis embutidos não podem ser apagados")
    (config.PROFILES_USER / f"{profile_id}.json").unlink(missing_ok=True)
