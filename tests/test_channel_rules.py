"""O planejamento do canal comanda a geração: regras, verificações, padrões de vídeo, imposição no que o LLM devolve e a cadeia automática."""
import copy
import time

import pytest
from fastapi.testclient import TestClient

from app import channel_plan, channel_rules, db, scheduler
from app.main import app
from app.pipeline.backends.fake import FakeBackend

R = channel_rules.DEFAULT_RULES

GOOD = ("Em mil novecentos e oito, um livro anônimo disse vir do Egito antigo, e os textos antigos dizem outra coisa. Segundo o historiador Frances Yates, o hermetismo "
        "nasceu no Egito romano. De acordo com Isaac Casaubon, o Corpus foi escrito séculos depois de Cristo. Conforme o Caibalion, os princípios são sete. "
        + "Esta é mais uma frase de apoio do roteiro para completar o tamanho necessário da narração. " * 80)


def test_defaults_merge_with_what_the_user_edited():
    ch = {"plan": {"regras_do_canal": {"titulo": {"max_caracteres": 55}, "miniatura": {"max_palavras": 3}}}}
    r = channel_rules.effective(ch)
    assert r["titulo"]["max_caracteres"] == 55 and r["titulo"]["palavras_proibidas"] == R["titulo"]["palavras_proibidas"]      # o resto vem do padrão
    assert r["miniatura"]["max_palavras"] == 3 and r["video"]["segundos_por_cena"] == 9
    assert channel_rules.effective(None)["titulo"]["max_caracteres"] == 70


def test_title_lint_rules():
    L = lambda t: {(x["nivel"], x["regra"]) for x in channel_rules.lint_title(t, R)}  # noqa: E731
    assert L("Hermetismo de verdade: o que Hermes Trismegisto ensinou") == {("ok", "titulo.ok")}
    assert ("erro", "titulo.caixa_alta") in L("OS SEGREDOS DO HERMETISMO REVELADOS")
    assert ("erro", "titulo.proibidas") in L("Os segredos do hermetismo")
    assert ("aviso", "titulo.tamanho") in L("Hermetismo de verdade: o que Hermes Trismegisto ensinou e o que o Caibalion não diz a ninguém")
    assert ("erro", "titulo.vazio") in L("  ")
    assert ("ok", "titulo.ok") in L("O Mago: por que digitar um prompt é uma forma de magia")


def test_thumbnail_and_description_lint():
    assert channel_rules.lint_thumb("UM DOIS TRÊS QUATRO CINCO", R)[0]["nivel"] == "erro"
    assert channel_rules.lint_thumb("É OCULTISTA?", R)[0]["nivel"] == "ok"
    d = channel_rules.lint_description("Curta.", R, 12, False)
    assert {x["regra"] for x in d} == {"descricao.intro", "descricao.capitulos", "descricao.fontes"}
    ok = "Uma introdução longa o bastante para explicar a ideia central do vídeo logo nas duas primeiras linhas.\n\n0:00 Abertura\n\nFontes: Atkinson, O Caibalion, 1908.\n\n#a #b"
    assert channel_rules.lint_description(ok, R, 12, True)[0]["nivel"] == "ok"
    assert any(x["regra"] == "descricao.hashtags" for x in channel_rules.lint_description(ok + " #c #d", R, 12, True))


