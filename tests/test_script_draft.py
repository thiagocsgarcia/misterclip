"""Rascunho de roteiro, números por extenso na voz, pronúncias e conferência das imagens."""
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import channel_rules, imagecheck, ptnum, scheduler, script_draft
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def wait(client, job, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("job não terminou")


# ----------------------------------------------------------------------- números e pronúncias
@pytest.mark.parametrize("src,out", [
    ("Em 2025 houve", "Em dois mil e vinte e cinco houve"),
    ("nasceu em 1908", "nasceu em mil novecentos e oito"),
    ("R$ 81 milhões", "oitenta e um milhões de reais"),
    ("US$ 2 bilhões", "dois bilhões de dólares"),
    ("10% a mais", "dez por cento a mais"),
    ("1.250 pessoas", "mil duzentos e cinquenta pessoas"),
    ("3,5 vezes", "três vírgula cinco vezes"),
    ("1.000.000 de casos", "um milhão de casos"),
    ("100 e 101", "cem e cento e um"),
    ("sem número nenhum", "sem número nenhum"),
])
def test_numbers_by_extension(src, out):
    assert ptnum.for_tts(src) == out


def test_pronunciations_replace_whole_words_only():
    assert ptnum.for_tts("Peter Thiel e Thielmann", {"Thiel": "Tíl"}) == "Peter Tíl e Thielmann"


def test_tts_receives_normalized_text_but_captions_keep_the_script(client, monkeypatch):
    from app.pipeline.backends.fake import FakeBackend
    heard = []
    orig = FakeBackend.tts
    monkeypatch.setattr(FakeBackend, "tts", lambda self, text, *a, **k: (heard.append(text), orig(self, text, *a, **k))[1])
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "num", "text": "Em 2025 a empresa recebeu 10% a mais, segundo o relatório publicado naquele ano de estudo.", "profile_id": prof}).json()["id"]
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert "dois mil e vinte e cinco" in heard[0] and "dez por cento" in heard[0]
    assert client.get(f"/api/projects/{pid}").json()["scenes"][0]["text"].startswith("Em 2025")      # o roteiro do autor não muda


# ----------------------------------------------------------------------- conferência das imagens
def test_imagecheck_flags_black_white_and_flat(tmp_path):
    for name, color, why in (("p.png", (0, 0, 0), "preta"), ("b.png", (255, 255, 255), "branca"), ("c.png", (120, 90, 60), "lisa")):
        Image.new("RGB", (64, 64), color).save(tmp_path / name)
        assert why in imagecheck.problem(str(tmp_path / name))
    img = Image.new("RGB", (64, 64), (20, 20, 20))
    for x in range(32):
        for y in range(64):
            img.putpixel((x, y), (200, 180, 150))
    img.save(tmp_path / "ok.png")
    assert imagecheck.problem(str(tmp_path / "ok.png")) is None


def test_bad_image_is_regenerated_with_another_seed(client, monkeypatch):
    from app.pipeline.backends.fake import FakeBackend
    calls = []
    orig = FakeBackend.image

    def flaky(self, prompt, profile, seed, out_png, size):
        calls.append(seed)
        if len(calls) < 3:
            Image.new("RGB", size, (0, 0, 0)).save(out_png)      # o gerador devolveu um quadro preto duas vezes
        else:
            orig(self, prompt, profile, seed, out_png, size)
    monkeypatch.setattr(FakeBackend, "image", flaky)
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "preto", "text": "Uma frase só para uma cena de teste da imagem preta que se repete.", "profile_id": prof}).json()["id"]
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    s = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert len(calls) == 3 and len(set(calls)) == 3 and not s["image_warning"]


