"""Clipe musical: análise (andamento, batidas, partes), cortes no ritmo, letra por cena e história."""
import wave

import numpy as np
import pytest

from app import musicclip as mc

SR = 22050


def make_song(path, bpm=120.0, seconds=48.0):
    """Faixa sintética: bumbo em toda batida, chimbal nos contratempos; calma, depois média, depois intensa."""
    t = np.arange(int(SR * seconds)) / SR
    y = np.zeros_like(t)
    beat = 60.0 / bpm
    for k in range(int(seconds / beat)):
        t0 = k * beat
        i0 = int(t0 * SR)
        n = int(0.18 * SR)
        tt = np.arange(n) / SR
        y[i0:i0 + n] += np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 18) * 0.9
        j0 = int((t0 + beat / 2) * SR)
        m = int(0.05 * SR)
        rng = np.random.default_rng(k)
        y[j0:j0 + m] += rng.standard_normal(m) * np.exp(-np.arange(m) / (0.01 * SR)) * 0.25
    gain = np.where(t < seconds / 6, 0.25, np.where(t < seconds / 2, 0.6, 1.0))
    y = (y * gain)
    y = (y / (np.abs(y).max() + 1e-9) * 0.9 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(y.tobytes())
    return path


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    return make_song(tmp_path_factory.mktemp("song") / "s.wav")


def test_tempo_beats_and_sections(song):
    an = mc.analyze(song)
    assert abs(an["duration"] - 48.0) < 0.2
    assert abs(an["bpm"] - 120.0) < 2.5 or abs(an["bpm"] - 60.0) < 1.5 or abs(an["bpm"] - 240.0) < 4  # oitava também é aceitável
    gaps = np.diff(an["beats"])
    assert 0.2 < gaps.mean() < 1.2 and gaps.std() < 0.02          # grade regular
    lv = [s["nivel"] for s in an["sections"]]
    assert lv[0] < lv[-1] and 0 in lv and 2 in lv                  # sobe de intensidade ao longo da faixa
    assert an["sections"][0]["start"] == 0.0 and abs(an["sections"][-1]["end"] - an["duration"]) < 0.05


def test_cuts_cover_the_whole_song_and_follow_the_beat(song):
    an = mc.analyze(song)
    for ritmo in mc.RITMOS:
        sc = mc.plan_cuts(an, ritmo)
        assert sc[0]["start"] == 0.0 and abs(sc[-1]["end"] - an["duration"]) < 0.01
        assert all(abs(a["end"] - b["start"]) < 1e-6 for a, b in zip(sc, sc[1:]))
        assert all(mc.MIN_SCENE - 0.01 <= s["duration"] <= mc.MAX_SCENE + 1.5 for s in sc)
    n = {r: len(mc.plan_cuts(an, r)) for r in mc.RITMOS}
    assert n["agitado"] > n["normal"] > n["calmo"]                 # ritmo mais agitado = mais cortes
    sc = mc.plan_cuts(an, "normal")
    beats = np.array(an["beats"])
    inner = [s["start"] for s in sc[1:]]
    assert all(np.abs(beats - t).min() < 0.01 for t in inner)      # todo corte cai numa batida


def test_motion_plan_modes():
    sc = [{"nivel": n} for n in [0, 0, 1, 2, 2, 2, 1, 2, 2, 0] * 4]
    assert set(mc.plan_motion(sc, "camera")) == {"ken_burns"}
    d = mc.plan_motion(sc, "destaques")
    assert d[0] == "ltx" and all((m == "ltx") == (s["nivel"] == 2 or i == 0) for i, (m, s) in enumerate(zip(d, sc)))
    t = mc.plan_motion(sc, "total")
    assert "ken_burns" not in t and t.count("wan") <= 6 and t[0] == "wan" and t.count("ltx") > len(t) // 2


def test_lyrics_lines_times_and_scene_assignment():
    lines = mc.lyric_lines("[Verso 1]\nEu andei pela rua vazia\n\nA lua seguia meu passo (x2)\n[Refrão]\nE o mar me chamou de volta\nPara casa")
    assert lines == ["Eu andei pela rua vazia", "A lua seguia meu passo (x2)", "E o mar me chamou de volta", "Para casa"] or len(lines) == 4
    an = {"duration": 40.0, "sections": [{"start": 0, "end": 6, "nivel": 0}, {"start": 6, "end": 36, "nivel": 2}, {"start": 36, "end": 40, "nivel": 0}]}
    times = mc.line_times_proportional(len(lines), an)
    assert times == sorted(times) and times[0] >= 5.9 and times[-1] < 36
    words = mc.words_for_lines(lines, times, 40.0)
    assert len(words) == sum(len(x.split()) for x in lines) and all(b > a for _, a, b in words)
    scenes = [{"start": float(a), "duration": 8.0} for a in range(0, 40, 8)]
    mc.attach_lyrics(scenes, lines, times, words)
    assert sum(len(s["lines"]) for s in scenes) == len(lines) and len(scenes[0]["lines"]) <= 1 and scenes[-1]["lines"] == []
    assert all(0 <= w[1] <= 8.0 and w[2] <= 8.0 for s in scenes for w in s["words"])
    assert mc.line_times_from_words(lines, [["x", 0, 1]], 40.0) is None


def test_story_uses_llm_and_falls_back():
    class Good:
        def llm_json(self, system, user):
            return {"resumo": "Uma viagem de volta para casa.", "protagonista": "a tired sailor in a yellow raincoat", "cenario": "a stormy harbor town",
                    "paleta": "teal and gold", "arco": [{"momento": f"m{i}", "visual": f"a sailor scene number {i}"} for i in range(7)]}

    class Bad:
        def llm_json(self, system, user):
            raise RuntimeError("fora do ar")

    class Fake:
        def llm_json(self, system, user):
            return {"titles": ["x"]}

    b = mc.build_story("Volta", "letra", "mar", Good())
    assert b["protagonista"].startswith("a tired sailor") and len(b["arco"]) == 7
    for backend in (Bad(), Fake()):
        d = mc.build_story("Volta", "letra", "mar", backend)
        assert d["protagonista"] and len(d["arco"]) >= 3
    ctx = mc.scene_context(b, b["arco"][2], ["Para casa"], 2)
    assert "[P]" in ctx and "Para casa" in ctx and "intensa" in ctx and "yellow raincoat" not in ctx   # o LLM nunca vê (nem copia) a descrição do personagem
    assert mc.arc_index(0.999, 7) == 6 and mc.arc_index(0.0, 7) == 0


# ------------------------------------------------------------------ ponta a ponta (modo de teste)
import time  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.3)
    raise AssertionError("job não terminou")


