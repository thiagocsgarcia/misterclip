"""Rascunho de roteiro para um vídeo do calendário.

O LLM da andes escreve em duas etapas: primeiro o ESBOÇO (tese, gancho, seções e o que cobrir em cada uma), depois cada seção
com a anterior como contexto, o que mantém o roteiro de 8 a 12 minutos coerente. O resultado é só um RASCUNHO: o autor revisa,
confere os fatos e edita antes de virar vídeo. O que o modelo não sabe com certeza vai para "incertezas", não para o texto.
"""
import pathlib
import re

from . import channel_content_c, channel_rules, ptnum

MARK = re.compile(r"\[(?:B-ROLL|TELA|SOM|QUEBRA|TEASER|SAÍDA)[^\]]*\]", re.IGNORECASE)


def style_example(words: int = 420) -> str:
    """Início de um roteiro aprovado do canal, usado como exemplo de ritmo, clareza e atribuição de fontes (não de conteúdo)."""
    try:
        t = (pathlib.Path(__file__).parent / "estilo_exemplo.txt").read_text(encoding="utf-8")
    except OSError:
        return ""
    return " ".join(t.split()[:words])

OUTLINE_SYSTEM = (
    "Você é roteirista de YouTube em português do Brasil e vai planejar o ESBOÇO de uma narração (vídeo sem rosto, só voz e imagens). "
    "Responda SOMENTE com JSON com estas chaves: "
    '"tese" (a ideia própria que o vídeo defende, em 1 a 2 frases), '
    '"gancho" (a abertura falada, de até 35 palavras: uma pergunta ou cena forte; sem "olá" e sem pedir inscrição), '
    '"secoes" (lista de {n} a {m} objetos com "titulo", "objetivo", "pontos": de 3 a 5 ideias ou fatos a cobrir (prefira o específico e o surpreendente: um número, uma data, um nome, uma cena; cada ponto cita a fonte quando houver) e "gancho_final": uma frase de tensão que empurra para a próxima seção, '
    '"laco" (a pergunta ou o mistério aberto no gancho e só respondido perto do fim: é o que segura o espectador), '
    '"reviravolta" (o ponto em que a expectativa do espectador se desfaz; vai no meio), '
    '"fecho" (como o vídeo termina: devolve a pergunta ao espectador, sem pedir curtida), '
    '"fontes" (autores, obras e instituições REAIS que você conhece com segurança e que o roteiro pode citar) e '
    '"incertezas" (afirmações que o autor precisa conferir antes de gravar). '
    "Siga esta estrutura (a do roteiro de referência do canal): gancho com laço aberto, prova rápida, contexto, pontos principais, um teaser no meio e um final forte que devolve uma pergunta. "
    "RETENÇÃO é o objetivo: cada seção abre com algo concreto (cena, número, contradição), nunca com definição; o espectador deve sempre ter uma pergunta na cabeça; "
    "corte a enrolação; só o que é verdadeiro e verificável pode surpreender (surpresa inventada é proibida). Sem clickbait que o vídeo não entrega. "
    "Nunca invente citação, número, data ou fonte: se não tem certeza, ponha em \"incertezas\" e fora do texto. "
    "Pessoa viva só pelo que diz e faz em público, com fonte, sem acusação.\n\n{ctx}"
)

SECTION_SYSTEM = (
    "Você escreve a NARRAÇÃO FALADA de um vídeo de YouTube em português do Brasil. Escreva só o trecho pedido, como texto corrido para ser lido em voz alta: "
    "parágrafos curtos, frases de até 28 palavras, tom calmo e inteligente, sem gírias forçadas. "
    "Proibido: títulos, listas, marcadores, markdown, emojis, parênteses de direção, marcações como [B-ROLL], e frases de 'inscreva-se'. "
    "Escreva todos os números por extenso. Atribua cada afirmação a quem a fez (“segundo…”, “escreveu em…”); use “teria” quando a fonte for indireta. "
    "Técnicas de retenção (use sem exagero): comece o trecho por um fato, cena ou contradição concreta; alterne frase curta e frase longa; faça uma pergunta ao espectador e responda só depois; "
    "dê um exemplo específico em vez de uma ideia abstrata; termine o trecho com tensão, uma promessa ou uma pergunta que puxa o próximo. Corte adjetivo vazio e repetição. "
    "Nunca acuse pessoa viva de crime nem de caráter. Não repita o que o trecho anterior já disse. Responda SOMENTE com o texto do trecho.\n\n{ctx}"
)


