"""Regras do canal: o que o planejamento define passa a COMANDAR a geração dos vídeos.

As regras vivem na seção editável `regras_do_canal` do plano (com padrões abaixo) e alimentam: os prompts do LLM (título, descrição, tags, imagens, revisão
do roteiro), a imposição automática no que o LLM devolve, os padrões de um vídeo novo (estilo, voz, velocidade), a verificação do roteiro antes de gerar, a
verificação antes de publicar e a trava do envio automático ao YouTube. Tudo em Python simples (regex e contas), sem depender de LLM para verificar.
"""
import copy
import re

DEFAULT_RULES = {
    "titulo": {
        "max_caracteres": 70, "permitir_caixa_alta": False,
        "palavras_proibidas": ["segredo", "segredos", "revelado", "revelados", "proibido", "proibida", "ninguém conta", "o que escondem", "chocante", "você não vai acreditar"],
        "regra_de_estilo": "Frase normal (sem CAIXA ALTA), com o nome que as pessoas buscam no começo e uma pergunta ou uma tensão concreta. O vídeo precisa entregar o que o título promete.",
    },
    "miniatura": {"max_palavras": 4},
    "descricao": {"exigir_fontes": True, "exigir_capitulos_acima_de_minutos": 5, "max_hashtags": 3, "min_caracteres_intro": 80},
    "roteiro": {
        "minutos_por_formato": {"ensaio": [8, 12], "longo": [8, 12]}, "minutos_maximo": 30, "palavras_por_minuto": 125, "max_palavras_primeira_frase": 45, "citar_fontes_minimo": 3,
        "numeros_por_extenso": True,
        "palavras_de_promessa": ["garantido", "garantia de", "cura", "ganhe dinheiro", "vai ficar rico", "previsão certa", "resultado certo"],
        "palavras_sensacionalistas": ["segredo", "segredos", "revelado", "revelados", "proibido", "chocante", "ninguém te conta"],
        "palavras_de_campanha": ["vote em", "vote no", "vote na", "não vote", "apoie o candidato", "apoie a candidata"],       # o canal analisa política, não faz campanha
        "palavras_de_ataque": ["petralha", "bolsominion", "esquerdopata", "direitopata", "mortadela", "coxinha"],
    },
    "politica": {
        "ativo": True,
        "regras": ["Analise ideias, fatos e instituições; nunca peça voto nem faça campanha por candidato, partido ou governo.",
                   "Separe o que é fato (com fonte), o que é interpretação e o que é opinião do canal, dizendo qual é qual em voz alta.",
                   "Apresente o melhor argumento de cada lado antes de concluir; a conclusão pode existir, mas vem depois das evidências.",
                   "Fale de pessoas vivas só pelo que dizem e fazem em público, com fonte; sem insulto, sem adivinhar intenção, sem teoria da conspiração dita como fato.",
                   "Nada de imagem ou voz sintética de político ou pessoa real (a Justiça Eleitoral proíbe em campanha e o canal não faz em nenhum momento)."],
    },
    "geopolitica": {      # o canal analisa o poder entre países (chips, minerais, rotas, moedas, ideias); não toma lado em guerra nem faz propaganda
        "ativo": True,
        "regras": ["Descreva o interesse de cada país com as palavras e os dados dele mesmo antes de julgar; nada de tratar um povo como um bloco (“os russos são…”, “os chineses são…”).",
                   "Separe fato (com fonte e data), estimativa e opinião do canal; em guerra e crise em andamento, diga que os dados mudam e dê a data da coleta.",
                   "Sem propaganda de nenhum lado e sem celebrar violência; fale de vítimas com respeito e sem imagem gráfica.",
                   "Mapas e fronteiras em disputa aparecem como disputados, nunca como definitivos; cite quem reconhece o quê.",
                   "Ideólogos (Dugin, Haushofer, Mackinder…) entram pelo que escreveram e pelo uso que dizem ter feito deles, com citação; nunca como acusação sem fonte.",
                   "Não afirme intenção secreta de governo, serviço de inteligência ou grupo; “quem controla o mundo” é conspiração e não entra como fato."],
        "generalizacoes": ["os russos são", "os chineses são", "os americanos são", "os árabes são", "os iranianos são", "os ucranianos são", "os israelenses são", "os palestinos são", "os judeus são", "os muçulmanos são", "os brasileiros são"],
    },
    "narracao": {"voz": "pm_alex", "velocidade": 0.85, "pronuncias": {}},   # pronuncias: {"Thiel": "Tíl"} troca só na voz; a legenda mantém a grafia do roteiro
    "video": {
        "modo_padrao": "automatico",                  # automatico: o sistema monta tudo sozinho a partir do roteiro; revisar: para nas cenas para você conferir
        "segundos_por_cena": 9, "proporcao_animada": 0.35, "motor_de_animacao": "ltx", "transicao": "crossfade", "legendas": True,
        "musica": {"arquivo": "", "volume": 0.25, "duck": True},
        "apos_renderizar": ["metadata", "thumbnail", "shorts"], "shorts_por_video": 2,
    },
    "visual": {
        "estilo_padrao": "",
        "evitar": ["close de rosto", "rostos deformados ou assustadores", "espelhos que mostram outra pessoa", "multidões", "cenas de terror",
                  "rosto de político ou de qualquer pessoa real", "bandeiras e símbolos de partido", "cartazes de campanha",
                  "violência gráfica, corpos ou imagem real de guerra", "mapas de fronteira em disputa mostrados como definitivos"],
        "composicao_segura": True,
    },
    "publicacao": {"bloquear_envio_automatico_com_erros": True},
    "juridico": {        # proteção contra calúnia, difamação, discurso de ódio e desinformação (não é aconselhamento jurídico: ajuda a evitar o que mais gera problema)
        "ativo": True,
        "pessoas_vivas": ["Peter Thiel", "Thiel", "Elon Musk", "Musk", "Sam Altman", "Altman", "Curtis Yarvin", "Yarvin", "Larry Ellison", "Donald Trump", "Trump", "JD Vance", "Vance",
                          "Lula", "Bolsonaro", "Alexandre de Moraes", "Moraes", "Yanis Varoufakis", "Varoufakis", "Mark Zuckerberg", "Zuckerberg", "Jeff Bezos", "Bezos", "Nick Land",
                          "Marc Andreessen", "Andreessen", "Ray Kurzweil", "Kurzweil", "Nick Bostrom", "Bostrom", "Eliezer Yudkowsky", "Yudkowsky", "Barack Obama", "Obama", "Dario Amodei", "Demis Hassabis", "Byung-Chul Han", "Javier Milei", "Milei", "Greta Thunberg", "Papa Leão"],
        "acusacoes": ["criminos", "corrupt", "ladr", "assassin", "pedófil", "golpist", "traidor", "terrorist", "genocid", "estelionat", "nazist", "fascist", "racist", "mentiros",
                      "farsant", "charlat", "anticristo"],
        "odio_grave": ["judeus controlam", "judeus dominam", "complô judaico", "conspiração judaica", "sionistas controlam", "banqueiros judeus", "raça superior", "raça inferior"],
        "conspiracao": ["controlam o mundo", "dominam o mundo", "governam o mundo", "governo secreto", "elite secreta", "nova ordem mundial"],
        "certeza_indevida": ["é fato que", "está provado que", "todo mundo sabe", "sabemos que ele", "com certeza ele", "sem dúvida nenhuma"],
        "aviso_editorial": ("Vídeo de análise e opinião, feito com fontes públicas citadas acima. Não afirma fatos além dos citados, não faz campanha política e não acusa ninguém de crime. "
                            "Imagens e narração geradas por IA; nenhuma pessoa real é retratada."),
    },
}
DESCRICAO = "Estas regras guiam a geração: títulos, miniaturas, descrição, prompts de imagem, revisão do roteiro e o envio ao YouTube. Edite à vontade; o sistema segue o que estiver aqui."


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def effective(ch: dict | None) -> dict:
    return _merge(DEFAULT_RULES, ((ch or {}).get("plan") or {}).get("regras_do_canal") or {})