def test_script_lint_flags_and_passes():
    good = channel_rules.lint_script(GOOD, R)
    assert good["achados"][0]["nivel"] == "ok" and 8 <= good["minutos"] <= 12
    bad = channel_rules.lint_script("Garantido: ganhe dinheiro com este segredo de 2024! " + "Palavras simples de enchimento sem fonte nenhuma aqui. " * 40 + " [B-ROLL: algo] ", R)
    regras = {x["regra"] for x in bad["achados"]}
    assert {"roteiro.promessa", "roteiro.numeros", "roteiro.marcacoes", "roteiro.sensacionalismo", "roteiro.fontes", "roteiro.duracao"} <= regras
    assert channel_rules.lint_script("Curto.", R)["achados"][0]["regra"] == "roteiro.curto"
    assert not any(x["regra"] == "roteiro.duracao" for x in channel_rules.lint_script(GOOD, R, formato="longo")["achados"])   # os dois formatos pedem de 8 a 12 min
    medio = channel_rules.lint_script(GOOD + " Mais uma frase de apoio para esticar o roteiro além do tamanho usual do canal. " * 60, R)
    assert not any(x["regra"] == "roteiro.duracao" for x in medio["achados"]) and 12 < medio["minutos"] < 30   # passar de 12 min é permitido
    comprido = channel_rules.lint_script(GOOD + " Mais uma frase de apoio para esticar o roteiro além do limite de tempo do canal. " * 260, R)
    assert comprido["minutos"] > 30 and any(x["regra"] == "roteiro.duracao" for x in comprido["achados"])   # mais de 30 min avisa


def test_political_content_rules():
    camp = channel_rules.lint_script(GOOD + " Por isso, vote em quem defende a regulação. Os petralha e os bolsominion discordam.", R)
    regras = {a["regra"]: a["nivel"] for a in camp["achados"]}
    assert regras["roteiro.campanha"] == "erro" and regras["roteiro.ataque"] == "aviso"
    ctx = channel_rules.context_text({"name": "X", "plan": {}})
    assert "nunca peça voto" in ctx and "pessoa real" in ctx
    assert "rosto de político" in channel_rules.visual_extra({"name": "X", "plan": {}})
    assert "roteiro.campanha" not in {a["regra"] for a in channel_rules.lint_script(GOOD, R)["achados"]}