LYRICS = "[Verso]\nEu andei pela rua vazia\nA lua seguia meu passo\n[Refrão]\nE o mar me chamou de volta\nPara casa eu vou voltar\nNa areia deixei meu nome\nO vento levou de vez"


def create(client, song, **over):
    prof = client.get("/api/profiles").json()[0]["id"]
    data = {"title": "Volta pra casa", "lyrics": LYRICS, "concept": "um marinheiro voltando para casa", "profile_id": prof, "ritmo": "normal", "animacao": "total", **over}
    with open(song, "rb") as f:
        return client.post("/api/clips", data=data, files={"file": ("volta.wav", f, "audio/wav")})


def test_clip_validation(client, song):
    assert create(client, song, lyrics="", concept="").status_code == 422
    assert create(client, song, ritmo="turbo").status_code == 422
    assert create(client, song, animacao="x").status_code == 422
    bad = client.post("/api/clips", data={"title": "x", "lyrics": "a", "profile_id": client.get("/api/profiles").json()[0]["id"]},
                      files={"file": ("x.txt", b"nao e audio", "text/plain")})
    assert bad.status_code == 422
    bad = client.post("/api/clips", data={"title": "x", "lyrics": "a", "profile_id": client.get("/api/profiles").json()[0]["id"]},
                      files={"file": ("x.wav", b"RIFFnaoeumwav", "audio/wav")})
    assert bad.status_code == 422
    assert client.get("/api/clips/options").json()["ritmos"]["normal"]


