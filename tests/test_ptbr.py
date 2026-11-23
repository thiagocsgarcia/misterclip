"""Ajuste de sons do Kokoro para o português do Brasil."""
from app.pipeline import ptbr

T = "̃"


def test_nasal_words_are_left_as_espeak_writes_them():
    for ps in ("mˈAŋʧy", "ˌumˈɐ̃næ".replace("æ", "ɐ"), "tˈAmpʊ", "ˌumˈɐ̃nʊ", "kˈɐ̃nɐ"):       # mente, humana, tempo, humano, cana
        assert ptbr.fix(ps) == ps


def test_final_a_and_r_follow_brazilian_speech():
    assert ptbr.fix("pˈɔɾətæ") == "pˈɔɾtɐ"                  # porta: sem "e" mudo, "a" final brasileiro
    assert ptbr.fix("ˌumˈɐ̃næ") == "ˌumˈɐ̃nɐ"                # humana mantém o n
    assert ptbr.fix("falˈar") == "falˈaɾ"                    # r final curto
    assert ptbr.fix("xˈA ʤy") == "xˈA ʤy" and ptbr.fix("") == ""


def test_optional_nasal_adjustment_only_touches_i_o_u():
    assert ptbr.fix("sˈiŋ", nasal=True) == "sˈi" + T
    assert ptbr.fix("mˈAŋʧy", nasal=True) == "mˈAŋʧy"         # o "e" nasal não é tocado
    assert ptbr.fix("ˌumˈɐ̃næ", nasal=True) == "ˌumˈɐ̃nɐ"


def test_wrapper_keeps_the_kokoro_contract():
    run = ptbr.wrap_g2p(lambda text: ("kˈazæ", ["tok"]))
    assert run("casa") == ("kˈazɐ", ["tok"])