# --------------------------------------------------------------------------- contexto para o LLM
def _lines(items) -> str:
    return "; ".join(str(x) for x in items if str(x).strip())


def context_text(ch: dict | None) -> str:
    """Texto curto com a identidade e as regras do canal, para colocar nos prompts do LLM."""
    if not ch:
        return ""
    plan, r = ch["plan"], effective(ch)
    ident = (plan.get("nicho") or {}).get("identidade") or {}
    pos = plan.get("posicionamento") or {}
    parts = [f"CANAL: {ch['name']}" + (f" — {ident.get('slogan')}" if ident.get("slogan") else "")]
    if pos.get("promessa"):
        parts.append(f"Promessa do canal: {pos['promessa']}")
    if pos.get("publico"):
        parts.append(f"Público: {pos['publico']}")
    voz = ident.get("voz") or pos.get("voz")
    if voz:
        parts.append(f"Voz do canal: {voz}")
    if ident.get("valores"):
        parts.append("Valores: " + _lines(ident["valores"]))
    if pos.get("evitar"):
        parts.append("O que o canal NUNCA faz: " + _lines(pos["evitar"]))
    t = r["titulo"]
    parts.append(f"Regras do título: até {t['max_caracteres']} caracteres; {'pode' if t['permitir_caixa_alta'] else 'sem'} CAIXA ALTA; palavras proibidas: {_lines(t['palavras_proibidas'])}. {t['regra_de_estilo']}")
    jur = r.get("juridico") or {}
    if jur.get("ativo"):
        parts.append("Segurança jurídica (obrigatória): nunca acuse pessoa viva de crime nem de caráter (corrupto, fascista, criminoso, 'é o Anticristo'); atribua cada afirmação a uma fonte "
                     "(“segundo…”, “disse em…”); use 'teria', 'segundo o relato' quando a fonte for indireta; separe fato, opinião e lenda; sem estereótipo sobre religião, etnia ou grupo; "
                     "sem teoria de que um grupo secreto controla o mundo; título e miniatura sem acusação nem nome de pessoa viva ligado a palavra de ataque.")
    pol = r.get("politica") or {}
    if pol.get("ativo") and pol.get("regras"):
        parts.append("Política (o canal trata de poder e tecnologia, sem partido): " + _lines(pol["regras"]))
    geo = r.get("geopolitica") or {}
    if geo.get("ativo") and geo.get("regras"):
        parts.append("Geopolítica (o canal analisa poder entre países, sem tomar lado): " + _lines(geo["regras"]))
    parts.append(f"Miniatura: no máximo {r['miniatura']['max_palavras']} palavras.")
    d = r["descricao"]
    parts.append(f"Descrição: ideia central nas duas primeiras linhas, capítulos" + (" e uma seção 'Fontes' com autor, obra e ano" if d["exigir_fontes"] else "") + f"; até {d['max_hashtags']} hashtags no fim.")
    return "\n".join(parts)


