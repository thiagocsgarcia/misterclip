"""Configuração do MisterClip (tudo por variáveis de ambiente)."""
import os
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent

# fake = backend de teste (sem GPU); real = ComfyUI + Kokoro + Whisper (andes)
MODE = os.getenv("MC_MODE", "fake")

DATA = pathlib.Path(os.getenv("MC_DATA", str(BASE / "data")))
PROFILES_BUILTIN = pathlib.Path(os.getenv("MC_PROFILES", str(BASE / "profiles")))
PROFILES_USER = DATA / "profiles"
MODELS = pathlib.Path(os.getenv("MC_MODELS", "/models"))
MUSIC_DIR = DATA / "music"
CLIP_UPLOADS = DATA / "clip_uploads"  # músicas enviadas no "Novo clipe", antes de o clipe existir
WEB = BASE / "web"

COMFY_URL = os.getenv("MC_COMFY_URL", "http://127.0.0.1:8188")
OLLAMA_URL = os.getenv("MC_OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("MC_LLM_MODEL", "qwen3:14b")

# Aviso opcional ao fim de cada job (POST JSON). Vazio = desligado.
NOTIFY_URL = os.getenv("MC_NOTIFY_URL", "")

# Token opcional (cookie `mc_token`, cabeçalho Bearer ou ?token=). Vazio = sem autenticação.
TOKEN = os.getenv("MC_TOKEN", "")

# "Esqueci o token": o servidor envia o token para este e-mail (nunca para um endereço vindo do pedido). Precisa de um SMTP seu.
TOKEN_EMAIL = os.getenv("MC_TOKEN_EMAIL", "")
SMTP_HOST = os.getenv("MC_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("MC_SMTP_PORT", "587"))
SMTP_USER = os.getenv("MC_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("MC_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("MC_SMTP_FROM", "") or SMTP_USER

_default_size = "640x360" if MODE == "fake" else "1920x1080"
VIDEO_W, VIDEO_H = (int(v) for v in os.getenv("MC_VIDEO_SIZE", _default_size).lower().split("x"))
FPS = 24

# Narração
DEFAULT_VOICE = os.getenv("MC_VOICE", "pm_alex")
DEFAULT_SPEED = float(os.getenv("MC_SPEED", "0.85"))
SCENE_TARGET_SECONDS = float(os.getenv("MC_SCENE_SECONDS", "9"))
SCENE_PAUSE_SECONDS = 0.45
WORDS_PER_SECOND = 2.75  # estimativa com speed 0.85 (~165 palavras/min)
