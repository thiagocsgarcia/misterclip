"""Modelo de plano de 90 dias para um canal novo (nicho: filosofia + ocultismo + tecnologia + futurismo).

É só dado: cada canal recebe uma CÓPIA do plano ao ser criado e pode editá-la (título e estado de cada vídeo, notas).
Os números de metas são metas de planejamento, não promessas. Os dados de concorrentes foram colhidos em 22/11/2026
na busca pública do YouTube e são aproximados.
"""
import copy
import datetime as dt

from . import channel_rules, shorts_plan

TEMPLATE_ID = "ocultismo-tecnologia-90d"
TEMPLATE_NAME = "Filosofia + ocultismo + tecnologia · 90 dias"

SOURCES = [
    ["Regras do Programa de Parcerias (YouTube)", "https://support.google.com/youtube/answer/72851"],
    ["Mudanças do programa em 2027 (blog oficial)", "https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn/"],
    ["Conteúdo inautêntico: o que muda (TechCrunch, jul/2026)", "https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/"],
    ["Conteúdo inautêntico (Tubefilter, jul/2026)", "https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/"],
]

POSITIONING = {
    "promessa": "Ocultismo explicado com rigor e lido à luz da era das máquinas: o que alquimistas, herméticos e místicos já disseram sobre mente, criação e futuro.",
    "publico": "Pessoas curiosas por ocultismo, filosofia, tecnologia e futuro que estão cansadas de vídeos sensacionalistas e querem fontes, contexto e uma ideia nova a cada vídeo.",
    "voz": "Sóbria, cinematográfica e honesta. Sem sensacionalismo, sem proselitismo, com a fonte dita em voz alta (autor, obra, época).",
    "diferencial": "Quase ninguém em português cruza ocultismo e inteligência artificial com seriedade: nas buscas por esse cruzamento, o melhor resultado tem cerca de 9,5 mil views e o resto são cortes de poucos minutos.",
    "evitar": [
        "Títulos em CAIXA ALTA com 'segredos', 'mistérios revelados' ou 'o que escondem de você'.",
        "Prometer cura, dinheiro ou previsões; falar como especialista de saúde, direito ou finanças.",
        "Vídeos com a mesma estrutura e os mesmos visuais repetidos sem uma ideia própria em cada um.",
    ],
}

PILLARS = [
    {"id": "tradicoes", "nome": "Tradições e mestres", "peso": 30, "papel": "Porta de entrada pela busca",
     "texto": "Hermetismo, alquimia, cabala, gnosticismo, Eliphas Lévi, Blavatsky, Giordano Bruno. É conteúdo que as pessoas já procuram: vídeos completos de hermetismo de outros canais têm entre 215 mil e 456 mil views. Aqui vence quem for mais claro e mais fiel às fontes."},
    {"id": "arcanos", "nome": "Os 22 Arcanos da Era das Máquinas", "peso": 60, "papel": "Série assinatura (o que só o seu canal tem)",
     "texto": "Cada arcano maior do tarô vira um tema de tecnologia e futuro: O Mago é o prompt, A Torre é a bolha da IA, A Morte é a imortalidade digital. É série numerada, então quem gosta de um vídeo tem motivo para ver o próximo, e isso aumenta o tempo de exibição."},
    {"id": "futuro", "nome": "Futuro e consciência", "peso": 10, "papel": "Especiais pontuais",
     "texto": "Simulação, transumanismo, singularidade, consciência. Entra em especiais mais longos depois dos primeiros 60 dias, quando já houver audiência para sustentá-los."},
]

FORMATS = [
    {"id": "ensaio", "nome": "Ensaio narrado", "duracao": "8 a 12 min", "uso": "Formato padrão. Longo o bastante para gerar tempo de exibição e curto o bastante para a retenção não despencar."},
    {"id": "longo", "nome": "Aprofundamento", "duracao": "18 a 22 min", "uso": "Só nos temas com muita procura (ex.: cabala). Um por mês no máximo."},
    {"id": "shorts", "nome": "Shorts (cortes)", "duracao": "30 a 45 s", "uso": "Servem para trazer inscritos e levar gente aos vídeos longos. Atenção: o tempo assistido dos Shorts NÃO conta para as horas de exibição. O MisterClip corta os Shorts do vídeo pronto (botão Gerar Shorts) e a aba Shorts traz o plano e as ideias."},
]