def visual_extra(ch: dict | None) -> str:
    """Complemento (em inglês) para o prompt de imagem dos vídeos narrados: estética do canal e o que evitar."""
    if not ch:
        return ""
    r = effective(ch)
    est = ((ch["plan"].get("nicho") or {}).get("identidade") or {}).get("estetica", "")
    out = []
    if est:
        out.append(f"Channel visual aesthetic (follow it): {est}")
    if r["visual"]["evitar"]:
        out.append("Never depict: " + _lines(r["visual"]["evitar"]) + ".")
    if r["visual"]["composicao_segura"]:
        out.append("Prefer wide or medium-wide shots, people from behind or at a distance, calm and beautiful scenes, never scary or unsettling.")
    return " ".join(out)


# --------------------------------------------------------------------------- verificações
def _f(nivel: str, onde: str, regra: str, msg: str, corrigir: str = "") -> dict:
    return {"nivel": nivel, "onde": onde, "regra": regra, "mensagem": msg, "como_corrigir": corrigir}


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if c.isupper()) / len(letters) if letters else 0.0


def _found(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w and re.search(r"(?<![\wà-ú])" + re.escape(w.lower()) + r"(?![\wà-ú])", low)]


def lint_title(title: str, rules: dict) -> list[dict]:
    t, out = rules["titulo"], []
    title = (title or "").strip()
    if not title:
        return [_f("erro", "titulo", "titulo.vazio", "O título está vazio.", "Escolha uma das sugestões ou escreva o seu.")]
    if len(title) > t["max_caracteres"]:
        out.append(_f("erro" if len(title) > 100 else "aviso", "titulo", "titulo.tamanho", f"O título tem {len(title)} caracteres (o canal pede até {t['max_caracteres']}).", "Corte palavras: o começo é o que aparece no celular."))
    if not t["permitir_caixa_alta"] and (_caps_ratio(title) > 0.6 and len(title.split()) > 2):
        out.append(_f("erro", "titulo", "titulo.caixa_alta", "O título está em CAIXA ALTA.", "Use frase normal."))
    bad = _found(title, t["palavras_proibidas"])
    if bad:
        out.append(_f("erro", "titulo", "titulo.proibidas", "O título usa palavras que o canal evita: " + ", ".join(bad) + ".", "Troque por uma pergunta ou uma tensão concreta."))
    jur = rules.get("juridico") or {}
    if jur.get("ativo"):
        people = _living(title, rules)
        stems = "|".join(re.escape(x) for x in jur.get("acusacoes", []))
        if people and stems and re.search(rf"(?:{stems})", title, re.I) and not title.rstrip().endswith("?") and "fato" not in title.lower():
            out.append(_f("erro", "titulo", "titulo.acusacao", "O título liga uma pessoa viva (" + ", ".join(people) + ") a uma acusação sem pergunta nem “fato e lenda”.", "Reescreva como pergunta ou como “o que é fato e o que é lenda”."))
        elif people:
            out.append(_f("aviso", "titulo", "titulo.pessoa_viva", "O título cita pessoa viva (" + ", ".join(people) + "): o vídeo precisa provar tudo o que ele sugere.", "Prefira pergunta ou “o que é fato”; sem adjetivo de ataque."))
    if not [x for x in out if x["nivel"] in ("erro", "aviso")]:
        out.append(_f("ok", "titulo", "titulo.ok", f"Título dentro das regras ({len(title)} caracteres)."))
    return out