MARKS_RULE = (
    " Marque a produção em linhas separadas, no meio do texto: [B-ROLL: o que aparece na imagem], [TELA: texto curto na tela], [SOM: efeito ou música], "
    "[QUEBRA: o que muda no ritmo], [TEASER] (só na seção do meio, prometendo a virada) e [SAÍDA: risco de o espectador sair | como este trecho resolve]. "
    "Use uma marcação nova a cada cerca de sessenta segundos de fala (125 palavras), e pelo menos uma [SAÍDA] por seção. As marcações não contam como fala."
)


def target_words(rules: dict, formato: str | None) -> tuple[int, int]:
    """(mínimo, máximo) de palavras que o formato pede, pelas regras do canal."""
    r = rules["roteiro"]
    lo, hi = (r["minutos_por_formato"].get(formato or "ensaio") or r["minutos_por_formato"].get("ensaio") or [8, 12])
    wpm = r["palavras_por_minuto"] or 125
    return int(lo * wpm), int(hi * wpm)


def clean(text: str, keep_marks: bool = False) -> str:
    """Tira o que o modelo costuma deixar escapar (markdown, títulos, colchetes) e passa os números para extenso.
    Com `keep_marks`, as marcações de produção ([B-ROLL: ...], [TELA: ...], [SOM: ...], [QUEBRA: ...], [TEASER], [SAÍDA: ...]) ficam, cada uma na sua linha."""
    t = re.sub(r"```.*?```", "", text, flags=re.S)
    marks: list[str] = []
    if keep_marks:
        def hold(m):
            marks.append(" ".join(m.group(0).split()))
            return f"\n\n@@M{len(marks) - 1}@@\n\n"
        t = MARK.sub(hold, t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"^[ \t]{0,3}#{1,6}[ \t].*$", "", t, flags=re.M)
    t = re.sub(r"^[ \t]*(?:[-*•]|\d+[.)])[ \t]+", "", t, flags=re.M)
    t = re.sub(r"[*_`>]+", "", t)
    t = ptnum.expand_numbers(t)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", t.replace("\r", ""))]
    paras = [re.sub(r"^@@M(\d+)@@$", lambda m: marks[int(m.group(1))], p) for p in paras if p]
    return "\n\n".join(paras)


def exit_points(marked: str, titles: list[str] | None = None) -> list[dict]:
    """Pontos de saída do espectador, lidos das marcações [SAÍDA: risco | solução]."""
    out = []
    for i, m in enumerate(re.finditer(r"\[SAÍDA:\s*([^\]|]*)\|?([^\]]*)\]", marked, flags=re.IGNORECASE)):
        out.append({"ponto": (titles[i] if titles and i < len(titles) else f"Trecho {i + 1}"), "risco": m.group(1).strip(), "solucao": m.group(2).strip()})
    return out


def _pillar(plan: dict, video: dict) -> str:
    for p in plan.get("pilares", []) or []:
        if p.get("id") == video.get("pilar") or p.get("nome") == video.get("pilar"):
            return f"{p.get('nome', '')}: {p.get('descricao', '') or p.get('foco', '')}".strip(": ")
    return str(video.get("pilar") or "")