def test_image_that_stays_bad_is_kept_with_a_warning(client, monkeypatch):
    from app.pipeline.backends.fake import FakeBackend
    monkeypatch.setattr(FakeBackend, "image", lambda self, prompt, profile, seed, out_png, size: Image.new("RGB", size, (255, 255, 255)).save(out_png))
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "branco", "text": "Outra frase de teste para uma cena cuja imagem nunca sai boa.", "profile_id": prof}).json()["id"]
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    s = client.get(f"/api/projects/{pid}").json()["scenes"][0]
    assert "branca" in s["image_warning"] and "3 tentativas" in s["image_warning"] and s["image"]


# ----------------------------------------------------------------------- rascunho de roteiro
def test_clean_removes_markup_and_spells_numbers():
    raw = "## Título\n\n- **Primeiro** ponto em 1908 [B-ROLL: mapa]\n\n1. Segundo `ponto` com 10% a mais."
    out = script_draft.clean(raw)
    assert "#" not in out and "[" not in out and "*" not in out and "`" not in out
    assert "mil novecentos e oito" in out and "dez por cento" in out and "\n\n" in out


def test_target_words_follow_the_channel_rules():
    rules = channel_rules.effective(None)
    assert script_draft.target_words(rules, "ensaio") == (1000, 1500)                  # vídeos de 8 a 12 minutos, 125 palavras por minuto
    assert script_draft.target_words(rules, "longo") == (1000, 1500)


def test_draft_is_saved_as_draft_and_never_replaces_a_real_script(client):
    cid = client.get("/api/channels").json()[0]["id"]
    plan = client.get(f"/api/channels/{cid}").json()
    have = {r["video_n"] for r in plan["plan"].get("roteiros", [])}
    n = next(v["n"] for v in plan["videos"] if v["n"] not in have)
    mine = next(iter(have), None)
    assert client.post(f"/api/channels/{cid}/videos/9999/draft").status_code == 404
    if mine is not None:                                                                  # já existe um roteiro do autor: o rascunho não o troca
        assert client.post(f"/api/channels/{cid}/videos/{mine}/draft").status_code == 409
    j = wait(client, client.post(f"/api/channels/{cid}/videos/{n}/draft").json())
    assert j["status"] == "done", j
    plan = client.get(f"/api/channels/{cid}").json()["plan"]
    r = next(x for x in plan["roteiros"] if x["video_n"] == n)
    assert r["rascunho"]["tese"] and r["rascunho"]["incertezas"] and r["marcado"].count("\n\n") >= 3
    assert "roteiros" in plan["_edited"] and j["result"]["palavras"] > 0
    assert any(x["video_n"] == mine for x in plan["roteiros"]) or mine is None             # o do autor continua lá
    again = client.post(f"/api/channels/{cid}/videos/{n}/draft")                           # um rascunho pode ser refeito
    assert again.status_code == 202 and wait(client, again.json())["status"] == "done"


