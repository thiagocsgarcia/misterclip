"""Plano de Shorts de um canal: estratégia, comparação dos dois caminhos do Programa de Parcerias e banco de ideias por vídeo.

As ideias-base vêm de 12 modelos preenchidos com o tema de cada vídeo do calendário; o botão "gerar ideias a partir do roteiro"
as substitui por ideias escritas pelo LLM em cima do texto real. Cada ideia traz gancho, duração ideal, final em laço e dica visual.
Os números do YouTube vêm das páginas oficiais e de estimativas de terceiros (marcadas como tal); confirme no YouTube Studio.
"""
import re

VERSION = 2
TYPE_IDS = ["trecho", "mito", "ia_hoje", "frase", "pergunta", "tres", "erro", "ponte", "cliff", "enquete", "bastidor", "citacao"]

# id, nome, gancho (começa pelo tema), duração ideal, faixa, final em laço (frase que fica "aberta" e continua no gancho), dica visual
TEMPLATES = [
    ("trecho", "Trecho mais forte do vídeo", "{nome}: a parte que quase ninguém explica direito.", 35, "30 a 45 s", "E é exatamente aqui que entra…",
     "Corte o momento de maior tensão do vídeo. O botão Gerar Shorts do vídeo pronto já faz isto."),
    ("mito", "Mito ou verdade", "Você já ouviu falar de {nome}, mas o que contaram está pela metade.", 40, "35 a 45 s", "…e a outra metade muda tudo, porque",
     "Mostre o mito na tela e risque-o no meio do Short."),
    ("ia_hoje", "E hoje, com a IA?", "Se {nome} visse uma inteligência artificial hoje, esta seria a primeira coisa que diria.", 40, "35 a 45 s",
     "…e a resposta é inquietante, porque", "Imagem do mestre ao lado de uma tela de computador."),
    ("frase", "Uma frase, uma ideia", "{nome} cabe em uma frase, e ela explica quase tudo.", 22, "15 a 25 s", "…e por isso, mais uma vez:",
     "Frase grande na tela, sem cortes rápidos, voz calma."),
    ("pergunta", "Pergunta que fica", "Responda sem pensar: o que {nome} tem a ver com o seu dia de hoje?", 25, "20 a 30 s",
     "…pense na sua resposta e escute de novo:", "Pergunta em texto grande, 1 segundo de silêncio e depois a explicação."),
    ("tres", "Três fatos rápidos", "3 coisas sobre {nome} que mudam o jeito de olhar o assunto.", 40, "35 a 45 s", "E a terceira é a que começa tudo:",
     "Numere na tela (1, 2, 3) e deixe a mais forte para o fim."),
    ("erro", "O erro comum", "O erro número um de quem estuda {nome}, e como evitá-lo.", 30, "25 a 35 s", "E o erro começa justamente com…",
     "Mostre o erro riscado e depois a versão certa."),
    ("ponte", "Mestre contra a máquina", "O que {nome} e a inteligência artificial têm em comum vai te surpreender.", 45, "40 a 45 s",
     "…e a ligação entre os dois é", "Tela dividida: o antigo em cima e o moderno embaixo."),
    ("cliff", "Parte 1 de 2", "Isto é só metade da história de {nome}.", 35, "30 a 40 s", "…a segunda metade está no vídeo completo, e começa assim:",
     "Corte exatamente na virada, sem resolver a história."),
    ("enquete", "Enquete", "Pergunto a você: {nome} é sabedoria ou ilusão? Eu respondo a melhor resposta.", 20, "15 a 25 s",
     "…e você, o que pensa? Pense e veja outra vez:", "Duas opções escritas na tela."),
    ("bastidor", "Em 5 imagens", "{nome} contado em 5 imagens, em 30 segundos.", 30, "25 a 35 s", "…e a quinta imagem leva de volta à primeira:",
     "Cinco imagens do vídeo em sequência rápida, uma a cada 5 ou 6 segundos."),
    ("citacao", "Citação", "Uma frase sobre {nome} que serve para a sua semana.", 25, "20 a 30 s", "…repetindo, para fixar:",
     "Citação curta em destaque, música baixa."),
]
CTA = "Ao publicar, use “Vídeo relacionado” e escolha o vídeo completo; fixe um comentário com o título do vídeo longo."
SCHEDULE = [(1, "trecho"), (3, None)]  # dias depois da data do vídeo longo; o segundo Short alterna o tipo
ROTATE = ["mito", "ia_hoje", "tres", "erro", "ponte", "cliff", "pergunta", "bastidor"]

SYSTEM_IDEAS = (
    "Você é estrategista de YouTube Shorts para um canal em português do Brasil sobre ocultismo, filosofia, tecnologia e futurismo. "
    "Com base no ROTEIRO de um vídeo longo, crie 12 ideias de Shorts que levem gente nova ao vídeo completo. Cada ideia é um objeto com: "
    '"tipo" (um de: ' + ", ".join(TYPE_IDS) + '), "gancho" (a primeira frase falada, até 18 palavras, que prende nos 2 primeiros segundos, sem "olá" e sem apresentação), '
    '"duracao_s" (número entre 15 e 45), "final" (última frase do Short, que fica aberta e continua naturalmente no gancho para o Short rodar em laço) '
    'e "visual" (uma dica de imagem em uma frase). Não repita ganchos, use fatos e frases que realmente estão no roteiro, sem sensacionalismo '
    'e sem prometer nada. Evite as palavras "segredo", "revelado" e "ninguém conta", e não comece com "você sabia". '
    'Prefira uma afirmação concreta, uma pergunta específica ou um contraste entre o antigo e o moderno. Responda SOMENTE com JSON no formato {"ideias": [...]}.'
)