def lint_thumb(text: str, rules: dict) -> list[dict]:
    n, m = len((text or "").split()), rules["miniatura"]["max_palavras"]
    if not (text or "").strip():
        return [_f("aviso", "miniatura", "miniatura.vazia", "A miniatura ainda não tem texto.", "Gere as miniaturas na tela Publicar.")]
    if n > m:
        return [_f("erro", "miniatura", "miniatura.palavras", f"O texto da miniatura tem {n} palavras (o máximo é {m}).", "Deixe só a ideia principal.")]
    return [_f("ok", "miniatura", "miniatura.ok", f"Texto da miniatura com {n} palavras.")]


def lint_description(desc: str, rules: dict, minutes: float, has_chapters: bool) -> list[dict]:
    d, out = rules["descricao"], []
    intro = (desc or "").strip().split("\n\n")[0] if desc else ""
    if len(intro) < d["min_caracteres_intro"]:
        out.append(_f("aviso", "descricao", "descricao.intro", "A introdução da descrição está curta.", "Escreva a ideia central do vídeo nas duas primeiras linhas."))
    if d["exigir_capitulos_acima_de_minutos"] and minutes >= d["exigir_capitulos_acima_de_minutos"] and not has_chapters:
        out.append(_f("aviso", "descricao", "descricao.capitulos", "Faltam capítulos na descrição.", "Gere as sugestões de novo ou ajuste os nomes dos capítulos."))
    if d["exigir_fontes"] and not re.search(r"\bfontes?\b", desc or "", re.I):
        out.append(_f("aviso", "descricao", "descricao.fontes", "A descrição não tem a seção “Fontes”.", "Liste autor, obra e ano das fontes citadas no vídeo."))
    tags = re.findall(r"(?<!\w)#\w+", desc or "")
    if len(tags) > d["max_hashtags"]:
        out.append(_f("aviso", "descricao", "descricao.hashtags", f"São {len(tags)} hashtags (o canal usa até {d['max_hashtags']}).", "Deixe só as mais importantes."))
    if not out:
        out.append(_f("ok", "descricao", "descricao.ok", "Descrição dentro das regras."))
    return out


_CITE = re.compile(r"\b(segundo|de acordo com|conforme|escrit[oa] por|publicad[oa] em|no livro|na obra|o texto chamado|diz o|afirma|aponta|relata|em (?:mil|dois mil)\b)", re.I)
_MARKS = re.compile(r"\[(?:B-ROLL|TELA|SOM|QUEBRA|SAÍDA|TEASER|CENA)[^\]]*\]", re.I)