CADENCE = {
    "videos_por_semana": 2, "shorts_por_semana": 4, "dias": "terça e sexta", "horario": "18h (ajuste depois pelo relatório de quando seu público está online)",
    "texto": "Dois vídeos por semana (a cada 3 ou 4 dias) fecham 26 vídeos em 90 dias. Constância importa mais que volume: melhor 2 por semana sem falhar do que 5 numa semana e nenhum na outra.",
}

GROWTH = [
    {"titulo": "Títulos e miniaturas que as pessoas clicam", "itens": [
        "Título em frase normal (não caixa alta), com uma pergunta ou uma tensão concreta e a palavra que a pessoa busca nos primeiros caracteres.",
        "Miniatura com no máximo 4 palavras e um único elemento forte (o MisterClip já gera 3 variações).",
        "Meta: taxa de cliques (CTR) acima de 4,5%. Abaixo de 4% depois de 48 h, troque a miniatura e depois o título."]},
    {"titulo": "Busca (SEO)", "itens": [
        "Nos vídeos 'porta de entrada', escreva o título como as pessoas pesquisam: 'O que é hermetismo', 'Eliphas Lévi quem foi'.",
        "Primeiras duas linhas da descrição com a ideia central; capítulos de ~90 s (o MisterClip gera); poucas tags, só as relevantes.",
        "Responda todos os comentários nas primeiras 2 horas: o YouTube lê isso como sinal de interesse."]},
    {"titulo": "Série e playlists (assistir um atrás do outro)", "itens": [
        "Playlist 'Os 22 Arcanos da Era das Máquinas', em ordem. Todo vídeo termina apontando para o próximo (tela final + fala).",
        "Fixe no topo do canal a playlist e o melhor vídeo porta de entrada."]},
    {"titulo": "Shorts e comunidades", "itens": [
        "4 Shorts por semana, amarrados aos vídeos longos (um no dia seguinte e outro 3 dias depois). Veja o plano completo na aba Shorts.",
        "Em vídeo pronto, use Gerar Shorts: o MisterClip escolhe os trechos e monta o corte vertical.",
        "Divulgue sem spam em grupos de ocultismo, filosofia e tecnologia (Telegram, Reddit, Discord, Instagram): ofereça a ideia, não só o link.",
        "Procure 5 canais pequenos do nicho por semana para conversa e participação em vídeos um do outro."]},
    {"titulo": "Revisão semanal (domingo, 30 min)", "itens": [
        "Registre os números na aba Métricas. Veja qual vídeo teve mais cliques e qual reteve mais.",
        "Regra: CTR baixo = mexa em título e miniatura. Retenção baixa nos primeiros 30 s = reescreva a abertura dos próximos. Um tema com o dobro de views dos outros = faça mais dele."]},
]

RETENTION = {
    "estrutura": [
        ["0:00 a 0:30", "Abertura que prende", "Comece pela pergunta ou pela cena mais forte. Diga o que a pessoa vai descobrir. Nada de 'olá pessoal, hoje vamos falar de'."],
        ["0:30 a 1:00", "Por que importa agora", "Ligue o tema a algo do presente (uma notícia de IA, uma dúvida comum)."],
        ["1:00 a 9:00", "Três atos", "Cada ato traz uma ideia e termina com um gancho que aponta para o próximo. A cada 60 a 90 s, uma virada ou uma imagem nova."],
        ["~60% do vídeo", "A virada", "O cruzamento inesperado: o que o místico disse e o que a máquina faz hoje. É o trecho que as pessoas comentam."],
        ["Final", "Fechamento e próximo vídeo", "Conclusão em uma frase, convite curto (15 s) e a indicação do próximo arcano. Sem repetir o vídeo inteiro."],
    ],
    "regras": [
        "Sem vinheta nem apresentação do canal nos primeiros 30 segundos.",
        "Cortar toda frase que não acrescenta nada. Vídeo de 12 min bem apertado retém mais que 15 min com enrolação.",
        "O MisterClip já troca de imagem a cada poucos segundos, tem capítulos e música que abaixa na fala: use isso a favor.",
        "Meta de retenção: tempo médio assistido acima de 38% e ~5 min nos vídeos de 13 min.",
    ],
}