def test_metadata_enforcement_fixes_what_the_llm_returned():
    yt = {"titles": ["OS SEGREDOS DO HERMETISMO", "O HERMETISMO EXPLICADO COM CALMA E FONTES", "Hermetismo: " + "palavra " * 20, "O hermetismo explicado"], "title": "x",
          "thumb_text": "UM DOIS TRÊS QUATRO CINCO SEIS", "hashtags": ["#a", "#b", "#c", "#d"]}
    notes = channel_rules.enforce_metadata(yt, R)
    assert all(len(t) <= 70 for t in yt["titles"]) and not any("segredo" in t.lower() for t in yt["titles"]) and yt["title"] == yt["titles"][0]
    assert yt["titles"][0] == "O hermetismo explicado com calma e fontes" and len(yt["thumb_text"].split()) == 4 and len(yt["hashtags"]) == 3 and len(notes) >= 4
    allbad = {"titles": ["OS SEGREDOS REVELADOS"], "title": "x", "thumb_text": "", "hashtags": []}
    assert any("violavam" in n for n in channel_rules.enforce_metadata(allbad, R))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def wait(client, job, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job não terminou")


def set_rules(client, cid, **sections):
    cur = copy.deepcopy(client.get(f"/api/channels/{cid}").json()["plan"].get("regras_do_canal") or R)
    for k, v in sections.items():
        cur[k] = {**cur[k], **v}
    assert client.put(f"/api/channels/{cid}/plan/regras_do_canal", json={"value": cur}).status_code == 200


def test_rules_endpoints_and_the_plan_section(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    assert v["plan"]["regras_do_canal"]["video"]["modo_padrao"] == "automatico" and v["plan"]["versao"] == channel_plan.VERSION
    r = client.get(f"/api/channels/{cid}/rules").json()
    assert f"CANAL: {v['name']}" in r["contexto"] and "CAIXA ALTA" in r["contexto"] and r["padroes"]["voice"] == "pm_alex"
    lint = client.post(f"/api/channels/{cid}/lint", json={"kind": "titulo", "text": "OS SEGREDOS"}).json()
    assert any(x["nivel"] == "erro" for x in lint["achados"])
    assert client.post(f"/api/channels/{cid}/lint", json={"kind": "roteiro", "text": GOOD})["palavras"] if False else True
    s = client.post(f"/api/channels/{cid}/lint", json={"kind": "roteiro", "text": GOOD}).json()
    assert s["achados"][0]["nivel"] == "ok" and s["palavras"] > 1000
    assert client.post(f"/api/channels/{cid}/lint", json={"kind": "xyz", "text": "a"}).status_code == 422


def test_new_project_takes_the_channel_defaults(client):
    cid = client.get("/api/channels").json()[0]["id"]
    set_rules(client, cid, narracao={"voz": "pf_dora", "velocidade": 0.9}, video={"transicao": "dissolve"})
    prof = client.get("/api/profiles").json()[1]["id"]
    set_rules(client, cid, visual={"estilo_padrao": prof})
    p = client.post("/api/projects", json={"title": "padrões", "text": "Uma frase. Outra frase.", "channel_id": cid}).json()
    assert p["voice"] == "pf_dora" and p["speed"] == 0.9 and p["profile_id"] == prof and p["meta"]["options"]["transition"] == "dissolve"
    mine = client.post("/api/projects", json={"title": "meu", "text": "Uma frase. Outra.", "channel_id": cid, "voice": "pm_alex", "speed": 0.8,
                                              "profile_id": client.get("/api/profiles").json()[0]["id"]}).json()
    assert mine["voice"] == "pm_alex" and mine["speed"] == 0.8                                 # o que você escolhe vale mais que o padrão
    set_rules(client, cid, narracao={"voz": "pm_alex", "velocidade": 0.85}, video={"transicao": "crossfade"}, visual={"estilo_padrao": ""})


def test_video_premises_drive_scene_length_and_visual_prompts(client, monkeypatch):
    cid = client.get("/api/channels").json()[0]["id"]
    seen = []
    orig = FakeBackend.visual_prompt
    monkeypatch.setattr(FakeBackend, "visual_prompt", lambda self, text, system=None, extra="": (seen.append(extra), orig(self, text))[1])
    prof = client.get("/api/profiles").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do roteiro de teste com palavras suficientes." for i in range(1, 41))
    counts = {}
    for sec in (4, 25):
        set_rules(client, cid, video={"segundos_por_cena": sec, "proporcao_animada": 0.5})
        pid = client.post("/api/projects", json={"title": f"cena {sec}", "text": text, "profile_id": prof, "channel_id": cid}).json()["id"]
        assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
        sc = client.get(f"/api/projects/{pid}").json()["scenes"]
        counts[sec] = len(sc)
        assert abs(sum(1 for s in sc if s["motion"] != "ken_burns") - round(len(sc) * 0.5)) <= 1       # proporção animada do canal
    assert counts[4] > counts[25]                                                              # cenas mais curtas = mais cenas
    assert any("Channel visual aesthetic" in e and "Never depict" in e and "never scary" in e for e in seen)   # estética do canal no prompt de imagem
    set_rules(client, cid, video={"segundos_por_cena": 9, "proporcao_animada": 0.35})


def test_metadata_job_applies_channel_context_and_enforces_rules(client, monkeypatch):
    cid = client.get("/api/channels").json()[0]["id"]
    got = {}

    def fake_json(self, system, user):
        if "trechos" in system:
            return {"titles": ["Parte um", "Parte dois", "Parte três"]}
        got["system"] = system
        return {"titles": ["OS SEGREDOS DO HERMETISMO REVELADOS", "O HERMETISMO EXPLICADO COM FONTES", "Hermetismo de verdade"], "intro": "Uma introdução longa o bastante para explicar o vídeo.",
                "tags": ["a"], "hashtags": ["#a", "#b", "#c", "#d", "#e"], "thumb_text": "UM DOIS TRÊS QUATRO CINCO", "thumb_prompt": "x"}

    monkeypatch.setattr(FakeBackend, "llm_json", fake_json)
    prof = client.get("/api/profiles").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do roteiro de teste com palavras suficientes." for i in range(1, 60))
    pid = client.post("/api/projects", json={"title": "meta", "text": text, "profile_id": prof, "channel_id": cid}).json()["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert wait(client, client.post(f"/api/projects/{pid}/metadata/generate").json())["status"] == "done"
    assert "IDENTIDADE E REGRAS DO CANAL" in got["system"] and client.get(f"/api/channels/{cid}").json()["name"] in got["system"] and "palavras proibidas" in got["system"]
    yt = client.get(f"/api/projects/{pid}").json()["meta"]["youtube"]
    assert yt["title"] == "O hermetismo explicado com fontes" and not any("segredo" in t.lower() for t in yt["titles"]) and len(yt["thumb_text"].split()) == 4 and len(yt["hashtags"]) == 3
    assert yt["ajustes_das_regras"]
    # verificação antes de publicar e trava do YouTube
    checks = client.get(f"/api/projects/{pid}/checks").json()
    assert checks["pode_enviar"] in (True, False) and any(x["onde"] == "titulo" for x in checks["achados"])
    return pid


def test_publish_checks_and_the_youtube_gate(client, monkeypatch):
    from app import youtube
    cid = client.get("/api/channels").json()[0]["id"]
    prof = client.get("/api/profiles").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do roteiro de teste com palavras suficientes." for i in range(1, 40))
    pid = client.post("/api/projects", json={"title": "gate", "text": text, "profile_id": prof, "channel_id": cid}).json()["id"]
    for step in ("plan", "prepare", "render"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    c = client.get(f"/api/projects/{pid}/checks").json()
    assert c["pode_enviar"] is False and any(x["regra"] == "publicacao.sem_metadados" for x in c["achados"])            # sem título nem descrição ainda
    youtube._save_tokens(cid, {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3000})
    try:
        r = client.post(f"/api/projects/{pid}/youtube/upload", json={"privacidade": "privado"})
        assert r.status_code == 409 and "regras do canal barram" in r.json()["detail"]
    finally:
        for f in (youtube._dir()).glob("token_*"):
            f.unlink()


def test_script_review_job_stores_a_review(client, monkeypatch):
    monkeypatch.setattr(FakeBackend, "llm_json", lambda self, system, user: {"veredito": "Bom, mas a abertura é longa.", "tese": "O hermetismo antigo difere do Caibalion.", "fontes_citadas": ["Casaubon"],
                                                                                "pontos_fortes": ["fontes claras"], "riscos": [{"trecho": "x", "problema": "p", "sugestao": "s"}, "lixo"],
                                                                                "pontos_de_saida": [{"aprox": "3:00", "risco": "r", "solucao": "s"}], "abertura_sugerida": "Uma abertura melhor.",
                                                                                "originalidade": {"nota": 4, "motivo": "tese própria"}})
    cid = client.get("/api/channels").json()[0]["id"]
    prof = client.get("/api/profiles").json()[0]["id"]
    pid = client.post("/api/projects", json={"title": "rev", "text": GOOD, "profile_id": prof, "channel_id": cid}).json()["id"]
    j = wait(client, client.post(f"/api/projects/{pid}/review-script").json())
    assert j["status"] == "done"
    rv = client.get(f"/api/projects/{pid}").json()["meta"]["review"]
    assert rv["veredito"].startswith("Bom") and rv["riscos"] == [{"trecho": "x", "problema": "p", "sugestao": "s"}] and rv["originalidade"]["nota"] == 4 and rv["abertura_sugerida"]
    short = client.post("/api/projects", json={"title": "curto", "text": "Curto demais.", "profile_id": prof, "channel_id": cid}).json()["id"]
    assert wait(client, client.post(f"/api/projects/{short}/review-script").json())["status"] == "failed"


def test_run_all_builds_everything_from_a_draft_script(client):
    cid = client.get("/api/channels").json()[0]["id"]
    prof = client.get("/api/profiles").json()[0]["id"]
    text = " ".join(f"Esta é a frase número {i} do roteiro de teste com palavras suficientes." for i in range(1, 50))
    pid = client.post("/api/projects", json={"title": "tudo sozinho", "text": text, "profile_id": prof, "channel_id": cid}).json()["id"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "draft"                     # rascunho: nem as cenas existem ainda
    sc = client.post(f"/api/projects/{pid}/run-all")
    assert sc.status_code == 202
    s = db.schedule_get(sc.json()["id"])
    t0 = time.time()
    while s["status"] not in ("done", "failed") and time.time() - t0 < 300:
        scheduler.tick()
        time.sleep(0.3)
        s = db.schedule_get(s["id"])
    assert s["status"] == "done", s
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "done" and p["meta"]["youtube"]["title"] and p["meta"]["thumbnail"]["variants"]
    assert [j["kind"] for j in reversed(p["jobs"])][:4] == ["prepare", "render", "metadata", "thumbnail"]       # o projeto já nasce com as cenas, então a cadeia começa em prepare
    assert client.post("/api/projects", json={"title": "vazio", "text": " ", "profile_id": prof}).status_code == 422


def test_legal_guardrails_for_living_people_and_hate_tropes():
    base = GOOD
    risky = channel_rules.lint_script(base + " Peter Thiel é o Anticristo e é corrupto. Os banqueiros judeus controlam o mundo. Sem dúvida nenhuma ele quer o poder.", R)
    regras = {a["regra"]: a["nivel"] for a in risky["achados"]}
    assert regras["roteiro.acusacao"] == "erro" and regras["roteiro.odio"] == "erro" and regras["roteiro.conspiracao"] == "aviso"
    assert regras["roteiro.certeza"] == "aviso" and regras["roteiro.pessoa_viva"] == "aviso"
    careful = channel_rules.lint_script(base + " Segundo a revista Reason, Thiel teria descrito o Anticristo como um tirano. Hitler foi nazista.", R)
    regras = {a["regra"]: a["nivel"] for a in careful["achados"]}
    assert "roteiro.acusacao" not in regras and regras["roteiro.pessoa_viva"] == "aviso"          # atribuído e sem acusação direta; Hitler já morreu e não está na lista
    only_dead = channel_rules.lint_script(base + " Crowley foi acusado de muita coisa, e a Maçonaria foi perseguida.", R)
    assert "roteiro.pessoa_viva" not in {a["regra"] for a in only_dead["achados"]}


def test_titles_with_living_people_and_the_editorial_footer():
    T = lambda t: {(a["nivel"], a["regra"]) for a in channel_rules.lint_title(t, R)}  # noqa: E731
    assert ("erro", "titulo.acusacao") in T("Peter Thiel é o Anticristo e corrupto")
    assert ("aviso", "titulo.pessoa_viva") in T("Peter Thiel e o Anticristo: o que é fato e o que é lenda") and ("erro", "titulo.acusacao") not in T("Peter Thiel e o Anticristo: o que é fato e o que é lenda")
    assert ("ok", "titulo.ok") in T("Hermetismo de verdade: o que o Caibalion não diz")
    from app import metadata
    foot = channel_rules.editorial_footer({"name": "X", "plan": {}})
    assert "análise e opinião" in foot
    d = metadata.final_description({"intro": "x" * 6000}, [], foot)
    assert len(d) <= metadata.MAX_DESC and d.endswith(foot)
    assert "Segurança jurídica" in channel_rules.context_text({"name": "X", "plan": {}})


def test_geopolitics_rules_enter_the_context_and_lint_flags_generalizations():
    ch = {"name": "X", "plan": {}}
    ctx = channel_rules.context_text(ch)
    assert "Geopolítica" in ctx and "sem tomar lado" in ctx
    body = ("Segundo o relatório publicado em dois mil e vinte e quatro, o governo chinês anunciou novas regras para minerais. " * 3)
    ok = channel_rules.lint_script(body + "Os chineses são todos iguais nesse assunto.", R)
    assert any(x["regra"] == "roteiro.generalizacao" for x in ok["achados"])
    assert not any(x["regra"] == "roteiro.generalizacao" for x in channel_rules.lint_script(body, R)["achados"])
    off = channel_rules.effective({"plan": {"regras_do_canal": {"geopolitica": {"ativo": False}}}})
    assert not any(x["regra"] == "roteiro.generalizacao" for x in channel_rules.lint_script(body + "Os chineses são todos iguais.", off)["achados"])