def _living(text: str, rules: dict) -> list[str]:
    """Pessoas vivas citadas (da lista do canal), sem repetir 'Thiel' quando já achou 'Peter Thiel'."""
    names = [n for n in (rules.get("juridico") or {}).get("pessoas_vivas", []) if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text or "", re.I)]
    return [n for n in names if not any(n != m and n.lower() in m.lower() for m in names)]


def _legal_findings(body: str, rules: dict) -> list[dict]:
    jur = rules.get("juridico") or {}
    if not jur.get("ativo"):
        return []
    out, stems = [], "|".join(re.escape(x) for x in jur.get("acusacoes", []))
    sents = re.split(r"(?<=[.!?…])\s+", body)
    bad = []
    if stems:
        pat = re.compile(rf"\b(?:é|foi|são|era|seria|foram)\s+(?:um|uma|o|a|os|as)?\s*(?:{stems})", re.I)
        for i, sen in enumerate(sents):
            ref = i > 0 and re.match(r"\s*(ele|ela|esse|essa|este|esta|o bilionário|o fundador|o empresário|o presidente)\b", sen, re.I)      # "Ele é corrupto" depois de citar o nome
            if pat.search(sen) and _living(" ".join(sents[i - 1:i + 1]) if ref else sen, rules):
                bad.append(sen.strip()[:110])
    if bad:
        out.append(_f("erro", "roteiro", "roteiro.acusacao", "Frase que afirma como fato algo grave sobre pessoa viva: “" + bad[0] + "”" + (f" (e mais {len(bad) - 1})" if len(bad) > 1 else "") + ".",
                      "Atribua a uma fonte (“segundo…”), use “teria” ou troque por fato verificável; não acuse ninguém de crime ou de caráter."))
    grave = _found(body, jur.get("odio_grave", []))
    if grave:
        out.append(_f("erro", "roteiro", "roteiro.odio", "Trecho com estereótipo ou teoria de ódio contra um grupo: " + ", ".join(grave) + ".", "Remova. É o que mais leva a remoção do canal e a processo."))
    consp = _found(body, jur.get("conspiracao", []))
    if consp:
        out.append(_f("aviso", "roteiro", "roteiro.conspiracao", "Linguagem de teoria da conspiração: " + ", ".join(consp) + ".", "Diga que é uma crença ou lenda e mostre o que a história documenta, sem afirmar que um grupo controla o mundo."))
    cert = _found(body, jur.get("certeza_indevida", []))
    if cert:
        out.append(_f("aviso", "roteiro", "roteiro.certeza", "Certeza sem fonte: " + ", ".join(cert) + ".", "Troque por “segundo…” ou “até onde se sabe”."))
    people = _living(body, rules)
    if people:
        out.append(_f("aviso", "roteiro", "roteiro.pessoa_viva", "Cita pessoa viva: " + ", ".join(people) + ". Cada afirmação sobre ela precisa de fonte e atribuição.", "Confira data, número e autor da fonte antes de publicar."))
    return out