MONETIZATION = {
    "ypp": [
        "Hoje (confirme em YouTube Studio > Monetização): 1.000 inscritos e 4.000 horas de exibição públicas nos últimos 12 meses.",
        "A partir de 1º/02/2027 (anúncio oficial de 10/08/2026): quem ainda não está no programa passa a precisar de 8.000 horas qualificadas em 365 dias (ou 20 milhões de views em Shorts em 90 dias). Quem já está no programa não é afetado.",
        "A página oficial não deixa claro se os 1.000 inscritos continuam exigidos nem como ficam pedidos já em análise: confira no Studio.",
        "Consequência prática: bater 4.000 h e 1.000 inscritos até 31/01/2027 e enviar o pedido antes de 1º/02 é possível, mas exige que um ou mais vídeos tenham desempenho acima da média. O plano B é seguir até 8.000 h (mais 3 a 6 meses).",
    ],
    "politica": [
        "O YouTube não monetiza conteúdo 'inautêntico': genérico ou repetitivo, que parece feito de molde, com poucas ideias próprias. Usar IA não é proibido; o que pesa é a falta de perspectiva própria e de variação.",
        "Seu roteiro é escrito por você, e isso é o ponto forte. Mantenha: opinião e ponto de vista em cada vídeo, fontes citadas, estrutura que varia de um vídeo para outro e visual coerente com o tema, não o mesmo molde.",
        "Evite fazer uma 'IA' falar como especialista em saúde, direito, finanças ou política.",
        "Se aparecer algo realista que possa enganar (pessoa, notícia, desastre), marque 'conteúdo alterado ou sintético' ao publicar. Ilustração claramente artística não precisa.",
    ],
    "etapas": [
        ["Dias 1 a 90", "Chegar ao programa", "Foco total em horas e inscritos. Já coloque links de afiliado (livros que você realmente cita, em Amazon ou Hotmart) na descrição desde o primeiro vídeo."],
        ["Mês 4 em diante", "Anúncios + apoio", "Receita de anúncios, e apoio dos fãs (Apoia.se, Pix, Membros do canal assim que liberar). Comece uma lista de e-mails."],
        ["Mês 6 em diante", "Produto próprio", "E-book ou mini-curso 'Os 22 Arcanos da Era das Máquinas'. Patrocínios quando a média passar de ~10 mil views por vídeo."],
    ],
    "meta_reais": "R$ 1.000 por mês: com receita de R$ 5 a R$ 15 por mil views no Brasil (estimativa de terceiros, varia muito), são ~67 mil a 200 mil views monetizadas por mês. É realista olhar para esse patamar entre o mês 6 e o 12, não no dia 90. Afiliados e apoio dos fãs podem cobrir parte.",
}

COMPETITORS = [
    {"nome": "História Oculta", "dados": "277 inscritos, 64 vídeos, 33 a 340 views por vídeo",
     "licao": "O modelo que NÃO funciona: títulos em CAIXA ALTA com 'segredos' e 'mistérios', temas espalhados (de nefilins a Diddy). É exatamente o padrão genérico que o YouTube penaliza."},
    {"nome": "Realidade Fantástica", "dados": "181 mil inscritos",
     "licao": "Venceu pela autoridade: 'ocultismo tratado de forma séria e fundamentada', com pesquisa e entrevistas. Rigor é diferencial."},
    {"nome": "Portal Espiritualidade", "dados": "119 mil inscritos", "licao": "Esoterismo clássico e filosofia, 'sem proselitismo'. Há público para tom neutro."},
    {"nome": "O Poder da Mente", "dados": "Vídeos de hermetismo com 369 mil e 456 mil views",
     "licao": "Prova de demanda por hermetismo completo. É o tema onde você deve entrar com clareza e fontes."},
    {"nome": "Barbarismo Esotérico", "dados": "215 mil views em 'Esse é o VERDADEIRO hermetismo'", "licao": "O tom 'o que realmente é' (corrigir mitos) rende cliques."},
    {"nome": "Zodiaco", "dados": "179 mil views no 'Iceberg do ocultismo'", "licao": "Formatos de camadas (iceberg) viralizam: boa ideia para um especial."},
    {"nome": "Nigredo", "dados": "38 mil views em 9 dias num vídeo novo", "licao": "Canal em ascensão: acompanhe o que ele publica."},
    {"nome": "Ocultismo × IA (a busca)", "dados": "Melhor resultado: 9,5 mil views; os demais, cortes com menos de 2 mil",
     "licao": "Oferta baixa. A demanda ainda não está provada, e é por isso que os primeiros vídeos testam o cruzamento junto com temas de busca garantida."},
]

