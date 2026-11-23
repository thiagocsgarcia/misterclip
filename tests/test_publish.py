"""Publicar: título/descrição/capítulos/tags (regras do YouTube) e miniatura 1280x720 até 2 MB."""
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, metadata, thumbnail
from app.main import app


def scenes(n, seconds=10.0, real=True):
    return [{"id": f"s{i:03d}", "n": i + 1, "text": f"Texto da cena {i + 1}.", "est_seconds": seconds, "duration": seconds if real else None}
            for i in range(n)]


# ------------------------------------------------------------------------ capítulos
def test_chapters_follow_youtube_rules():
    items = scenes(60)                                   # 10 min
    ch = metadata.plan_chapters(items)
    assert 5 <= len(ch) <= 8 and ch[0]["scene"] == "s000"
    titled = [{"scene": c["scene"], "title": f"Parte {i}"} for i, c in enumerate(ch)]
    res = metadata.resolve_chapters(titled, items)
    assert res[0][0] == 0.0 and len(res) >= 3
    assert all(b[0] - a[0] >= metadata.CHAPTER_MIN for a, b in zip(res, res[1:]))   # mínimo de 10 s entre capítulos
    assert metadata.plan_chapters(scenes(3)) == []       # 30 s: curto demais
    assert metadata.plan_chapters(scenes(14)) == []      # 140 s dá só 2 capítulos de ~90 s: o YouTube exige 3
    assert metadata.plan_chapters([]) == []


def test_chapter_times_follow_the_current_timeline():
    items = scenes(60)
    ch = [{"scene": c["scene"], "title": "x"} for c in metadata.plan_chapters(items)]
    before = metadata.resolve_chapters(ch, items)
    items[0]["duration"] += 30                           # a 1ª cena ficou 30 s mais longa: tudo depois desloca 30 s
    after = metadata.resolve_chapters(ch, items)
    assert after[1][0] == before[1][0] + 30 and after[0][0] == 0.0


def test_timestamps_and_final_description():
    assert metadata.fmt_ts(0) == "0:00" and metadata.fmt_ts(75) == "1:15" and metadata.fmt_ts(3725) == "1:02:05"
    items = scenes(60)
    chapters = [{"scene": c["scene"], "title": f"Capítulo {i + 1}"} for i, c in enumerate(metadata.plan_chapters(items))]
    yt = {"intro": "Gancho.\n\nO que você vai ver.", "chapters": chapters, "hashtags": ["#a", "#b", "#c"]}
    d = metadata.final_description(yt, items)
    lines = d.split("\n")
    assert lines[0] == "Gancho." and "0:00 Capítulo 1" in d and d.endswith("#a #b #c")
    assert len(metadata.final_description({"intro": "x" * 9000}, items)) == metadata.MAX_DESC


def test_cleaning_respects_limits():
    tags = metadata.clean_tags(["#Filosofia", "filosofia", "  ocultismo  ", "x" * 80, "inteligência artificial e filosofia da mente"] + [f"tag número {i}" for i in range(200)])
    assert tags[0] == "filosofia" and tags[1] == "ocultismo" and len(set(tags)) == len(tags)
    assert not any(t.startswith("xxxx") or t.startswith("inteligência artificial e") for t in tags)       # longas demais: descartadas, não cortadas
    assert all(len(t) <= 30 for t in tags) and sum(len(t) + 1 for t in tags) <= metadata.MAX_TAGS_CHARS
    assert metadata.clean_hashtags(["Alquimia IA", "#filosofia", "filosofia", "a-b", "quatro", "cinco"]) == ["#AlquimiaIA", "#filosofia", "#ab"]
    assert metadata.clean_hashtags(["#historiadainteligenciaartificial", "#ia"]) == ["#ia"]               # hashtag gigante some


def test_apply_edit_validates_title_and_keeps_only_known_chapters():
    yt = {"title": "Ok", "chapters": [{"scene": "s1", "title": "A"}, {"scene": "s2", "title": "B"}]}
    with pytest.raises(ValueError, match="máximo do YouTube"):
        metadata.apply_edit(yt, {"title": "x" * 101})
    with pytest.raises(ValueError):
        metadata.apply_edit(yt, {"title": "   "})
    out = metadata.apply_edit(yt, {"title": "Novo", "tags": "um, dois,\num", "chapters": [{"scene": "s2", "title": "Beta"}, {"scene": "zzz", "title": "?"}]})
    assert out["title"] == "Novo" and out["tags"] == ["um", "dois"] and out["chapters"] == [{"scene": "s2", "title": "Beta"}]