# ----------------------------------------------------------------------- roteiros por ideia
def test_idea_scripts_batch_edit_and_marks(client):
    cid = client.get("/api/channels").json()[0]["id"]
    ideas = client.get(f"/api/channels/{cid}").json()["plan"]["ideias"]
    n = next(i["n"] for i in ideas if not i["roteiro"])
    assert client.get(f"/api/channels/{cid}/ideas/{n}/script").status_code == 404
    j = wait(client, client.post(f"/api/channels/{cid}/ideas/scripts", json={"ns": [n]}).json())
    assert j["status"] == "done" and j["result"]["feitos"] == [n], j
    e = client.get(f"/api/channels/{cid}/ideas/{n}/script").json()
    assert e["rascunho"]["tese"] and e["palavras"] > 0 and "[" not in e["narracao"] and e["achados"]
    marked = next(i for i in client.get(f"/api/channels/{cid}").json()["plan"]["ideias"] if i["n"] == n)["roteiro"]
    assert marked["rascunho"] and not marked["editado"]
    assert client.post(f"/api/channels/{cid}/ideas/scripts", json={"ns": [n]}).status_code == 409        # já tem: não refaz sem force
    text = "[B-ROLL: mapa antigo]\n\n" + " ".join(["Palavra"] * 60) + ".\n\n[SAÍDA: aula | entra uma cena]\n\n" + " ".join(["Outra"] * 40) + "."
    r = client.put(f"/api/channels/{cid}/ideas/{n}/script", json={"marcado": text, "revisado": True}).json()
    assert r["editado"] and "rascunho" not in r and r["palavras"] == 100 and "[B-ROLL" not in r["narracao"]
    assert r["pontos_de_saida"] == [{"ponto": "Trecho 1", "risco": "aula", "solucao": "entra uma cena"}]
    r2 = client.put(f"/api/channels/{cid}/ideas/{n}/script", json={"marcado": text, "revisado": True, "notas": {"tese": "T", "origem": "Escrito com pesquisa", "fontes": ["F1"], "incertezas": ["I1"]}}).json()
    assert r2["notas"] == {"tese": "T", "origem": "Escrito com pesquisa", "fontes": ["F1"], "incertezas": ["I1"]}
    assert client.put(f"/api/channels/{cid}/ideas/{n}/script", json={"marcado": "curto demais"}).status_code == 422
    # “o que conferir”: incertezas da pesquisa + avisos das regras, cada um com o seu estado
    v = client.get(f"/api/channels/{cid}/ideas/{n}/script").json()
    pesq = [x for x in v["conferir"] if x["origem"] == "pesquisa"]
    assert [x["texto"] for x in pesq] == ["I1"] and not pesq[0]["feito"]
    lst = next(i for i in client.get(f"/api/channels/{cid}").json()["plan"]["ideias"] if i["n"] == n)["roteiro"]
    assert lst["total"] == len(v["conferir"]) and lst["pendentes"] == lst["total"]
    after = client.post(f"/api/channels/{cid}/ideas/{n}/conferir", json={"id": pesq[0]["id"], "feito": True}).json()
    assert next(x for x in after["conferir"] if x["id"] == pesq[0]["id"])["feito"]
    lst2 = next(i for i in client.get(f"/api/channels/{cid}").json()["plan"]["ideias"] if i["n"] == n)["roteiro"]
    assert lst2["pendentes"] == lst["pendentes"] - 1
    assert client.post(f"/api/channels/{cid}/ideas/{n}/conferir", json={"id": "nao-existe"}).status_code == 404
    assert client.post(f"/api/channels/{cid}/ideas/99999/conferir", json={"id": "x"}).status_code == 404
    again = client.put(f"/api/channels/{cid}/ideas/{n}/script", json={"marcado": text, "notas": {"tese": "T", "incertezas": ["I1", "I2"]}}).json()   # editar o roteiro mantém o que já foi conferido
    assert next(x for x in again["conferir"] if x["texto"] == "I1")["feito"] and not next(x for x in again["conferir"] if x["texto"] == "I2")["feito"]
    assert client.put(f"/api/channels/{cid}/ideas/99999/script", json={"marcado": text}).status_code == 404
    # salvar a lista de ideias (mudar a situação) não grava o resumo do roteiro dentro do plano
    ideas = client.get(f"/api/channels/{cid}").json()["plan"]["ideias"]
    assert client.put(f"/api/channels/{cid}/plan/ideias", json={"value": ideas}).status_code == 200
    assert not any("roteiro" in i for i in __import__("app.db", fromlist=["x"]).channel_get(cid)["plan"]["ideias"])


def test_clean_can_keep_production_marks_on_their_own_lines():
    raw = "Frase um com 1908 [B-ROLL: mapa] segue a fala. [SAÍDA: aula | cena forte] Outra frase [nota solta]."
    out = script_draft.clean(raw, keep_marks=True)
    assert "[B-ROLL: mapa]" in out.split("\n\n") and "[SAÍDA: aula | cena forte]" in out.split("\n\n") and "nota solta" not in out
    assert "mil novecentos e oito" in out
    pts = script_draft.exit_points(out, ["Abertura"])
    assert pts == [{"ponto": "Abertura", "risco": "aula", "solucao": "cena forte"}]