def test_clip_end_to_end_plan_prepare_render_and_shorts(client, song):
    r = create(client, song)
    assert r.status_code == 201
    p = r.json()
    pid = p["id"]
    assert p["meta"]["kind"] == "clip" and p["meta"]["clip"]["audio"].startswith("song") and p["meta"]["options"]["transition"] == "cut"

    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    p = client.get(f"/api/projects/{pid}").json()
    sc, clip = p["scenes"], p["meta"]["clip"]
    assert p["status"] == "planned" and len(sc) >= 8
    assert abs(sum(s["duration"] for s in sc) - 48.0) < 0.1                       # as cenas cobrem a música inteira
    assert clip["analise"]["bpm"] > 50 and clip["historia"]["protagonista"] and len(clip["historia"]["arco"]) >= 3
    assert all(s["audio"] == "song" and not s["dirty_audio"] and s["visual_prompt"] for s in sc)
    assert sum(len(s["words"]) for s in sc) == len(LYRICS.replace("[Verso]", "").replace("[Refrão]", "").split())  # toda palavra da letra caiu numa cena
    assert any(s["motion"] == "ltx" for s in sc) and sum(1 for s in sc if s["motion"] == "ltx") + sum(1 for s in sc if s["motion"] == "wan") == len(sc)

    # cenas seguem a música: não dá para dividir/juntar/apagar
    assert client.post(f"/api/projects/{pid}/scenes/1/merge").status_code == 409
    assert client.delete(f"/api/projects/{pid}/scenes/1").status_code == 409
    assert client.patch(f"/api/projects/{pid}/scenes/1", json={"text": "outra linha"}).json()["dirty_audio"] is False

    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "storyboard"
    assert wait(client, client.post(f"/api/projects/{pid}/render").json())["status"] == "done"
    p = client.get(f"/api/projects/{pid}").json()
    assert p["status"] == "done"
    final = db_path(pid) / "final.mp4"
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)], capture_output=True, text=True).stdout
    assert abs(float(out) - 48.0) < 1.0                                                  # duração do clipe = duração da música
    assert client.get(f"/api/projects/{pid}/estimate").status_code == 200

    sh = client.post(f"/api/projects/{pid}/shorts/generate", json={"count": 1})
    assert sh.status_code == 202 and wait(client, sh.json())["status"] == "done"
    assert len(client.get(f"/api/projects/{pid}/shorts").json()["items"]) == 1


def db_path(pid):
    from app import config
    return config.DATA / "projects" / pid


import subprocess  # noqa: E402


# ------------------------------------------------------------------ upload + transcrição da letra
def test_lyrics_from_segments_blank_line_on_long_pause():
    from app.pipeline import clipengine as ce
    r = ce.lyrics_from_segments([{"start": 0, "end": 3, "text": "  Primeira   linha "}, {"start": 3.5, "end": 6, "text": "Segunda linha"},
                                 {"start": 12, "end": 15, "text": "Outra estrofe"}, {"start": 15, "end": 16, "text": ""}])
    assert r["lyrics"] == "Primeira linha\nSegunda linha\n\nOutra estrofe" and r["linhas"] == 3 and not r["instrumental"]
    assert ce.lyrics_from_segments([])["instrumental"] is True


def test_upload_transcribes_then_clip_is_created_from_the_upload(client, song):
    prof = client.get("/api/profiles").json()[0]["id"]
    with open(song, "rb") as f:
        r = client.post("/api/clips/upload", files={"file": ("volta.wav", f, "audio/wav")})
    assert r.status_code == 201
    up = r.json()
    assert up["seconds"] > 40 and up["arquivo"] == "volta.wav" and up["job"]["kind"] == "transcribe_lyrics"
    j = wait(client, up["job"])
    assert j["status"] == "done" and j["result"]["linhas"] == 5 and not j["result"]["instrumental"] and "Linha 1" in j["result"]["lyrics"]
    assert wait(client, client.post(f"/api/clips/upload/{up['upload_id']}/transcribe").json())["status"] == "done"

    # o usuário revisa e edita a letra; o clipe nasce da música já enviada (sem enviar o arquivo de novo)
    lyrics = j["result"]["lyrics"] + "\nUma linha que o usuário acrescentou"
    r = client.post("/api/clips", data={"upload_id": up["upload_id"], "title": "Revisado", "lyrics": lyrics, "profile_id": prof, "ritmo": "calmo", "animacao": "camera"})
    assert r.status_code == 201
    p = r.json()
    assert p["meta"]["clip"]["arquivo"] == "volta.wav" and p["text"] == lyrics and p["meta"]["clip"]["animacao"] == "camera"
    assert client.post(f"/api/clips/upload/{up['upload_id']}/transcribe").status_code == 404      # o rascunho do upload foi consumido

    # letra pode ser corrigida depois, antes de gerar imagens e renderizar
    pid = p["id"]
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    new = "Nova primeira linha\nNova segunda linha"
    assert client.put(f"/api/projects/{pid}/lyrics", json={"lyrics": new}).json()["text"] == new
    assert client.put(f"/api/projects/{pid}/lyrics", json={"lyrics": "", "concept": ""}).status_code == 422
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    sc = client.get(f"/api/projects/{pid}").json()["scenes"]
    assert sum(len(s["words"]) for s in sc) == len(new.split()) and any("Nova primeira" in s["text"] for s in sc)
    assert all(s["motion"] == "ken_burns" for s in sc)                                              # animação "só câmera"