WEEK_FOCUS = [
    ("Fundação", ["Escolher nome, foto e banner do canal (editável aqui)", "Preencher descrição do canal, links e e-mail comercial", "Criar as playlists 'Os 22 Arcanos…' e 'Tradições e mestres'", "Publicar os 2 primeiros vídeos e responder todos os comentários"]),
    ("Constância e busca", ["Revisar título e descrição dos 2 primeiros com base em como as pessoas pesquisam", "Preencher Métricas no domingo (primeira revisão semanal)", "Programar os vídeos da semana 3 e 4 com a Agenda"]),
    ("Primeiro teste de miniaturas", ["Para cada vídeo, escolher a miniatura mais forte entre as 3", "Se o CTR ficou abaixo de 4% após 48 h, trocar a miniatura", "Começar a divulgar em 2 comunidades do nicho (sem spam)"]),
    ("Revisão do dia 30", ["Comparar Métricas com as metas do dia 30", "Anotar quais 2 vídeos tiveram melhor CTR e retenção e por quê", "Ajustar os próximos 4 temas usando o que funcionou"]),
    ("Dobrar no que funcionou", ["Fazer mais um vídeo do tema que mais reteve", "Publicar os 4 Shorts da semana (aba Shorts) e anotar quais ganham inscritos", "Revisar a abertura (0 a 30 s) dos vídeos com pior retenção"]),
    ("Parcerias", ["Procurar 5 canais pequenos do nicho e propor participação cruzada", "Responder comentários e fixar a melhor pergunta como assunto do próximo vídeo", "Atualizar a tela final: sempre apontar para o próximo arcano"]),
    ("Alcance", ["Testar um título no formato 'o que realmente é…' em um tema de busca", "Verificar no Analytics de onde vêm as visitas (busca, sugeridos, externo)", "Responder se o público pede algum tema novo"]),
    ("Revisão do dia 56 (decisão)", ["Calcular as horas projetadas até 31/01/2027 (aba Métricas)", "Se a projeção ficar abaixo de 3.000 h, assumir o plano B (8.000 h) sem se frustrar", "Escolher o melhor vídeo para virar especial mais longo"]),
    ("Sprint 1", ["Manter 2 vídeos por semana e 4 Shorts", "Reaproveitar o melhor tema com outro ângulo", "Conferir a lista de verificação antes de cada publicação"]),
    ("Sprint 2", ["Reforçar os temas de busca com título otimizado", "Fazer a segunda rodada de parcerias", "Preencher Métricas toda semana"]),
    ("Sprint 3", ["Publicar um especial mais longo (18 a 22 min) se a retenção permitir", "Verificar se o pedido de monetização já está liberado no Studio", "Revisar a lista de verificação de conteúdo autêntico do canal inteiro"]),
    ("Sprint final", ["Se tiver atingido os requisitos, enviar o pedido ao Programa de Parcerias", "Se não, registrar as horas que faltam e a data estimada com a aba Métricas", "Planejar o segundo trimestre"]),
    ("Fechamento do dia 90", ["Comparar Métricas com as metas do dia 90", "Escrever o que funcionou e o que não funcionou", "Definir o plano dos próximos 90 dias (monetização e produto próprio)"]),
]