def nome_do_tema(title: str) -> str:
    base = title.split(":")[0].strip() if ":" in title else title.strip()
    if len(base) > 45:
        base = base[:45].rsplit(" ", 1)[0]
    return base


def _idea(n: int, k: int, t: tuple) -> dict:
    return {"id": f"s{n}-{k}", "tipo": t[0], "nome": t[1], "gancho": "", "duracao": t[3], "faixa": t[4], "final": t[5], "visual": t[6],
            "cta": CTA, "dia": None, "status": "ideia", "nota": "", "origem": "modelo"}


def ideas_for(video: dict) -> list[dict]:
    nome = nome_do_tema(video["titulo"])
    out = []
    for k, t in enumerate(TEMPLATES, start=1):
        i = _idea(video["n"], k, t)
        i["gancho"] = t[2].format(nome=nome)
        out.append(i)
    # agenda padrão: 2 Shorts por vídeo longo (um dia depois e três dias depois)
    for (offset, tipo), pos in zip(SCHEDULE, range(len(SCHEDULE))):
        tipo = tipo or ROTATE[video["n"] % len(ROTATE)]
        for i in out:
            if i["tipo"] == tipo:
                i["dia"], i["status"] = offset, "agendado"
                break
    return out


def from_llm(video: dict, data: dict) -> list[dict]:
    """Converte a resposta do LLM em ideias válidas; devolve [] se vier algo inútil."""
    meta = {t[0]: t for t in TEMPLATES}
    out, seen = [], set()
    for k, r in enumerate((data.get("ideias") or [])[:16], start=1):
        tipo = str(r.get("tipo") or "").strip()
        hook = " ".join(str(r.get("gancho") or "").split())
        if tipo not in meta or not hook or hook.lower() in seen:
            continue
        try:
            dur = int(round(float(r.get("duracao_s") or meta[tipo][3])))
        except (TypeError, ValueError):
            dur = meta[tipo][3]
        dur = max(15, min(45, dur))
        t = meta[tipo]
        i = _idea(video["n"], len(out) + 1, t)
        i.update(gancho=hook[:220], duracao=dur, faixa=f"{max(15, dur - 5)} a {min(45, dur + 5)} s",
                 final=" ".join(str(r.get("final") or t[5]).split())[:220], visual=" ".join(str(r.get("visual") or t[6]).split())[:220], origem="roteiro")
        seen.add(hook.lower())
        out.append(i)
    return out if len(out) >= 10 else []


def merge(video: dict, fresh: list[dict]) -> list[dict]:
    """Troca as ideias-base pelas novas, mas preserva o que você já mexeu (agendado, gravado, publicado ou com nota)."""
    kept = [i for i in video.get("shorts", []) if i["status"] in ("gravado", "publicado") or i.get("nota") or (i["status"] == "agendado" and i.get("origem") == "roteiro")]
    kept_ids = {i["id"] for i in kept}
    out = list(kept)
    for i in fresh:
        if i["id"] in kept_ids:
            i["id"] = f"{i['id']}b"
        out.append(i)
    # garante a agenda padrão se nada ficou agendado
    if not any(i["dia"] is not None for i in out):
        for (offset, _), pick in zip(SCHEDULE, out[len(kept):]):
            pick["dia"], pick["status"] = offset, "agendado"
    return out


# ------------------------------------------------------------------ conteúdo estratégico
STRATEGY = {
    "objetivo": "Levar gente nova para os vídeos longos e juntar inscritos. Short não é o produto: é a porta de entrada. Quem gosta do trecho vai até o vídeo completo.",
    "funil": [
        ["Descobrir", "O Short aparece para quem nunca viu o canal. Nos dois primeiros segundos ele precisa prender."],
        ["Se inscrever", "Inscritos valem para os dois caminhos do Programa de Parcerias. É onde o Short mais ajuda."],
        ["Ir ao vídeo longo", "Pelo recurso “Vídeo relacionado” e pelo comentário fixado. É ali que nascem as horas de exibição."],
        ["Voltar", "A série dos arcanos e as playlists seguram a pessoa por mais de um vídeo."],
    ],
    "cadencia": "4 Shorts por semana, sempre amarrados a um vídeo longo: um no dia seguinte à publicação e outro 3 dias depois. Assim cada vídeo longo ganha uma segunda onda de visitas.",
    "regras": [
        "Primeiros 2 segundos: a frase mais forte, escrita na tela e falada. Nada de “olá” nem de apresentação.",
        "Duração ideal de 20 a 40 segundos. Shorts curtos são vistos até o fim com mais frequência, e isso conta a favor.",
        "Um Short, uma ideia. Se precisa de duas, são dois Shorts.",
        "Final em laço: a última frase fica aberta e continua na primeira. Quem deixa rodar reassiste sem perceber.",
        "Legenda grande no meio da tela, longe da parte de baixo onde ficam os botões do YouTube.",
        "Sem link no texto (não funciona): use “Vídeo relacionado” e o comentário fixado com o título do vídeo longo.",
        "Publique de manhã ou no começo da noite e responda os comentários na primeira hora.",
    ],
    "medir": [
        "Vistos até o fim ou deslizados: procure manter mais de 70% de quem fica.",
        "Inscritos ganhos por Short: os que ganham inscritos merecem outras versões.",
        "Visitas aos vídeos longos vindas de Shorts (Análises > Origem de tráfego > Feed de Shorts, dentro do vídeo longo).",
        "Tempo médio assistido acima de 100% quer dizer que o laço está funcionando.",
    ],
}