def test_upload_validation_and_unknown_upload_id(client, song):
    prof = client.get("/api/profiles").json()[0]["id"]
    assert client.post("/api/clips/upload", files={"file": ("x.txt", b"nao e audio", "text/plain")}).status_code == 422
    assert client.post("/api/clips/upload", files={"file": ("x.wav", b"RIFFnaoeumwav", "audio/wav")}).status_code == 422
    assert client.post("/api/clips/upload/inexistente00/transcribe").status_code == 404
    assert client.delete("/api/clips/upload/../../etc").status_code in (404, 405)
    base = {"title": "x", "lyrics": "a b c", "profile_id": prof}
    assert client.post("/api/clips", data={**base, "upload_id": "0123456789ab"}).status_code == 404
    assert client.post("/api/clips", data=base).status_code == 422                                   # sem música nem upload
    assert client.put("/api/projects/naoexiste/lyrics", json={"lyrics": "x"}).status_code == 404


def test_whisper_output_cleaning_drops_hallucinations():
    from app.pipeline.backends.voice_worker import clean_segments
    seg = lambda t, nsp=0.0, lp=-0.2, cr=1.2, a=0.0: {"start": a, "end": a + 3, "text": t, "no_speech_prob": nsp, "avg_logprob": lp, "compression_ratio": cr}  # noqa: E731
    raw = [seg("Como é bom te encontrar"), seg("Como é bom te encontrar", a=3), seg("Legendas pela comunidade Amara.org", a=6), seg("ruído", nsp=0.9, lp=-1.4, a=9),
           seg("la la la la la la la la", cr=3.1, a=12), seg("quase inaudível", lp=-1.9, a=15), seg("  Vem   comigo cantar ", a=18),
           seg("🎶", a=21), seg("♪ ♪", a=24), seg("Transcrição e Legendas Pedro Negri", a=27)]
    got = clean_segments(raw)
    assert [g["text"] for g in got] == ["Como é bom te encontrar", "Vem comigo cantar"]


# ------------------------------------------------------------------ animações sem rosto deformado (processo de geração)
def test_motion_prompt_keeps_people_still_and_ignores_scene_action():
    p = mc.motion_prompt("The woman sprints down a dark subway tunnel, screaming, lights flicker above the lake", 2)
    low = p.lower()
    assert "sprint" not in low and "scream" not in low                       # a ação da cena NÃO vai para o modelo de animação
    assert "almost still" in low and "same shape" in low and "gentle" in low
    assert "ripples" in low and "lights glowing" in low                      # só o ambiente se move (água, luzes)
    assert mc.motion_prompt("x", 0) != mc.motion_prompt("x", 1)              # a câmera varia de cena para cena
    assert mc.CLIP_SECONDS <= 3.0


def test_story_and_scene_prompts_forbid_scary_and_unsafe_compositions():
    for needle in ("NUNCA terror", "sósias", "espelhos"):
        assert needle in mc.SYSTEM_STORY
    for needle in ("NEVER a close-up of a face", "never running", "from behind", "never scary"):
        assert needle in mc.SYSTEM_SCENE