def lint_script(text: str, rules: dict, formato: str | None = None) -> dict:
    """Verifica o roteiro ANTES de gerar o vídeo: tamanho, abertura, números por extenso, fontes, promessas, sensacionalismo e marcações esquecidas."""
    r, out = rules["roteiro"], []
    body = _MARKS.sub("", text or "")
    words = len(body.split())
    wpm = r["palavras_por_minuto"] or 125
    minutes = round(words / wpm, 1)
    if words < 30:
        return {"palavras": words, "minutos": minutes, "achados": [_f("erro", "roteiro", "roteiro.curto", "O roteiro está muito curto.", "Cole o texto completo da narração.")]}
    span = (r["minutos_por_formato"].get(formato or "ensaio") or r["minutos_por_formato"].get("ensaio") or [0, 999])
    top = max(span[1], r.get("minutos_maximo") or span[1])      # o tamanho usual é o do formato; passar dele é permitido quando o tema pede, até o máximo do canal
    if minutes < span[0] or minutes > top:
        out.append(_f("aviso", "roteiro", "roteiro.duracao", f"O roteiro rende cerca de {minutes} min; o canal pede de {span[0]} a {span[1]} min, e aceita até {top} min quando o tema pede.", "Corte enrolação ou acrescente um ponto novo."))
    first = re.split(r"(?<=[.!?…])\s+", body.strip(), maxsplit=1)[0]
    if len(first.split()) > r["max_palavras_primeira_frase"]:
        out.append(_f("aviso", "roteiro", "roteiro.abertura", f"A primeira frase tem {len(first.split())} palavras. Abertura longa perde gente nos primeiros 15 segundos.", "Comece pela pergunta ou pela cena mais forte, em até " + str(r["max_palavras_primeira_frase"]) + " palavras."))
    if r["numeros_por_extenso"]:
        nums = re.findall(r"\d[\d.,]*", body)
        if nums:
            out.append(_f("aviso", "roteiro", "roteiro.numeros", f"Há números em dígitos ({', '.join(nums[:4])}{'…' if len(nums) > 4 else ''}). A voz sintética lê melhor por extenso.", "Escreva por extenso: mil novecentos e oito."))
    prom = _found(body, r["palavras_de_promessa"])
    if prom:
        out.append(_f("erro", "roteiro", "roteiro.promessa", "O roteiro promete resultado: " + ", ".join(prom) + ". O canal nunca promete cura, dinheiro ou previsão.", "Reescreva como história ou análise, sem garantia."))
    sens = _found(body, r["palavras_sensacionalistas"])
    if sens:
        out.append(_f("aviso", "roteiro", "roteiro.sensacionalismo", "Palavras sensacionalistas no roteiro: " + ", ".join(sens) + ".", "Troque por fato e fonte."))
    out += _legal_findings(body, rules)
    gen = _found(body, (rules.get("geopolitica") or {}).get("generalizacoes") or []) if (rules.get("geopolitica") or {}).get("ativo") else []
    if gen:
        out.append(_f("aviso", "roteiro", "roteiro.generalizacao", "Generalização sobre um povo: " + ", ".join(gen) + ".", "Fale do governo, da instituição ou do documento, com fonte, e não de um povo inteiro."))
    camp = _found(body, r.get("palavras_de_campanha") or [])
    if camp:
        out.append(_f("erro", "roteiro", "roteiro.campanha", "O roteiro faz campanha: " + ", ".join(camp) + ". O canal analisa política, mas não pede voto.", "Troque o pedido por análise: fatos, fontes e os dois lados."))
    atq = _found(body, r.get("palavras_de_ataque") or [])
    if atq:
        out.append(_f("aviso", "roteiro", "roteiro.ataque", "Termos de ataque político no roteiro: " + ", ".join(atq) + ".", "Descreva a posição pelo que a pessoa ou o grupo diz e faz, sem rótulo ofensivo."))
    cites = len(_CITE.findall(body))
    if cites < r["citar_fontes_minimo"]:
        out.append(_f("aviso", "roteiro", "roteiro.fontes", f"Só achei {cites} citações de fonte (o canal pede pelo menos {r['citar_fontes_minimo']}).", "Diga em voz alta quem escreveu o quê e quando."))
    if _MARKS.search(text or ""):
        out.append(_f("erro", "roteiro", "roteiro.marcacoes", "Há marcações de produção no texto ([B-ROLL], [TELA]...). Elas seriam narradas.", "Use a “narração limpa” do roteiro (aba Ideias)."))
    caps = [s for s in re.split(r"(?<=[.!?])\s+", body) if len(s.split()) > 3 and _caps_ratio(s) > 0.7]
    if caps:
        out.append(_f("aviso", "roteiro", "roteiro.caixa_alta", "Há frases inteiras em CAIXA ALTA; a voz pode ler soletrando.", "Escreva em frase normal."))
    if not [x for x in out if x["nivel"] in ("erro", "aviso")]:
        out.append(_f("ok", "roteiro", "roteiro.ok", f"Roteiro dentro das regras (~{minutes} min)."))
    return {"palavras": words, "minutos": minutes, "achados": out}


def editorial_footer(ch: dict | None) -> str:
    """Aviso editorial que entra no fim da descrição de todo vídeo do canal."""
    j = effective(ch).get("juridico") or {}
    return (j.get("aviso_editorial") or "").strip() if j.get("ativo") else ""