HOURS_GOAL = [20, 60, 130, 250, 420, 650, 950, 1350, 1850, 2450, 3150, 4000, 5000]
SUBS_GOAL = [10, 35, 80, 160, 280, 420, 580, 760, 940, 1100, 1250, 1400, 1550]
FLOOR_FACTOR = 0.25  # "piso": o mínimo aceitável é 25% da meta

MILESTONES = [
    {"dia": 30, "titulo": "Dia 30", "videos": 8, "inscritos": 170, "horas": 270, "ctr": "CTR acima de 4,5%", "retencao": "tempo médio assistido acima de 38%",
     "entrega": "Canal montado, 8 vídeos no ar, 2 playlists, primeiras miniaturas testadas e rotina de revisão semanal funcionando.",
     "piso": {"inscritos": 45, "horas": 65}},
    {"dia": 60, "titulo": "Dia 60", "videos": 16, "inscritos": 850, "horas": 1600, "ctr": "CTR acima de 5%", "retencao": "tempo médio assistido acima de 40%",
     "entrega": "16 vídeos, pelo menos 1 vídeo com mais de 5 mil views, Shorts rodando e decisão tomada entre o plano A (4.000 h até 31/01) e o plano B (8.000 h).",
     "piso": {"inscritos": 210, "horas": 400}},
    {"dia": 90, "titulo": "Dia 90", "videos": 26, "inscritos": 1550, "horas": 5000, "ctr": "CTR acima de 5%", "retencao": "tempo médio assistido acima de 40%",
     "entrega": "26 vídeos, série dos arcanos com 18 episódios publicados, pedido ao Programa de Parcerias enviado (ou data estimada clara).",
     "piso": {"inscritos": 390, "horas": 1250}},
]

SCENARIOS = [
    {"nome": "Conservador", "texto": "Canais novos costumam crescer devagar no começo. É um resultado comum: de 400 a 700 inscritos e de 900 a 1.500 horas em 90 dias. Já formaria base, mas a monetização ficaria para os meses 5 a 8."},
    {"nome": "Base", "texto": "Um ou dois vídeos acima da média trazem a maior parte das horas: de 900 a 1.500 inscritos e de 2.500 a 4.000 horas. É preciso acertar o tema, a miniatura e a retenção."},
    {"nome": "Otimista", "texto": "Um vídeo 'estoura' e carrega o canal: 4.000 h antes de 31/01. Não dá para planejar isso, mas dá para aumentar a chance com títulos de busca forte e retenção alta."},
]

CHECKLIST_PUBLISH = [
    "Tem opinião ou ponto de vista próprio e não só um resumo do que já existe?",
    "Cita as fontes (autor, obra, época) dentro do vídeo?",
    "A estrutura e as imagens são diferentes do último vídeo (não é o mesmo molde)?",
    "A abertura (0 a 30 s) tem pergunta ou cena forte e promete algo concreto?",
    "Título em frase normal, sem CAIXA ALTA e sem 'segredos revelados'?",
    "Miniatura com no máximo 4 palavras e um elemento forte?",
    "Descrição com ideia central nas duas primeiras linhas, capítulos e links de livros citados?",
    "Nada de promessa de cura, dinheiro ou previsão; nenhuma 'IA' dando conselho de saúde, direito ou finanças?",
    "Se há algo realista que possa enganar, marquei 'conteúdo alterado ou sintético'?",
    "Tela final aponta para o próximo vídeo da série?",
]

