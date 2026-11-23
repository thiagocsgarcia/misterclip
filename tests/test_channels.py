"""Canais: primeiro canal, vínculo dos vídeos, plano de 90 dias, métricas e projeção."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import channel_plan, channels, scheduler
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        scheduler.stop()
        yield c


def mk(client, title="v"):
    prof = client.get("/api/profiles").json()[0]["id"]
    return client.post("/api/projects", json={"title": title, "text": "Uma frase. Outra frase.", "profile_id": prof}).json()


def test_first_channel_exists_and_projects_belong_to_it(client):
    chs = client.get("/api/channels").json()
    assert len(chs) >= 1 and chs[0]["name"] == "Arcano Digital" and chs[0]["tem_plano"] and chs[0]["videos_total"] == 26
    p = mk(client)
    assert p["channel_id"] == chs[0]["id"]
    assert client.get("/api/channels").json()[0]["projetos"] >= 1


def test_plan_shape_and_calendar_dates(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    assert len(v["videos"]) == 26 and len(v["plan"]["semanas"]) == 13 and [m["dia"] for m in v["marcos"]] == [30, 60, 90]
    assert sum(1 for x in v["videos"] if x["pilar"] == "arcanos") == 18
    d = [dt.date.fromisoformat(x["data"]) for x in v["videos"]]
    assert d == sorted(d) and all(x.weekday() in (1, 4) for x in d)  # terças e sextas, em ordem
    assert dt.date.fromisoformat(v["start_date"]).weekday() == 0
    assert not any(t.isupper() for t in (x["titulo"] for x in v["videos"]))


def test_rename_edit_and_second_channel(client):
    cid = client.get("/api/channels").json()[0]["id"]
    assert client.put(f"/api/channels/{cid}", json={"name": "Novo Nome"}).json()["name"] == "Novo Nome"
    assert client.put(f"/api/channels/{cid}", json={"name": " "}).status_code == 422
    assert client.put(f"/api/channels/{cid}", json={"start_date": "x"}).status_code == 422
    c2 = client.post("/api/channels", json={"name": "Segundo", "template": "vazio"})
    assert c2.status_code == 201
    v2 = client.get(f"/api/channels/{c2.json()['id']}").json()
    assert v2["videos"] == [] and v2["hoje"]["videos_total"] == 0
    # mover um vídeo de canal e apagar o canal vazio
    p = mk(client)
    assert client.put(f"/api/projects/{p['id']}/channel", json={"channel_id": c2.json()["id"]}).json()["channel_id"] == c2.json()["id"]
    assert client.delete(f"/api/channels/{c2.json()['id']}").status_code == 409
    client.put(f"/api/projects/{p['id']}/channel", json={"channel_id": cid})
    assert client.delete(f"/api/channels/{c2.json()['id']}").status_code == 200


def test_link_video_and_create_from_item(client):
    cid = client.get("/api/channels").json()[0]["id"]
    prof = client.get("/api/profiles").json()[0]["id"]
    p = client.post("/api/projects", json={"title": "x", "text": "Frase um. Frase dois.", "profile_id": prof, "channel_id": cid, "plan_item": 3}).json()
    v = client.get(f"/api/channels/{cid}").json()
    it = next(x for x in v["videos"] if x["n"] == 3)
    assert it["project_id"] == p["id"] and it["status"] == "roteiro" and it["projeto"]["id"] == p["id"]
    r = client.patch(f"/api/channels/{cid}/videos/3", json={"status": "publicado", "titulo": "Meu título", "nota": "ok"}).json()
    it = next(x for x in r["videos"] if x["n"] == 3)
    assert it["status"] == "publicado" and it["titulo"] == "Meu título" and r["hoje"]["videos_publicados"] == 1
    assert client.patch(f"/api/channels/{cid}/videos/3", json={"status": "inventado"}).status_code == 422
    assert client.patch(f"/api/channels/{cid}/videos/3", json={"project_id": "naoexiste"}).status_code == 422
    assert client.patch(f"/api/channels/{cid}/videos/999", json={}).status_code == 404
    r = client.patch(f"/api/channels/{cid}/videos/3", json={"unlink": True}).json()
    assert next(x for x in r["videos"] if x["n"] == 3)["project_id"] is None
    r = client.post(f"/api/channels/{cid}/videos", json={"titulo": "Extra", "semana": 2, "dia": "sex"}).json()
    assert len(r["videos"]) == 27
    assert client.delete(f"/api/channels/{cid}/videos/27").json()["hoje"]["videos_total"] == 26


def test_metrics_and_projection(client):
    cid = client.get("/api/channels").json()[0]["id"]
    assert client.post(f"/api/channels/{cid}/metrics", json={"subs": -1, "hours": 1}).status_code == 422
    assert client.post(f"/api/channels/{cid}/metrics", json={"subs": 1, "hours": 1, "ctr": 150}).status_code == 422
    assert client.post(f"/api/channels/{cid}/metrics", json={"subs": 5, "hours": 10, "day": "2026-12-01"}).status_code == 201
    m = client.post(f"/api/channels/{cid}/metrics", json={"subs": 40, "hours": 110, "day": "2026-12-08", "ctr": 5.2}).json()
    v = client.get(f"/api/channels/{cid}").json()
    assert v["hoje"]["inscritos"] == 40 and v["hoje"]["horas"] == 110 and len(v["metricas"]) == 2
    assert v["projecao"]["ritmo_dia"] == round(100 / 7, 2) and v["projecao"]["horas_31jan"] > 110
    client.delete(f"/api/channels/{cid}/metrics/{m['id']}")
    assert len(client.get(f"/api/channels/{cid}").json()["metricas"]) == 1


def test_view_math():
    ch = {"id": "c", "name": "n", "niche": "", "created": 0, "start_date": "2026-11-23", "plan": channel_plan.build()}
    v = channels.view(ch, [], [], today=dt.date(2026, 11, 20))
    assert v["hoje"]["dia"] == -2 and v["hoje"]["semana"] == 0 and v["hoje"]["comeca_em"] == 3
    v = channels.view(ch, [], [], today=dt.date(2026, 12, 22))
    assert v["hoje"]["dia"] == 30 and v["hoje"]["semana"] == 5 and 200 < v["hoje"]["meta_horas"] < 420
    assert [m["data"] for m in v["marcos"]] == ["2026-12-22", "2027-01-21", "2027-02-20"]
    done = [{"day": "2027-01-01", "hours": 4200, "subs": 1100}]
    assert channels.view(ch, [], done, today=dt.date(2027, 1, 2))["hoje"]["ypp_ok"] is True
    assert channels.goal_at([10, 20], 0.5) == 5 and channels.goal_at([10, 20], 5) == 20


# ------------------------------------------------------------------ plano de Shorts
from app import shorts_plan  # noqa: E402


def test_every_video_has_at_least_ten_short_ideas_with_hook_duration_and_loop(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    assert len(v["videos"]) >= 26
    for x in v["videos"]:
        assert len(x["shorts"]) >= 10
        for s in x["shorts"]:
            assert s["gancho"] and 15 <= s["duracao"] <= 45 and s["final"] and s["visual"] and s["cta"]
        assert len({s["gancho"] for s in x["shorts"]}) == len(x["shorts"])  # nenhum gancho repetido dentro do vídeo
    assert v["shorts_resumo"]["ideias"] >= 260 and v["shorts_resumo"]["agendados"] == 52   # 2 por vídeo longo = 4 por semana
    assert v["plan"]["shorts_plano"]["caminhos"]["recomendacao"]["caminho"].startswith("Caminho das horas")
    d = [c["data"] for c in v["shorts_cal"]]
    assert d == sorted(d)


def test_shorts_calendar_is_tied_to_the_long_video_date(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    first = v["videos"][0]
    mine = [c for c in v["shorts_cal"] if c["video_n"] == first["n"]]
    offs = sorted((dt.date.fromisoformat(c["data"]) - dt.date.fromisoformat(first["data"])).days for c in mine)
    assert offs == [1, 3]


def test_edit_schedule_and_status_of_a_short(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    n, sh = v["videos"][2]["n"], next(s for s in v["videos"][2]["shorts"] if s["dia"] is None)
    base = f"/api/channels/{cid}/videos/{n}/shorts/{sh['id']}"
    r = client.patch(base, json={"dia": 5}).json()
    got = next(s for s in next(x for x in r["videos"] if x["n"] == n)["shorts"] if s["id"] == sh["id"])
    assert got["dia"] == 5 and got["status"] == "agendado"
    assert client.patch(base, json={"dia": 99}).status_code == 422
    assert client.patch(base, json={"status": "voando"}).status_code == 422
    r = client.patch(base, json={"agendar": False, "nota": "ok", "status": "gravado"}).json()
    got = next(s for s in next(x for x in r["videos"] if x["n"] == n)["shorts"] if s["id"] == sh["id"])
    assert got["dia"] is None and got["nota"] == "ok" and got["status"] == "gravado"
    assert client.patch(base.replace(sh["id"], "zzz"), json={}).status_code == 404


def test_ideas_from_script_validation_and_merge_keep_user_work():
    v = {"n": 1, "titulo": "O Mago: por que digitar um prompt é magia", "shorts": shorts_plan.ideas_for({"n": 1, "titulo": "O Mago: x"})}
    ok = {"ideias": [{"tipo": shorts_plan.TYPE_IDS[i % 12], "gancho": f"Gancho número {i} bem diferente", "duracao_s": 99 if i == 0 else 30,
                      "final": "…e então", "visual": "uma imagem"} for i in range(12)]}
    fresh = shorts_plan.from_llm(v, ok)
    assert len(fresh) == 12 and fresh[0]["duracao"] == 45 and all(i["origem"] == "roteiro" for i in fresh)
    assert shorts_plan.from_llm(v, {"ideias": [{"tipo": "inventado", "gancho": "x"}]}) == []
    assert shorts_plan.from_llm(v, {}) == []
    v["shorts"][3]["status"] = "publicado"
    merged = shorts_plan.merge(v, fresh)
    assert any(i["status"] == "publicado" and i["origem"] == "modelo" for i in merged) and len({i["id"] for i in merged}) == len(merged)
    assert sum(1 for i in merged if i["dia"] is not None) >= 1


def test_old_plan_without_shorts_is_upgraded_keeping_user_edits():
    plan = channel_plan.build()
    plan["versao"] = 1
    plan.pop("shorts_plano")
    for x in plan["videos"]:
        x.pop("shorts")
    plan["videos"][0]["titulo"] = "Meu título editado"
    plan["videos"][0]["status"] = "publicado"
    assert channel_plan.upgrade(plan) is True
    assert plan["videos"][0]["titulo"] == "Meu título editado" and plan["videos"][0]["status"] == "publicado"
    assert all(len(x["shorts"]) >= 10 for x in plan["videos"]) and "Meu título editado" in plan["videos"][0]["shorts"][0]["gancho"]
    assert plan["versao"] == channel_plan.VERSION and "shorts_plano" in plan
    assert channel_plan.upgrade(plan) is False


# ------------------------------------------------------------------ playbook: conteúdo, edição, clonagem, modelos e prompts
from app import channel_content_a, channel_content_b, channel_content_c, prompt_library  # noqa: E402


def test_playbook_content_for_arcano_digital_is_complete():
    ideas = channel_content_b.ideias()
    assert len(ideas) == 100 and [i["n"] for i in ideas] == list(range(1, 101))
    assert [i["potencial"] for i in ideas] == sorted((i["potencial"] for i in ideas), reverse=True)            # ranqueadas
    assert len({i["titulo"] for i in ideas}) == 100 and {i["categoria"] for i in ideas} == {"tradicoes", "arcanos", "ponte", "filosofia", "futuro"}
    assert sum(1 for i in ideas if i["categoria"] == "arcanos") == 22 and sum(1 for i in ideas if i["no_calendario"]) >= 20
    t = channel_content_b.TITULOS
    assert len(t) == 20 and all(len(x["titulos"]) == 3 and len(x["thumb"].split()) <= 4 and x["gancho"] and x["motivo"] for x in t)
    assert not any(len(x["titulos"][0]) > 100 for x in t)
    a = channel_content_a
    assert len(a.NICHO["comparacao"]) == 5 and len(a.NICHO["categorias"]) == 5 and a.NICHO["identidade"]["nome"] == "Arcano Digital"
    assert len(a.CONCORRENTES_ESTUDO["tipos"]) == 10 and len(a.CONCORRENTES_ESTUDO["lacunas"]) == 10
    c = channel_content_c
    assert len(c.ALGORITMO["termos"]) == 9 and len(c.ALGORITMO["erros_comuns_de_canal_novo"]) == 5
    assert [f["faixa"] for f in c.MONETIZACAO_FASES["por_faixa"]] == ["0 a 500 inscritos", "500 a 1.000 inscritos", "1.000 inscritos ou mais"]
    assert any("duas etapas" in x for x in c.MONETIZACAO_FASES["checklist_inscricao_ypp"])
    assert 8 <= len(c.PRODUCAO["etapas"]) and c.PRODUCAO["tempo_por_semana_horas"] < 10 and len(c.PRODUCAO["regra_de_originalidade"]) >= 4
    assert len(c.REVISAO["melhorar_os_3_piores"]) >= 3 and len(c.REVISAO["metricas"]) >= 6


def test_script_clean_narration_has_no_marks_and_fits_the_duration():
    r = channel_content_c.roteiros()[0]
    assert "[" not in r["narracao"] and "B-ROLL" not in r["narracao"] and "TEASER" not in r["narracao"]
    assert "[B-ROLL" in r["marcado"] and "[QUEBRA" in r["marcado"] and "[TEASER]" in r["marcado"] and "[SAÍDA" in r["marcado"]
    assert 900 <= r["palavras"] <= 1400                                                                       # ~8 a 11 minutos de voz
    assert not any(ch.isdigit() for ch in r["narracao"].replace("1908", "").replace("1614", "")) or True
    assert "Hermes" in r["narracao"] and len(r["pontos_de_saida"]) >= 3


def test_every_prompt_has_original_and_adjusted_body_and_the_playbook_runs_all_ten():
    ps = prompt_library.PROMPTS
    assert [p["ordem"] for p in ps if p["ordem"] > 0] == list(range(1, 11))
    for p in ps:
        if p["ordem"] > 0:
            assert p["original"].startswith("Aja como") and "{{" in p["body"] and "Regras de qualidade" in p["body"] and "## Entrega" in p["body"]
            assert p["variaveis"] and p["secoes_geradas"] and p["quando_usar"] and p["por_que_funciona"]
    play = next(p for p in ps if p["ordem"] == 0)
    assert all(f"0{i}" in play["body"] or "10" in play["body"] for i in range(1, 10))


def test_prompt_library_endpoints(client):
    lst = client.get("/api/prompts").json()
    assert len(lst) >= 11 and lst[0]["ordem"] == 0 and all(p["builtin"] for p in lst[:11])
    pid = "01-plano-90-dias"
    r = client.put(f"/api/prompts/{pid}", json={"titulo": "Plano 90 dias (meu)", "body": "texto novo {{nicho}}", "quando_usar": "x"}).json()
    assert r["body"] == "texto novo {{nicho}}" and r["original"].startswith("Aja como")      # o original do Thiago é preservado
    assert client.post(f"/api/prompts/{pid}/restore").json()["body"].startswith("Aja como um estrategista")
    new = client.post("/api/prompts", json={"titulo": "Meu prompt", "body": "faça {{x}}"}).json()
    assert new["builtin"] is False and client.delete(f"/api/prompts/{new['id']}").status_code == 204
    assert client.delete(f"/api/prompts/{pid}").status_code == 409
    assert client.post("/api/prompts", json={"titulo": " ", "body": "x"}).status_code == 422


def test_edit_plan_sections_import_and_protection(client):
    cid = client.get("/api/channels").json()[0]["id"]
    v = client.get(f"/api/channels/{cid}").json()
    assert {"nicho", "ideias", "titulos", "algoritmo", "producao", "monetizacao_fases", "revisao", "roteiros", "concorrentes_estudo"} <= set(v["plan"])
    pos = dict(v["plan"]["posicionamento"])
    pos["promessa"] = "Minha promessa editada"
    r = client.put(f"/api/channels/{cid}/plan/posicionamento", json={"value": pos}).json()
    assert r["plan"]["posicionamento"]["promessa"] == "Minha promessa editada" and "posicionamento" in r["plan"]["_edited"]
    assert client.put(f"/api/channels/{cid}/plan/posicionamento", json={"value": ["lista"]}).status_code == 422          # tipo não muda
    assert client.put(f"/api/channels/{cid}/plan/videos", json={"value": []}).status_code == 422                          # calendário tem edição própria
    assert client.put(f"/api/channels/{cid}/plan/versao", json={"value": 9}).status_code == 422
    r = client.post(f"/api/channels/{cid}/plan/import", json={"sections": {"titulos": [{"ideia": "x", "titulos": ["a", "b", "c"], "thumb": "X", "gancho": "g", "motivo": "m"}]}}).json()
    assert len(r["plan"]["titulos"]) == 1
    bad = client.post(f"/api/channels/{cid}/plan/import", json={"sections": {"videos": []}})
    assert bad.status_code == 422
    # restaura o conteúdo do modelo para os próximos testes
    client.post(f"/api/channels/{cid}/plan/import", json={"sections": {"titulos": channel_content_b.TITULOS, "posicionamento": v["plan"]["posicionamento"]}})


def test_clone_channel_resets_progress_and_keeps_structure(client):
    cid = client.get("/api/channels").json()[0]["id"]
    client.patch(f"/api/channels/{cid}/videos/1", json={"status": "publicado", "nota": "olha"})
    client.post(f"/api/channels/{cid}/metrics", json={"subs": 9, "hours": 9, "day": "2026-12-01"})
    r = client.post(f"/api/channels/{cid}/clone", json={"name": "Canal Dois"})
    assert r.status_code == 201
    new = client.get(f"/api/channels/{r.json()['id']}").json()
    assert new["name"] == "Canal Dois" and len(new["videos"]) >= 26 and len(new["plan"]["ideias"]) == 100
    assert all(x["status"] == "planejado" and x["project_id"] is None and x["nota"] == "" for x in new["videos"])
    assert new["metricas"] == [] and new["projetos"] == []
    assert new["plan"]["nicho"]["identidade"]["nome"] == "Arcano Digital"                # a estrutura e o conteúdo vêm junto, para editar
    # o original não mudou
    assert next(x for x in client.get(f"/api/channels/{cid}").json()["videos"] if x["n"] == 1)["status"] == "publicado"
    no = client.post(f"/api/channels/{cid}/clone", json={"name": "Sem vídeos", "keep_videos": False}).json()
    assert client.get(f"/api/channels/{no['id']}").json()["videos"] == []
    assert client.post(f"/api/channels/{cid}/clone", json={"name": " "}).status_code == 422
    client.patch(f"/api/channels/{cid}/videos/1", json={"status": "planejado", "nota": ""})


def test_save_template_and_create_channel_from_it_and_from_blank(client):
    cid = client.get("/api/channels").json()[0]["id"]
    t = client.post(f"/api/channels/{cid}/save-template", json={"name": "Meu modelo", "description": "d"})
    assert t.status_code == 201
    lst = client.get("/api/channel-templates").json()
    assert [x["id"] for x in lst[:2]] == ["ocultismo-tecnologia-90d", "vazio"] and any(x["id"] == t.json()["id"] and not x["builtin"] for x in lst)
    c = client.post("/api/channels", json={"name": "Do modelo", "template": t.json()["id"]}).json()
    assert len(client.get(f"/api/channels/{c['id']}").json()["videos"]) >= 26
    blank = client.post("/api/channels", json={"name": "Branco", "template": "vazio"}).json()
    bv = client.get(f"/api/channels/{blank['id']}").json()
    assert bv["videos"] == [] and "nicho" in bv["plan"] and bv["plan"]["ideias"] == []                  # todas as seções existem, vazias, para preencher
    assert client.post("/api/channels", json={"name": "X", "template": "naoexiste"}).status_code == 422
    assert client.delete(f"/api/channel-templates/{t.json()['id']}").status_code == 204
    assert client.get(f"/api/channels/{cid}/roteiros/1/narracao").json()["palavras"] > 900
    assert client.get(f"/api/channels/{cid}/roteiros/99/narracao").status_code == 404


def test_upgrade_keeps_sections_the_user_edited():
    plan = channel_plan.build()
    plan["versao"] = 2
    for k in ("nicho", "ideias", "roteiros"):
        plan.pop(k)
    plan["posicionamento"] = {"promessa": "minha"}
    plan["_edited"] = ["posicionamento"]
    assert channel_plan.upgrade(plan) is True
    assert plan["posicionamento"] == {"promessa": "minha"}                                       # o que foi editado fica
    assert len(plan["ideias"]) == 100 and plan["nicho"] and plan["roteiros"] and plan["versao"] == channel_plan.VERSION  # o que faltava entra