def write(ch: dict, video: dict, backend, progress, stages, stage, marks: bool = False) -> dict:
    rules = channel_rules.effective(ch)
    ctx = channel_rules.context_text(ch)
    lo, hi = target_words(rules, video.get("formato"))
    goal = (lo + hi) // 2
    plan = ch["plan"]
    brief = (f"Título do vídeo: {video['titulo']}\nPilar: {_pillar(plan, video) or '—'}\nFormato: {video.get('formato') or 'ensaio'}\n"
             f"Série: {video.get('serie') or '—'}\nTamanho da narração: de {lo} a {hi} palavras (alvo {goal}).")

    stages(progress, [("outline", "Planejar o esboço do roteiro", 1), ("sections", "Escrever as seções", 6)])
    stage(progress, "outline", 0)
    progress(0.03, "planejando o esboço")
    ex = style_example()
    ref = ("\n\nROTEIRO DE REFERÊNCIA DO CANAL (imite o ritmo, a clareza e o cuidado com as fontes; NÃO copie o assunto nem as frases):\n" + ex) if ex else ""
    system = OUTLINE_SYSTEM.replace("{n}", "5").replace("{m}", "8").replace("{ctx}", ctx + ref)
    out = backend.llm_json(system, brief)
    secoes = [s for s in (out.get("secoes") or []) if isinstance(s, dict) and str(s.get("titulo", "")).strip()][:8]
    if len(secoes) < 3:
        raise RuntimeError("o LLM não montou um esboço utilizável; tente de novo")
    tese = str(out.get("tese") or "").strip()[:500]
    gancho = str(out.get("gancho") or "").strip()
    fecho = str(out.get("fecho") or "").strip()
    stage(progress, "outline", 1)

    stages(progress, [("outline", "Planejar o esboço do roteiro", 1), ("sections", "Escrever as seções", len(secoes))])
    stage(progress, "outline", 1)
    system = SECTION_SYSTEM.replace("{ctx}", ctx + ref) + (MARKS_RULE if marks else "")
    per = max(120, round((goal - 60) / len(secoes)))
    parts: list[str] = []
    for i, sec in enumerate(secoes):
        stage(progress, "sections", i)
        progress(0.08 + 0.9 * i / len(secoes), f"escrevendo a seção {i + 1} de {len(secoes)}: {str(sec['titulo'])[:50]}")
        pontos = "\n".join(f"- {p}" for p in (sec.get("pontos") or []) if str(p).strip())
        ask = [f"Tese do vídeo: {tese}", f"Título do vídeo: {video['titulo']}", f"Seção {i + 1} de {len(secoes)}: {sec['titulo']}",
               f"Objetivo: {sec.get('objetivo', '')}", f"Cubra, nesta ordem:\n{pontos}", f"Tamanho: cerca de {per} palavras."]
        if sec.get("gancho_final"):
            ask.append(f"Termine o trecho com esta tensão (reescreva à vontade): {sec['gancho_final']}")
        if i == 0 and out.get("laco"):
            ask.append(f"Abra o laço, sem responder: {out['laco']}")
        if i == len(secoes) // 2 and out.get("reviravolta"):
            ask.append(f"Aqui entra a reviravolta: {out['reviravolta']}")
        if i == len(secoes) - 1 and out.get("laco"):
            ask.append(f"Feche o laço aberto no início: responda {out['laco']}")
        if i == 0:
            ask.append(f"Comece EXATAMENTE por esta abertura (pode ajustar a redação, mantendo a ideia e até 35 palavras na primeira frase): {gancho}")
        else:
            ask.append("Trecho anterior (termina assim; continue dali sem repetir):\n" + parts[-1][-500:])
        if i == len(secoes) - 1:
            ask.append(f"Esta é a última seção. Feche assim: {fecho}")
        parts.append(clean(backend.llm_text(system, "\n".join(ask), max_tokens=int(per * (3.4 if marks else 2.6))), keep_marks=marks))
        stage(progress, "sections", i + 1)

    text = "\n\n".join(p for p in parts if p)
    narration = channel_content_c.narracao_limpa(text) if marks else text
    lint = channel_rules.lint_script(narration, rules, video.get("formato"))
    avisos = [{"nivel": a["nivel"], "mensagem": a["mensagem"]} for a in lint["achados"] if a["nivel"] in ("erro", "aviso")]
    titles = [str(s["titulo"]) for s in secoes]
    return {"texto": text, "narracao": narration, "pontos_de_saida": exit_points(text, titles) if marks else [], "palavras": lint["palavras"], "minutos": lint["minutos"], "tese": tese, "avisos": avisos,
            "fontes": [str(x)[:140] for x in (out.get("fontes") or [])][:15], "incertezas": [str(x)[:260] for x in (out.get("incertezas") or [])][:15]}