def test_animation_workflows_use_strong_negative_prompt_and_a_seed():
    from app.pipeline.backends.comfy import NEGATIVE_MOTION, Comfy
    assert "distorted face" in NEGATIVE_MOTION and "melting" in NEGATIVE_MOTION and "horror" in NEGATIVE_MOTION
    assert "static" not in NEGATIVE_MOTION.lower().split(", ")                # "static" pedia MAIS movimento no Wan
    ltx = Comfy.ltx_workflow("a.png", "p", 768, 416, 73, "x", seed=123)
    wan = Comfy.wan_workflow("a.png", "p", 960, 544, 73, "x", seed=456)
    assert ltx["4"]["inputs"]["text"] == NEGATIVE_MOTION and ltx["11"]["inputs"]["noise_seed"] == 123
    assert wan["5"]["inputs"]["text"].startswith(NEGATIVE_MOTION) and wan["10"]["inputs"]["seed"] == 456


def test_redo_clip_clears_the_animation_and_changes_seed(client, song):
    prof = client.get("/api/profiles").json()[0]["id"]
    with open(song, "rb") as f:
        up = client.post("/api/clips/upload", files={"file": ("v.wav", f, "audio/wav")}).json()
    pid = client.post("/api/clips", data={"upload_id": up["upload_id"], "lyrics": "Uma linha\nOutra linha", "profile_id": prof, "animacao": "total"}).json()["id"]
    assert wait(client, client.post(f"/api/projects/{pid}/plan").json())["status"] == "done"
    assert wait(client, client.post(f"/api/projects/{pid}/prepare").json())["status"] == "done"
    assert wait(client, client.post(f"/api/projects/{pid}/render").json())["status"] == "done"
    s = next(x for x in client.get(f"/api/projects/{pid}").json()["scenes"] if x["motion"] != "ken_burns")
    assert s["clip"]
    r = client.patch(f"/api/projects/{pid}/scenes/{s['n']}", json={"redo_clip": True}).json()
    assert r["clip"] is None and r["clip_seed"] and r["clip_seed"] != s["seed"]


def test_protagonist_is_injected_by_code_and_labels_are_stripped():
    bible = {"protagonista": "a man in his thirties in a white linen shirt, seen from behind."}
    out = mc.fill_protagonist("PROTAGONIST: [P] walks slowly along the shore at sunset, wide shot, soft light", bible)
    assert out.startswith("a man in his thirties in a white linen shirt, seen from behind walks slowly") and "PROTAGONIST" not in out and "[P]" not in out
    assert mc.fill_protagonist("An empty lighthouse over calm water", bible) == "An empty lighthouse over calm water"
    assert mc.fill_protagonist("[P] and [P]", bible).endswith("and the person")
    assert "SEM descrever o rosto" in mc.SYSTEM_STORY and "[P]" in mc.SYSTEM_SCENE


def test_clip_captions_follow_the_lyric_line_across_scenes():
    from app import captions
    lines = ["Plantando algumas flores pra te dar algum sinal", "Meu barco segue a trilha"]
    times = [3.4, 11.5]
    words = mc.words_for_lines(lines, times, 20.0)
    scenes = [{"start": 3.0 * i, "duration": 3.0} for i in range(7)]
    mc.attach_lyrics(scenes, lines, times, words)
    got = mc.caption_lines(scenes)
    assert [" ".join(w[0] for w in ln) for ln in got] == lines                        # um verso inteiro, mesmo atravessando cenas
    assert got[0][0][1] >= 3.4 and got[0][-1][1] < got[1][0][1]                       # tempos absolutos e em ordem
    ass = captions.build_ass([(0.0, ln) for ln in got], 1920, 1080, {})
    texts = [x.split(",,")[-1] for x in ass.splitlines() if x.startswith("Dialogue")]
    assert not any("sinal Meu" in t for t in texts) and texts[0] == "Plantando algumas flores pra" and texts[1] == "te dar algum sinal"
    for s in scenes:                                                                   # cenas sem as linhas guardadas (projeto antigo): vale a letra do projeto
        s["lines"] = []
    assert [" ".join(w[0] for w in ln) for ln in mc.caption_lines(scenes, lines)] == lines
    assert len(mc.caption_lines(scenes)) >= 2                                          # sem letra nenhuma: separa os versos pelas pausas
