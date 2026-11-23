"""Ajuste dos sons do Kokoro para o português do Brasil.

O fonetizador (espeak pt-br) acerta o essencial (t/d chiados antes de i, "rr" como h, l final como u), mas escreve o "a" final com um som aberto de inglês
("casa" vira "casæ") e põe um "e" mudo depois do r ("porta" vira "porêta"); o r final sai trinado, como em espanhol ou português europeu.
Aqui o texto de sons é corrigido antes de a voz falar. As vogais nasais NÃO são mexidas por padrão: o modelo fala bem "mente" e "humana" do jeito que o espeak escreve
(trocar por vogal com til deixou as duas palavras erradas). `nasal=True` liga um ajuste só para "im", "om" e "um", para teste.
"""
import re

TILDE = "̃"


def fix(ps: str, nasal: bool = False) -> str:
    if not ps:
        return ps
    if nasal:                                             # só i/o/u + ŋ no fim de sílaba ("sim", "honra"); o "A" (e nasal) e o resto ficam como estão
        ps = re.sub(r"([iou])ŋ(?=[^aeiouɐɛɔɪʊyæA]|$|\s)", lambda m: m.group(1) + TILDE, ps)
    ps = ps.replace("æ", "ɐ")                                # "a" final brasileiro, não o "a" de "cat"
    ps = ps.replace("ɾə", "ɾ")                               # sem "e" mudo depois do r
    ps = ps.replace("r", "ɾ")                                # r final trinado vira o r curto brasileiro
    return ps


def wrap_g2p(g2p, nasal: bool = False):
    """Embrulha o fonetizador do Kokoro para devolver os sons já corrigidos."""
    def run(text):
        ps, tokens = g2p(text)
        return fix(ps, nasal), tokens
    return run
