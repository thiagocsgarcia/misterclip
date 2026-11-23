"""A interface fala português simples: termos técnicos (modelos, ferramentas, siglas) não podem aparecer para o usuário."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
CANAL = "\n".join((ROOT / "web" / f).read_text(encoding="utf-8") for f in ("canal.js", "clipe.js", "plano.js", "prompts.js", "youtube.js"))
# só o texto dos templates (entre as crases): o código ao redor tem nomes de campos que não aparecem para o usuário
TEMPLATE = re.search(r"template: `(.*?)`,\n\}\)\.mount", APP, re.S).group(1) + "\n".join(re.findall(r"template: `(.*?)`,\n\};", CANAL, re.S))
# texto visível: sem tags/atributos e sem expressões {{ }} (essas são checadas pelas constantes de rótulos abaixo)
VISIBLE = re.sub(r"\{\{.*?\}\}", " ", re.sub(r"<[^>]+>", " ", TEMPLATE), flags=re.S)
_LABEL_SRC = APP[APP.index("const VOICE_LABEL"):APP.index("const guide = computed")] + APP[APP.index("const STATUS"):APP.index("const fmt =")]
# só os textos que o usuário lê: as chaves internas ('crossfade', 'ltx'...) são identificadores do código, não rótulos
# valores de objetos ({ chave: 'texto' }) e segundos elementos de pares (['chave', 'texto']); as chaves ficam de fora
LABELS = " | ".join(re.findall(r"(?:\[\s*'[a-z_]+'\s*,\s*|:\s*)'([^']+)'", _LABEL_SRC))

BANNED = ["Ken Burns", "LTX", "Wan", "crossfade", "Crossfade", "storyboard", "Storyboard", "ducking",  # "prompt" é vocabulário do próprio usuário (biblioteca de prompts)
          "renderiz", "Renderiz", "seed", "FFmpeg", "embutido", "Perfil", "perfil", "ComfyUI", "Ollama"]


def test_template_text_has_no_technical_jargon():
    found = sorted({w for w in BANNED if w in VISIBLE})
    assert not found, f"jargão na interface: {found}"


def test_label_constants_have_no_technical_jargon():
    found = sorted({w for w in BANNED if w in LABELS})
    assert not found, f"jargão nos rótulos: {found}"


def test_progress_messages_from_the_server_are_plain_portuguese():
    engine = (ROOT / "app" / "pipeline" / "engine.py").read_text(encoding="utf-8")
    msgs = " ".join(re.findall(r"progress\([^\n#]*", engine)).lower()
    for w in ("ffmpeg", "crossfade", "render final", "(wan)", "(ltx)"):
        assert w not in msgs, w


def test_every_screen_has_a_title_and_help_is_reachable():
    for marker in ("Meus vídeos", "Novo vídeo", "Estilos visuais", "Agenda de criação de vídeos", "Como o MisterClip funciona"):
        assert f"<h1>{marker}</h1>" in TEMPLATE or marker in VISIBLE, marker
    assert 'href="#/ajuda"' in TEMPLATE                                  # o "?" do cabeçalho leva à ajuda


def test_primary_actions_use_everyday_words():
    for phrase in ("Aprovar e criar o vídeo", "Preparar voz e imagens", "Tentar de novo", "Gerar outra imagem", "Juntar com a próxima"):
        assert phrase in APP, phrase


def test_static_files_are_revalidated_so_updates_reach_the_browser():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert c.get("/app.js").headers["cache-control"] == "no-cache"
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert "no-cache" not in c.get("/api/health").headers.get("cache-control", "")


def test_app_js_is_valid_es_module_syntax():
    """Um parêntese a mais na interface deixa a tela em branco; `node --check` comum não pega isso em módulos."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node não está instalado neste ambiente")
    r = subprocess.run([node, "--input-type=module", "--check"], input=APP, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:500]