# ----------------------------------------------------------------------- miniatura
def test_thumbnail_is_1280x720_under_2mb_and_text_changes_pixels(tmp_path):
    base = tmp_path / "b.png"
    Image.effect_noise((1500, 900), 80).convert("RGB").save(base)                    # ruído: o pior caso para o tamanho do JPEG
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    thumbnail.compose(str(base), "", str(a))
    thumbnail.compose(str(base), "A grande obra alquímica e a IA", str(b))
    for f in (a, b):
        im = Image.open(f)
        assert im.size == (1280, 720) and im.format == "JPEG" and f.stat().st_size <= thumbnail.MAX_BYTES
    left = (0, 100, 640, 620)
    assert Image.open(a).crop(left).tobytes() != Image.open(b).crop(left).tobytes()  # o texto aparece à esquerda


# ------------------------------------------------------------------ fluxo pela API
TEXT = " ".join(f"Frase de teste número {i} para formar cenas longas e variadas do roteiro." for i in range(120))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def test_metadata_and_thumbnail_flow(client):
    pid = client.post("/api/projects", json={"title": "Publicar", "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    assert client.get(f"/api/projects/{pid}/publish").json()["youtube"] is None
    assert client.put(f"/api/projects/{pid}/metadata", json={"title": "x"}).status_code == 409        # nada gerado ainda
    assert client.get(f"/api/projects/{pid}/thumbnail/download").status_code == 409
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"

    assert wait(client, client.post(f"/api/projects/{pid}/metadata/generate").json())["status"] == "done"
    pub = client.get(f"/api/projects/{pid}/publish").json()
    yt = pub["youtube"]
    assert len(yt["titles"]) == 5 and yt["title"] == yt["titles"][0] and yt["tags"] and len(yt["hashtags"]) == 3
    assert "0:00" in pub["description_final"] and len(pub["chapters_resolved"]) >= 3 and pub["chapters_resolved"][0]["t"] == "0:00"
    assert " ".join(yt["hashtags"]) in pub["description_final"]          # o aviso editorial do canal vem depois das hashtags

    edited = client.put(f"/api/projects/{pid}/metadata", json={"title": "Meu título", "tags": "a, b, c",
                                                               "chapters": [{"scene": c["scene"], "title": f"Cap {i}"} for i, c in enumerate(yt["chapters"])]})
    assert edited.status_code == 200 and edited.json()["youtube"]["title"] == "Meu título" and "Cap 1" in edited.json()["description_final"]
    assert client.put(f"/api/projects/{pid}/metadata", json={"title": "x" * 150}).status_code == 422

    assert wait(client, client.post(f"/api/projects/{pid}/thumbnail/generate", json={"count": 3}).json())["status"] == "done"
    th = client.get(f"/api/projects/{pid}/publish").json()["thumbnail"]
    assert [v["i"] for v in th["variants"]] == [1, 2, 3] and th["selected"] == 1
    base_dir = config.DATA / "projects" / pid
    for v in th["variants"]:
        assert Image.open(base_dir / v["file"]).size == (1280, 720)

    before = (base_dir / th["variants"][1]["file"]).read_bytes()
    comp = client.post(f"/api/projects/{pid}/thumbnail/compose", json={"index": 2, "text": "OUTRO TEXTO"})
    assert comp.status_code == 200 and (base_dir / th["variants"][1]["file"]).read_bytes() != before
    assert comp.json()["thumbnail"]["ver"] > th["ver"] and comp.json()["thumbnail"]["variants"][1]["text"] == "OUTRO TEXTO"
    assert client.post(f"/api/projects/{pid}/thumbnail/compose", json={"index": 9, "text": "x"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/thumbnail/select", json={"index": 3}).json()["thumbnail"]["selected"] == 3
    r = client.get(f"/api/projects/{pid}/thumbnail/download")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and len(r.content) <= thumbnail.MAX_BYTES


def test_failed_side_job_does_not_change_the_video_status(client, monkeypatch):
    from app.pipeline.backends.fake import FakeBackend

    pid = client.post("/api/projects", json={"title": "Lateral", "text": TEXT, "profile_id": "cinematico-sombrio"}).json()["id"]
    for step in ("plan", "prepare"):
        assert wait(client, client.post(f"/api/projects/{pid}/{step}").json())["status"] == "done"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "storyboard"
    monkeypatch.setattr(FakeBackend, "llm_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM fora do ar (simulado)")))
    j = wait(client, client.post(f"/api/projects/{pid}/metadata/generate").json())
    assert j["status"] == "failed" and "LLM fora do ar" in j["message"]
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "storyboard" and "LLM fora do ar" in proj["meta"]["last_error"]          # status intacto, erro registrado


def test_thumbnail_text_is_limited_to_four_words():
    assert metadata._thumb_text("Alquimia e IA: O espelho do conhecimento") == "Alquimia e IA O"
    assert metadata._thumb_text("  Vai ser ótimo!  ") == "Vai ser ótimo"
    assert metadata._thumb_text(None) == ""
