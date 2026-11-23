"""Confere uma imagem recém-gerada: o gerador às vezes devolve um quadro preto, branco ou liso. Barato (CPU) e sem IA."""
from PIL import Image, ImageStat


def problem(path: str) -> str | None:
    """None se a imagem parece boa; senão, o motivo em português."""
    try:
        with Image.open(path) as im:
            g = im.convert("L").resize((96, 96))
    except Exception as e:
        return f"arquivo ilegível ({type(e).__name__})"
    st = ImageStat.Stat(g)
    mean, sd = st.mean[0], st.stddev[0]
    if mean < 8:
        return "imagem quase toda preta"
    if mean > 248:
        return "imagem quase toda branca"
    if sd < 5:
        return "imagem lisa, sem detalhe"
    return None