ARCANOS = [
    ("O Louco", "O Louco e o salto no escuro: a humanidade diante da inteligência artificial"),
    ("O Mago", "O Mago: por que digitar um prompt é uma forma de magia"),
    ("A Sacerdotisa", "A Sacerdotisa: o conhecimento que a IA guarda e ninguém consegue ler"),
    ("A Imperatriz", "A Imperatriz: a máquina que cria e o que a arte gerada por IA revela sobre a criação"),
    ("O Imperador", "O Imperador: quem manda na IA? Poder, Estado e Big Techs"),
    ("O Hierofante", "O Hierofante: dogma, tradição e o que o algoritmo aprendeu de nós"),
    ("Os Enamorados", "Os Enamorados: apaixonar-se por uma máquina"),
    ("O Carro", "O Carro: a corrida pela superinteligência"),
    ("A Força", "A Força: como domar a máquina sem destruí-la"),
    ("O Eremita", "O Eremita: silêncio, solidão e o direito de se desconectar"),
    ("A Roda da Fortuna", "A Roda da Fortuna: os algoritmos conseguem prever o seu destino?"),
    ("A Justiça", "A Justiça: o viés escondido nos algoritmos"),
    ("O Enforcado", "O Enforcado: o trabalho humano num mundo de máquinas"),
    ("A Morte", "A Morte: imortalidade digital e transumanismo"),
    ("A Temperança", "A Temperança: o grande trabalho da alquimia é fundir humano e máquina?"),
    ("O Diabo", "O Diabo: o algoritmo que prende a sua atenção"),
    ("A Torre", "A Torre: e se a bolha da IA estourar?"),
    ("A Estrela", "A Estrela: o futuro que ainda dá para escolher"),
]
NUMERALS = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII"]

EVERGREEN = [
    ("Hermetismo de verdade: o que Hermes Trismegisto ensinou e o que o Caibalion não diz", "ensaio"),
    ("Alquimia: o que os alquimistas realmente buscavam (e não era ouro)", "ensaio"),
    ("Eliphas Lévi: o homem que inventou o ocultismo moderno", "ensaio"),
    ("O Golem de Praga: a primeira inteligência artificial da história?", "ensaio"),
    ("Gnosticismo: a ideia de que o mundo é uma prisão e por que Matrix a ressuscitou", "ensaio"),
    ("Cabala e a Árvore da Vida explicadas do zero", "longo"),
    ("Giordano Bruno: o monge que morreu por defender um universo infinito", "ensaio"),
    ("Madame Blavatsky e a Teosofia: a mulher que levou o Oriente ao ocultismo ocidental", "ensaio"),
]


def _items() -> list[dict]:
    items, arc = [], 0
    for week in range(1, 14):
        for slot in ("ter", "sex"):
            n = len(items) + 1
            if slot == "ter" and week <= 8:
                title, fmt = EVERGREEN[week - 1]
                pillar, serie = "tradicoes", None
            else:
                name, title = ARCANOS[arc]
                pillar, fmt, serie = "arcanos", "longo" if arc == 13 else "ensaio", f"Arcano {NUMERALS[arc]} · {name}"
                arc += 1
            v = {"n": n, "semana": week, "dia": slot, "titulo": title, "pilar": pillar, "formato": fmt, "serie": serie,
                 "status": "planejado", "project_id": None, "nota": ""}
            v["shorts"] = shorts_plan.ideas_for(v)
            items.append(v)
    return items


VERSION = 5
YT_DEFAULT = {"envio_automatico": False, "hora": "18:00", "fuso": "America/Sao_Paulo", "privacidade": "agendado", "categoria": "27", "conteudo_sintetico": False}
PROTECTED = {"videos", "template", "template_nome", "versao", "_edited"}   # o resto do plano é editável pelo usuário
EMPTY_SECTIONS = {"posicionamento": {}, "pilares": [], "formatos": [], "frequencia": {}, "crescimento": [], "retencao": {"estrutura": [], "regras": []},
                  "monetizacao": {"ypp": [], "politica": [], "etapas": [], "meta_reais": ""}, "concorrentes": [], "cenarios": [], "checklist_publicar": [],
                  "nicho": {}, "concorrentes_estudo": {"tipos": [], "lacunas": []}, "ideias": [], "titulos": [], "algoritmo": {}, "producao": {}, "monetizacao_fases": {},
                  "revisao": {}, "roteiros": [], "fontes": [], "youtube_config": dict(YT_DEFAULT), "regras_do_canal": copy.deepcopy(channel_rules.DEFAULT_RULES)}