PATHS = {
    "caminhos": [
        {"id": "horas", "nome": "Caminho das horas (vídeos longos)",
         "hoje": "1.000 inscritos e 4.000 horas de exibição públicas nos últimos 12 meses.",
         "depois": "A partir de 1º/02/2027, para quem ainda não está no programa: 8.000 horas qualificadas em 365 dias.",
         "conta": "Só o tempo assistido nos vídeos longos. O tempo assistido nos Shorts não entra nessas horas.",
         "esforco": "Com ~5 min assistidos por pessoa, 4.000 h são cerca de 48 mil visualizações de vídeos longos; 8.000 h, cerca de 96 mil."},
        {"id": "shorts", "nome": "Caminho das visualizações de Shorts",
         "hoje": "1.000 inscritos e 10 milhões de visualizações de Shorts em 90 dias (versão antiga das regras).",
         "depois": "A partir de 1º/02/2027, para novos: 20 milhões de visualizações de Shorts em 90 dias.",
         "conta": "Só as visualizações dos Shorts. As visualizações dos vídeos longos não somam aqui.",
         "esforco": "20 milhões em 90 dias são mais de 220 mil visualizações por dia, todos os dias, durante 3 meses."},
    ],
    "degrau": "Primeiro degrau (recursos de apoio dos fãs, ainda sem anúncios): 500 inscritos, 3 envios públicos em 90 dias e 3.000 h de vídeos longos ou 3 milhões de visualizações de Shorts. As páginas do YouTube divergem sobre os números atuais.",
    "separado": "As duas contagens são separadas e não se somam: 15 mil horas de Shorts não valem nada para o caminho das horas, e 1 milhão de visualizações de vídeos longos não vale nada para o caminho dos Shorts. O que vale para os dois é o mesmo: 1.000 inscritos. Por isso o Short ajuda a conseguir inscritos, e o vídeo longo ajuda a conseguir horas.",
    "receita": [
        "Vídeos longos: o criador fica com 55% da receita de anúncios. Receita por mil views (RPM) costuma ficar entre US$ 1 e US$ 10, com mediana perto de US$ 2,30 (estimativas de terceiros).",
        "Shorts: o criador fica com 45% de um conjunto de receita dividido entre todos. RPM de cerca de US$ 0,03 a US$ 0,08 por mil views (estimativas de terceiros), algo como R$ 0,36 a R$ 1,03 no Brasil. É uma fração do RPM dos longos.",
        "A partir de 02/2027, para ganhar dinheiro com Shorts mesmo estando no programa, será preciso manter 10 milhões de visualizações de Shorts a cada 90 dias. Abaixo disso, o canal continua no programa e ganha só com os vídeos longos.",
    ],
    "recomendacao": {
        "caminho": "Caminho das horas, com os Shorts como funil",
        "motivos": [
            "Seu formato é ensaio narrado de 8 a 12 minutos: cada visualização rende minutos de exibição, que é exatamente o que o caminho das horas pede.",
            "O caminho dos Shorts exige cerca de 200 vezes mais visualizações (20 milhões contra algo como 100 mil) e a receita por visualização é muito menor.",
            "O seu assunto pede explicação e contexto. O Short desperta a curiosidade; quem quer entender fica para o vídeo longo.",
            "Os Shorts ajudam justo no que os dois caminhos exigem igual: os 1.000 inscritos.",
        ],
        "quando_mudar": "Só vale perseguir o caminho dos Shorts se um Short estourar de verdade (milhões de visualizações). Nesse caso, mantenha o plano e aproveite a onda levando as pessoas aos vídeos longos.",
    },
    "fontes": [
        ["Regras do Programa de Parcerias (YouTube)", "https://support.google.com/youtube/answer/72851"],
        ["Mudanças do programa em 2027 (blog oficial)", "https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn/"],
        ["RPM de Shorts (AIR Media-Tech)", "https://air.io/pt/monetization/what-rpm-can-you-expect-from-shorts-in-2026"],
    ],
}


def strategy() -> dict:
    return {"estrategia": STRATEGY, "caminhos": PATHS, "tipos": [{"id": t[0], "nome": t[1], "faixa": t[4]} for t in TEMPLATES]}