def project_checks(project: dict, ch: dict | None) -> dict:
    """Verificação antes de publicar: título, miniatura, descrição e roteiro de um vídeo pronto, contra as regras do canal."""
    from . import metadata
    rules = effective(ch)
    yt = project["meta"].get("youtube") or {}
    findings: list[dict] = []
    if not yt:
        findings.append(_f("erro", "publicacao", "publicacao.sem_metadados", "Ainda não há título, descrição e tags.", "Use Gerar sugestões na tela Publicar."))
    else:
        findings += lint_title(yt.get("title", ""), rules)
        sel = (project["meta"].get("thumbnail") or {})
        v = next((x for x in sel.get("variants", []) if x["i"] == sel.get("selected")), None)
        findings += lint_thumb(v["text"] if v else yt.get("thumb_text", ""), rules)
        starts, total = metadata.timeline(project["scenes"])
        findings += lint_description(metadata.final_description(yt, project["scenes"], editorial_footer(ch)), rules, total / 60, bool(metadata.resolve_chapters(yt.get("chapters", []), project["scenes"])))
    if project["meta"].get("kind") != "clip":
        findings += lint_script(project["text"], rules)["achados"]
    erros = [x for x in findings if x["nivel"] == "erro"]
    return {"achados": findings, "erros": len(erros), "avisos": sum(1 for x in findings if x["nivel"] == "aviso"), "pode_enviar": not erros}


# --------------------------------------------------------------------------- impor as regras no que o LLM devolve
def _sentence_case(t: str) -> str:
    low = t.lower()
    return re.sub(r"(^|[.!?:]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), low, count=0)


def _clip_title(t: str, n: int) -> str:
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return cut or t[:n]


def enforce_metadata(yt: dict, rules: dict) -> list[str]:
    """Corrige o que o LLM devolveu contra as regras (caixa alta, palavras proibidas, tamanho, texto da miniatura). Devolve o que foi ajustado."""
    notes, t = [], rules["titulo"]
    good, seen = [], set()
    for title in yt.get("titles", []):
        orig = title
        if not t["permitir_caixa_alta"] and _caps_ratio(title) > 0.6 and len(title.split()) > 2:
            title = _sentence_case(title)
            notes.append(f"título em caixa alta convertido: “{orig}”")
        if _found(title, t["palavras_proibidas"]):
            notes.append(f"título descartado por palavra proibida: “{orig}”")
            continue
        clipped = _clip_title(title, t["max_caracteres"])
        if clipped != title:
            notes.append(f"título encurtado para {t['max_caracteres']} caracteres")
            title = clipped
        if title.lower() not in seen:
            seen.add(title.lower())
            good.append(title)
    if good:
        yt["titles"], yt["title"] = good, good[0]
    elif yt.get("titles"):
        notes.append("todos os títulos sugeridos violavam as regras: edite à mão")
    m = rules["miniatura"]["max_palavras"]
    words = (yt.get("thumb_text") or "").split()
    if len(words) > m:
        yt["thumb_text"] = " ".join(words[:m])
        notes.append(f"texto da miniatura cortado para {m} palavras")
    yt["hashtags"] = (yt.get("hashtags") or [])[: rules["descricao"]["max_hashtags"]]
    return notes


# --------------------------------------------------------------------------- revisão do roteiro com IA
def review_system(ch: dict | None) -> str:
    return ("Você é editor de roteiros de YouTube. Avalie o ROTEIRO contra as regras do canal abaixo e responda SOMENTE com JSON com estas chaves: "
            '"veredito" (1 a 2 frases honestas), "tese" (a tese própria que o roteiro defende, ou "não encontrei"), "fontes_citadas" (lista curta de quem/obra o texto cita), '
            '"pontos_fortes" (lista), "riscos" (lista de objetos com "trecho" curto, "problema" e "sugestao"), "pontos_de_saida" (lista de objetos com "aprox" '
            '(minuto aproximado), "risco" e "solucao"), "abertura_sugerida" (uma abertura melhor de até 40 palavras, ou "" se a atual for boa) e "originalidade" '
            '(objeto com "nota" de 1 a 5 e "motivo"). Não invente fatos; se duvidar de um fato, aponte em "riscos".\n\n' + context_text(ch))