def _content_sections() -> dict:
    """Seções do playbook de 10 prompts executado para o Arcano Digital (importadas aqui para não criar ciclo)."""
    from . import channel_content_a as a, channel_content_b as b, channel_content_c as c
    return {"nicho": a.NICHO, "concorrentes_estudo": a.CONCORRENTES_ESTUDO, "ideias": b.ideias(), "titulos": b.TITULOS, "algoritmo": c.ALGORITMO,
            "producao": c.PRODUCAO, "monetizacao_fases": c.MONETIZACAO_FASES, "revisao": c.REVISAO, "roteiros": c.roteiros()}


def build() -> dict:
    plan = {
        "template": TEMPLATE_ID, "template_nome": TEMPLATE_NAME, "fontes": SOURCES, "posicionamento": POSITIONING, "pilares": PILLARS,
        "formatos": FORMATS, "frequencia": CADENCE, "crescimento": GROWTH, "retencao": RETENTION, "monetizacao": MONETIZATION,
        "concorrentes": COMPETITORS, "marcos": MILESTONES, "cenarios": SCENARIOS, "checklist_publicar": CHECKLIST_PUBLISH,
        "curva": {"horas": HOURS_GOAL, "inscritos": SUBS_GOAL, "piso": FLOOR_FACTOR},
        "semanas": [{"n": i + 1, "foco": f, "tarefas": t} for i, (f, t) in enumerate(WEEK_FOCUS)],
        "videos": _items(),
        "dados_de": "22/11/2026", "versao": VERSION, "shorts_plano": shorts_plan.strategy(), "_edited": [],
    }
    plan.update(_content_sections())
    plan["youtube_config"] = dict(YT_DEFAULT)
    plan["regras_do_canal"] = copy.deepcopy(channel_rules.DEFAULT_RULES)
    return copy.deepcopy(plan)


def skeleton(name: str = "Em branco") -> dict:
    """Plano vazio, com todas as seções para preencher (à mão ou pedindo ao Claude para executar o playbook de prompts)."""
    plan = copy.deepcopy(EMPTY_SECTIONS)
    plan.update({"template": "vazio", "template_nome": name, "videos": [], "marcos": [], "semanas": [], "curva": {}, "versao": VERSION, "_edited": []})
    return plan


def upgrade(plan: dict) -> bool:
    """Atualiza um plano salvo por versão antiga: troca as seções de texto que o usuário NÃO editou, acrescenta as que faltam (nunca apaga o que
    ele escreveu) e põe ideias de Short nos vídeos que não têm. Título, situação, ligação com projeto e notas dos vídeos ficam como estão."""
    if plan.get("template") != TEMPLATE_ID or plan.get("versao", 1) >= VERSION:
        return False
    fresh, edited = build(), set(plan.get("_edited") or [])
    for k, v in fresh.items():
        if k in PROTECTED or k in edited:
            continue
        plan[k] = v
    for v in plan.get("videos", []):
        if not v.get("shorts"):
            v["shorts"] = shorts_plan.ideas_for(v)
    plan["versao"] = VERSION
    plan.setdefault("_edited", [])
    return True


def clone_plan(plan: dict, *, keep_videos: bool = True) -> dict:
    """Cópia do plano para outro canal: mesmas seções, vídeos do calendário com título e tema mas sem ligação a projetos, situação zerada e notas limpas."""
    out = copy.deepcopy(plan)
    out["_edited"] = list(plan.get("_edited") or [])
    vids = out.get("videos", []) if keep_videos else []
    for v in vids:
        v["status"], v["project_id"], v["nota"] = "planejado", None, ""
        for sh in v.get("shorts", []):
            sh["status"], sh["nota"] = ("agendado" if sh.get("dia") is not None else "ideia"), ""
    out["videos"] = vids
    for r in out.get("ideias", []):
        r["status"] = "ideia"
    return out


def next_monday(today: dt.date | None = None) -> dt.date:
    d = today or dt.date.today()
    return d + dt.timedelta(days=(7 - d.weekday()) % 7)


def item_date(start: dt.date, item: dict) -> dt.date:
    return start + dt.timedelta(days=7 * (item["semana"] - 1) + (1 if item["dia"] == "ter" else 4))
