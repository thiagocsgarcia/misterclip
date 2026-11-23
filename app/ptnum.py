"""Números e símbolos por extenso, em português do Brasil.

Serve a dois usos: a narração (a voz sintética lê "2025" ou "81 milhões" de forma estranha) e o rascunho de roteiro (o canal
escreve números por extenso). O texto das legendas nunca passa por aqui: só o que vai para a voz.
"""
import re

_UN = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze", "quinze",
       "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEN = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]
_ESCALA = [(10**12, "trilhão", "trilhões"), (10**9, "bilhão", "bilhões"), (10**6, "milhão", "milhões")]


def _ate_999(n: int) -> str:
    if n < 20:
        return _UN[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DEZ[d] + (f" e {_UN[u]}" if u else "")
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    return _CEN[c] + (f" e {_ate_999(r)}" if r else "")


def _liga(resto: int) -> str:
    """Entre dois blocos grandes: "e" quando o resto é pequeno (mil e vinte) ou redondo (mil e quinhentos); senão, só espaço."""
    return " e " if resto < 100 or resto % 100 == 0 else " "


def cardinal(n: int) -> str:
    if n < 0:
        return "menos " + cardinal(-n)
    if n < 1000:
        return _ate_999(n)
    for base, sing, plur in _ESCALA:
        if n >= base:
            q, r = divmod(n, base)
            head = f"{cardinal(q)} {sing if q == 1 else plur}"
            return head + (_liga(r) + cardinal(r) if r else "")
    q, r = divmod(n, 1000)
    head = "mil" if q == 1 else f"{cardinal(q)} mil"
    return head + (_liga(r) + cardinal(r) if r else "")


def _decimais(frac: str) -> str:
    if len(frac) <= 2 and not frac.startswith("0"):
        return cardinal(int(frac))
    return " ".join(_UN[int(c)] for c in frac)


_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
_ESC_RE = r"(?:\s+(milhões|milhão|bilhões|bilhão|trilhões|trilhão|mil)(?!\w))?"


def _say(tok: str) -> str:
    tok = tok.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", tok) else tok
    whole, _, frac = tok.partition(",")
    out = cardinal(int(whole))
    return out + (f" vírgula {_decimais(frac)}" if frac else "")


def _money(m: re.Match) -> str:
    sym, tok, scale = m.group(1), m.group(2), m.group(3)
    coin = "dólares" if sym.upper().startswith("US") else "reais"
    one = "dólar" if coin == "dólares" else "real"
    say = _say(tok)
    if scale:
        return f"{say} {scale} de {coin}"
    return f"{say} {one if say == 'um' else coin}"


def _plain(m: re.Match) -> str:
    return _say(m.group(1)) + (f" {m.group(2)}" if m.group(2) else "")


def expand_numbers(text: str) -> str:
    """"Em 2025, R$ 81 milhões e 10%" -> "Em dois mil e vinte e cinco, oitenta e um milhões de reais e dez por cento"."""
    t = re.sub(rf"(R\$|US\$)\s*({_NUM}){_ESC_RE}", _money, text)
    t = re.sub(rf"({_NUM})\s*%", lambda m: _say(m.group(1)) + " por cento", t)
    t = re.sub(rf"(?<![\w/-])({_NUM}){_ESC_RE}(?![\w/-])", _plain, t)
    t = re.sub(r"\s*&\s*", " e ", t)
    return t


def apply_pronunciations(text: str, table: dict | None) -> str:
    """Troca nomes que a voz lê errado pela grafia que ela pronuncia bem ("Thiel" -> "Tíl"). Só no que vai para a voz."""
    for word, say in sorted((table or {}).items(), key=lambda kv: -len(kv[0])):
        if str(word).strip() and str(say).strip():
            text = re.sub(rf"(?<!\w){re.escape(str(word).strip())}(?!\w)", str(say).strip(), text)
    return text


def for_tts(text: str, pronunciations: dict | None = None) -> str:
    return " ".join(apply_pronunciations(expand_numbers(text), pronunciations).split())
