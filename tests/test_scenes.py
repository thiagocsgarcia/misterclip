from app import scenes


def test_manual_markers_split_scenes():
    text = "Primeira cena inteira.\n[CENA]\nSegunda cena aqui.\n[cena]\nTerceira."
    assert scenes.split_text(text) == ["Primeira cena inteira.", "Segunda cena aqui.", "Terceira."]


def test_groups_sentences_to_target_duration():
    sentence = "Esta é uma frase de teste com dez palavras no total sim."  # 11 palavras ≈ 4 s
    parts = scenes.split_text(" ".join([sentence] * 9), target=9)
    assert 3 <= len(parts) <= 5
    assert all(scenes.est_seconds(p) <= 9 * 1.3 + 4 for p in parts)
    assert " ".join(parts).count("frase de teste") == 9  # nada se perde


def test_short_tail_is_merged():
    parts = scenes.split_text("Uma frase razoavelmente longa para formar uma cena completa aqui agora mesmo. Fim.", target=3)
    assert parts[-1].endswith("Fim.") and len(parts) <= 2


def test_empty_text():
    assert scenes.split_text("  \n ") == []


def test_pick_animated_even_spread_and_first_scene():
    picked = scenes.pick_animated(20, 0.35)
    assert len(picked) == 7 and 0 in picked
    assert scenes.pick_animated(10, 0) == set() and scenes.pick_animated(4, 1) == {0, 1, 2, 3}
