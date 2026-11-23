from app import captions


def test_align_uses_original_words_not_whisper_text():
    orig = "Eliphas Lévi chamava de Grande Arcano".split()
    heard = [("Eliphas", 0.0, 0.6), ("Levy", 0.6, 1.0), ("chamava", 1.0, 1.5), ("de", 1.5, 1.6), ("grande", 1.6, 2.0), ("arcano", 2.0, 2.6)]
    out = captions.align_words(orig, heard, 2.6)
    assert [w[0] for w in out] == orig                      # texto original preservado
    assert out[1][1:] == [0.6, 1.0]                          # "Lévi" ≈ "Levy": o difflib não casa, mas interpola no mesmo intervalo
    assert all(a[2] <= b[1] + 1e-6 for a, b in zip(out, out[1:]))  # monotônico


def test_align_ignores_hallucinated_words_and_fills_missing():
    orig = "um dois três quatro".split()
    heard = [("Oh", 0.0, 0.3), ("um", 0.3, 0.8), ("quatro", 2.0, 2.6)]
    out = captions.align_words(orig, heard, 2.6)
    assert out[0][1:] == [0.3, 0.8] and out[3][1:] == [2.0, 2.6]
    assert 0.8 <= out[1][1] < out[2][2] <= 2.0              # "dois" e "três" interpolados entre as âncoras


def test_ass_has_events_with_offset_and_color():
    words = [["Olá", 0.0, 0.5], ["mundo.", 0.5, 1.0]]
    ass = captions.build_ass([(10.0, words)], 1920, 1080, {"font": "serif", "color": "#FF8800"})
    assert "DejaVu Serif" in ass and "&H000088FF" in ass
    assert "Dialogue: 0,0:00:10.00,0:00:11.15,Default,,0,0,0,,Olá mundo." in ass


def test_ass_chunks_never_overlap_in_time():
    """Regressão: o 'segura' de 0,15 s fazia dois trechos coexistirem e as legendas empilhavam em duas linhas."""
    words = [["um", 0.0, 0.3], ["dois", 0.3, 0.6], ["três;", 0.6, 0.9], ["quatro", 0.95, 1.2], ["cinco", 1.2, 1.5], ["seis.", 1.5, 1.8]]
    words2 = [["sete", 0.0, 0.4], ["oito", 0.4, 0.8]]
    ass = captions.build_ass([(0.0, words), (1.85, words2)], 1920, 1080, {})
    ev = [l for l in ass.splitlines() if l.startswith("Dialogue")]

    def sec(x):
        h, m, s = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    times = [(sec(l.split(",")[1]), sec(l.split(",")[2])) for l in ev]
    assert len(times) >= 3
    for (a1, b1), (a2, b2) in zip(times, times[1:]):
        assert b1 <= a2 + 1e-6 and b1 > a1               # sem sobreposição e com duração positiva
