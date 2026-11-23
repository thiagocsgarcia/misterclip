"""Conteúdo do Arcano Digital, parte C: algoritmo (prompt 6), produção com IA (8), monetização por fase (9), revisão semanal (10) e roteiro (5).

As referências numéricas de CTR e retenção são faixas comuns citadas pelo próprio YouTube e por criadores, não garantias: dependem do assunto e do porte do canal.
"""
import re

ALGORITMO = {
    "ideia_central": "O YouTube mostra o seu vídeo a um grupo pequeno, mede se as pessoas clicam (CTR) e se ficam (retenção), e só então mostra a mais gente. Ele não julga o vídeo: julga a reação das pessoas.",
    "termos": [
        {"termo": "Impressões", "significa": "Quantas vezes a miniatura e o título foram mostrados.", "como_agir": "Impressão sobe quando o YouTube confia no vídeo. Se estão baixas, o problema costuma ser o tema ou o título que ninguém procura."},
        {"termo": "Taxa de cliques (CTR)", "significa": "De cada cem vezes que o vídeo apareceu, quantas pessoas clicaram.", "como_agir": "Referência comum: entre 2% e 10%, e acima de 4% já é um bom começo. Abaixo de 4% depois de 48 horas, troque a miniatura e depois o título."},
        {"termo": "Duração média da visualização", "significa": "Quanto tempo, em média, cada pessoa assistiu.", "como_agir": "Em vídeos de 12 minutos, 5 a 6 minutos é um bom resultado. Mais importante do que o número é a tendência de subir de um vídeo para o outro."},
        {"termo": "Percentual médio assistido", "significa": "Que fatia do vídeo as pessoas assistem em média.", "como_agir": "Entre 35% e 50% é comum em vídeos longos. Se estiver abaixo de 30%, reescreva a abertura e corte enrolação."},
        {"termo": "Retenção do público (o gráfico)", "significa": "A curva de quantas pessoas ainda estão assistindo a cada segundo.", "como_agir": "Queda forte nos primeiros 30 segundos: a abertura não cumpre o que o título prometeu. Quedas em degrau: um trecho ruim. Platôs ou subidas: o trecho que as pessoas reveem e vale repetir."},
        {"termo": "Espectadores recorrentes", "significa": "Quem já assistiu e voltou.", "como_agir": "É o sinal de que a série funciona. Playlists e a série dos arcanos existem para aumentar isso."},
        {"termo": "Tráfego de busca", "significa": "Visitas de quem pesquisou um assunto.", "como_agir": "É o que traz gente nova para um canal pequeno. Por isso os vídeos 'porta de entrada' usam o nome que as pessoas pesquisam."},
        {"termo": "Recursos de navegação (Início e Em alta)", "significa": "Vídeos recomendados na página inicial.", "como_agir": "Vem depois: o YouTube só recomenda para quem costuma ver conteúdo parecido. Construa a base com busca e série."},
        {"termo": "Vídeos sugeridos", "significa": "Aparecer ao lado ou depois de outro vídeo.", "como_agir": "Cresce quando o seu vídeo atrai o mesmo público de um canal maior. Estude os vídeos que mais trazem visitas para o seu."},
    ],
    "estrategia_menos_de_100_inscritos": {
        "frequencia": "Dois vídeos longos por semana (terça e sexta) e 4 Shorts. Constância vale mais que volume: o YouTube aprende com a regularidade.",
        "testar_primeiro": [
            "O título e a miniatura dos 4 primeiros vídeos (uma mudança por vez).",
            "Os primeiros 30 segundos: compare a retenção de duas aberturas diferentes.",
            "Um tema de busca (hermetismo, alquimia) contra um tema da série (arcanos): qual traz mais visitas.",
        ],
        "como_ler_os_resultados": [
            "Espere 48 horas para olhar o CTR e 7 dias para olhar a retenção. Antes disso o número engana.",
            "Em YouTube Studio > Análises, abra Alcance (impressões e CTR), Engajamento (retenção) e Público (recorrentes).",
            "Mude uma coisa por vez, anote a data e o motivo (aba Métricas > anotação).",
            "Compare com os seus próprios vídeos, não com canais grandes.",
        ],
        "de_espectador_a_inscrito": [
            "Peça a inscrição depois de entregar valor (por volta de 70% do vídeo), com um motivo concreto: 'a série continua na sexta'.",
            "Termine sempre apontando para o próximo episódio (fala e tela final).",
            "Fixe um comentário com a pergunta do vídeo e responda a todos nas duas primeiras horas.",
            "Use playlists para que quem gostou de um vídeo assista ao seguinte.",
            "Os Shorts convidam a ver o vídeo completo pelo recurso 'Vídeo relacionado'.",
        ],
    },
    "erros_comuns_de_canal_novo": [
        "Trocar de assunto toda semana: o YouTube não sabe para quem mostrar.",
        "Miniatura e título que prometem uma coisa e um vídeo que entrega outra (o público sai em 30 segundos).",
        "Abertura longa, com vinheta e apresentação, antes do primeiro ponto interessante.",
        "Julgar o canal pelo primeiro dia do vídeo, em vez de esperar 48 horas e 7 dias.",
        "Copiar o formato de canais grandes e esquecer de criar uma tese própria em cada vídeo.",
    ],
}

PRODUCAO = {
    "meta": "Publicar 2 vídeos longos e 4 Shorts por semana gastando menos de 10 horas do seu tempo (a andes trabalha sozinha, de noite).",
    "etapas": [
        {"etapa": "1. Escolher o tema", "quem": "Você + Claude", "tempo_min": 30, "ferramenta": "Aba Ideias do canal, Análises do YouTube", "saida": "Tema e título provisório"},
        {"etapa": "2. Escrever o roteiro", "quem": "Você + Claude", "tempo_min": 110, "ferramenta": "Modelo de roteiro (aba Roteiro e lista)", "saida": "Roteiro de 11 a 14 minutos com tese própria e fontes"},
        {"etapa": "3. Revisar a originalidade", "quem": "Você", "tempo_min": 20, "ferramenta": "Lista de verificação antes de publicar", "saida": "Roteiro aprovado"},
        {"etapa": "4. Voz, imagens e animação", "quem": "MisterClip (andes)", "tempo_min": 15, "ferramenta": "Novo vídeo > Fazer tudo agora (roda à noite)", "saida": "Cenas prontas para revisar"},
        {"etapa": "5. Revisar e montar o vídeo", "quem": "Você + MisterClip", "tempo_min": 15, "ferramenta": "Aba Cenas e Vídeo", "saida": "Vídeo final"},
        {"etapa": "6. Título, descrição e miniatura", "quem": "MisterClip + você", "tempo_min": 15, "ferramenta": "Publicar > Gerar sugestões e Miniaturas", "saida": "Metadados prontos"},
        {"etapa": "7. Agendar a publicação", "quem": "Você (ou o YouTube, depois da integração)", "tempo_min": 10, "ferramenta": "YouTube Studio (ou aba YouTube do canal)", "saida": "Vídeo agendado para terça ou sexta"},
        {"etapa": "8. Shorts", "quem": "MisterClip + você", "tempo_min": 20, "ferramenta": "Publicar > Gerar Shorts", "saida": "2 Shorts por vídeo longo"},
        {"etapa": "9. Reaproveitar em TikTok e Reels", "quem": "Você", "tempo_min": 10, "ferramenta": "Os mesmos Shorts verticais, nos aplicativos de cada rede", "saida": "Mesmo corte em 3 redes"},
        {"etapa": "10. Revisão da semana", "quem": "Você + Claude", "tempo_min": 30, "ferramenta": "Aba Métricas e a revisão semanal", "saida": "O que repetir e o que mudar"},
    ],
    "tempo_por_semana_horas": 8.8,
    "ferramentas_gratis_ou_baratas": [
        "Claude: pesquisa, ideias, roteiro e revisão.",
        "MisterClip: voz, imagens, animação, montagem, miniaturas, título, descrição e Shorts (roda na sua andes, sem mensalidade).",
        "YouTube Studio: publicação e Análises.",
        "Canva (plano grátis): banner e foto do canal, uma vez só.",
        "Aplicativos nativos do TikTok e do Instagram: para postar o mesmo Short vertical.",
    ],
    "modelos": {
        "titulo": ["Tema + virada: 'Alquimia: o que os alquimistas realmente buscavam (e não era ouro)'", "Pergunta com o nome buscado: 'Peter Thiel é ocultista?'",
                   "Correção de mito: 'Hermetismo de verdade: o que o Caibalion não diz'", "Ponte: 'O Golem de Praga: a primeira inteligência artificial?'"],
        "descricao": "Primeira e segunda linhas com a ideia central e o nome buscado; depois os capítulos; depois as fontes (autor, obra, ano); links dos livros citados; hashtags no fim.",
        "comentario_fixado": "Pergunta que provoca resposta + 'Próximo vídeo: [título] na [terça/sexta]'.",
    },
    "regra_de_originalidade": [
        "Todo vídeo defende uma tese sua em uma frase (o que você acha e por quê).",
        "Todo vídeo cita pelo menos 3 fontes dentro da narração (autor, obra, época).",
        "Todo vídeo tem algo que nenhum outro do canal tem: um formato, uma estrutura ou uma ideia visual diferentes.",
        "A cada 3 vídeos, mude a estrutura (por exemplo: história, debate, mapa de ideias) para o canal não parecer produzido em massa.",
        "Nunca publique um vídeo que você não conseguiria defender numa conversa.",
    ],
}

MONETIZACAO_FASES = {
    "por_faixa": [
        {"faixa": "0 a 500 inscritos", "foco": "Conteúdo e inscritos. Ainda não é hora de vender nada.",
         "acoes": ["Ativar a verificação em duas etapas e verificar o canal por telefone.", "Criar a conta do AdSense e começar o endereço de pagamento (o código de confirmação chega por carta e demora).",
                   "Colocar links de afiliado dos livros que você realmente cita (Amazon Associados) na descrição, desde o primeiro vídeo.", "Abrir um grupo de comunidade (Telegram ou Discord) e convidar de forma natural nos vídeos.",
                   "Registrar o que funciona na aba Métricas."]},
        {"faixa": "500 a 1.000 inscritos", "foco": "Preparar a monetização e os primeiros produtos.",
         "acoes": ["Ativar os recursos de apoio dos fãs quando o YouTube liberar para o seu canal.", "Criar um apoio por Pix ou plataforma de apoio (Apoia.se), citado com carinho, sem insistir.",
                   "Começar uma lista de e-mails com um conteúdo de graça (ex.: guia 'Os 22 arcanos e a IA').", "Fazer o rascunho de um produto digital simples (e-book).",
                   "Montar um 'kit de apresentação' do canal (números, público, temas) para patrocínios futuros."]},
        {"faixa": "1.000 inscritos ou mais", "foco": "Entrar no Programa de Parcerias e diversificar a renda.",
         "acoes": ["Enviar o pedido ao Programa de Parcerias assim que atingir os requisitos vigentes (confirme em YouTube Studio > Monetização).", "Ativar os anúncios e a receita do YouTube Premium.",
                   "Abrir os Membros do canal com benefícios simples (acesso antecipado, comunidade).", "Lançar o e-book ou um curso curto de 'Os 22 Arcanos da Era das Máquinas'.",
                   "Procurar patrocínio de livrarias, editoras e cursos de filosofia quando a média passar de uns 10 mil views por vídeo."]},
    ],
    "checklist_inscricao_ypp": [
        "Verificação em duas etapas ativada na conta Google do canal.",
        "Nenhum aviso de diretrizes da comunidade nem de direitos autorais ativo.",
        "Políticas lidas e em dia: conteúdo inautêntico (repetitivo ou em massa), spam, conteúdo sensível e declaração de conteúdo sintético.",
        "Canal verificado por telefone (libera miniaturas personalizadas e vídeos longos).",
        "Conta do AdSense criada e vinculada ao canal, com endereço e dados fiscais preenchidos (criadores fora dos EUA informam os dados fiscais no AdSense).",
        "Requisitos vigentes de horas e inscritos confirmados em YouTube Studio > Monetização (as regras mudam em 1º/02/2027).",
        "Vídeos originais, com voz e visual próprios, e sem trechos de terceiros sem licença.",
        "Depois de enviar o pedido: aguardar a análise (pode levar semanas) sem apagar vídeos nem mudar o canal de assunto.",
    ],
}

REVISAO = {
    "semanal": {
        "quando": "Todo domingo, 30 minutos.",
        "passos": [
            "Abrir YouTube Studio > Análises e preencher a aba Métricas (inscritos, horas, views, CTR, retenção).",
            "Ordenar os vídeos da semana por CTR e por percentual médio assistido.",
            "Olhar o gráfico de retenção do vídeo mais novo e anotar onde a curva cai.",
            "Escolher UMA mudança para a próxima semana (título, abertura, tema) e anotar.",
            "Conferir o calendário: os próximos 4 vídeos têm roteiro?",
        ],
    },
    "mensal": {
        "quando": "No último domingo do mês, 1 hora.",
        "passos": [
            "Comparar o mês com o plano (marcos do dia 30, 60 e 90 na aba Resumo).",
            "Ver quais temas e categorias trouxeram mais visitas e inscritos e dobrar neles.",
            "Rever as 3 piores publicações e aplicar o plano de melhoria abaixo.",
            "Atualizar a aba Plano (pilares, formatos, calendário) com o que aprendeu.",
            "Decidir o foco do mês seguinte em uma frase.",
        ],
    },
    "metricas": [
        {"metrica": "Impressões", "significa": "Quantas vezes o seu vídeo foi mostrado.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Centenas por vídeo é normal; milhares já é bom.", "1000_a_10000": "Milhares a dezenas de milhares.", "acima_de_10000": "Dezenas de milhares ou mais."}, "corrigir_primeiro": "Tema e título que as pessoas procuram."},
        {"metrica": "Taxa de cliques (CTR)", "significa": "Quem clicou entre quem viu.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Acima de 4% é bom; abaixo de 2% é problema.", "1000_a_10000": "Entre 4% e 8% é saudável.", "acima_de_10000": "Entre 3% e 7%: canais grandes têm CTR menor porque aparecem para mais gente."}, "corrigir_primeiro": "Miniatura (até 4 palavras) e depois título."},
        {"metrica": "Duração média da visualização", "significa": "Tempo médio assistido por pessoa.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Em vídeo de 12 minutos, 4 a 6 minutos é bom.", "1000_a_10000": "5 a 7 minutos.", "acima_de_10000": "6 minutos ou mais."}, "corrigir_primeiro": "Abertura e cortes de enrolação."},
        {"metrica": "Percentual médio assistido", "significa": "A fatia do vídeo que as pessoas assistem.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Entre 35% e 50% é bom; abaixo de 30% pede revisão.", "1000_a_10000": "40% a 50%.", "acima_de_10000": "40% ou mais."}, "corrigir_primeiro": "O trecho onde a curva de retenção despenca."},
        {"metrica": "Gráfico de retenção", "significa": "Quantas pessoas restam a cada instante.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Perder 30% a 40% nos primeiros 30 segundos é comum.", "1000_a_10000": "Perder menos de 30% no começo.", "acima_de_10000": "Manter mais de 70% no começo."}, "corrigir_primeiro": "Os primeiros 30 segundos."},
        {"metrica": "Inscritos ganhos por fonte", "significa": "De onde vieram os inscritos (vídeo, Shorts, página do canal).", "bom_ou_ruim": {"menos_de_1000_inscritos": "Qualquer fonte constante é boa.", "1000_a_10000": "Mais de 1 inscrito a cada 100 visualizações do vídeo é bom.", "acima_de_10000": "Mantenha a proporção enquanto cresce."}, "corrigir_primeiro": "O pedido de inscrição, em 70% do vídeo."},
        {"metrica": "Engajamento (curtidas, comentários, compartilhamentos)", "significa": "Quem reagiu ao vídeo.", "bom_ou_ruim": {"menos_de_1000_inscritos": "Comentários de verdade valem mais que curtidas.", "1000_a_10000": "Pelo menos 1 comentário a cada 200 visualizações.", "acima_de_10000": "Mantenha as respostas rápidas."}, "corrigir_primeiro": "A pergunta do comentário fixado."},
    ],
    "padroes_nos_melhores_videos": [
        "Qual era a categoria (tradições, arcanos, ponte, filosofia, futuro)?",
        "O título era pergunta, correção de mito ou nome próprio?",
        "Qual foi a duração e quantas quebras de ritmo havia?",
        "Como era a abertura (a primeira frase)?",
        "De onde veio a maioria das visitas: busca, sugeridos ou Shorts?",
    ],
    "melhorar_os_3_piores": [
        "Escolha os 3 vídeos com pior resultado depois de 28 dias.",
        "Diagnóstico: CTR baixo com muitas impressões = mexer em título e miniatura. CTR bom e retenção baixa = reescrever a abertura. Poucas impressões = tema ou título pouco procurado.",
        "Gere 3 títulos novos e 2 miniaturas novas (Publicar > Gerar sugestões e Miniaturas) e troque UMA coisa por vez.",
        "Espere 7 dias, compare e anote o resultado. Mantenha o que melhorou.",
        "Se nada melhorar, o tema não tem procura: aprenda e siga em frente.",
    ],
}

# prompt 5: roteiro completo com marcações. Marcas: [B-ROLL: ...] [TELA: ...] [SOM: ...] [QUEBRA: ...] [TEASER] [SAÍDA: risco | solução]
ROTEIRO_MARCADO = """A maior parte do que você ouviu sobre o hermetismo vem de um livro de mil novecentos e oito, escrito em Chicago por autores que nunca assinaram o nome, e os textos antigos de Hermes Trismegisto dizem quase o oposto do que esse livro promete. Nos próximos minutos, você vai ver o que Hermes realmente ensinou, quem desmontou a lenda do Egito e por que isso torna o hermetismo mais interessante, e não menos.
[B-ROLL: capa antiga de livro de 1908 ao lado de um papiro egípcio]
[TELA: "1908 ≠ Egito antigo"]
[SOM: acorde grave sustentado, sobe no fim da frase]

Para provar que isto é sério, repare em um detalhe: a frase que mais circula nas redes, "o que está embaixo é como o que está em cima", não vem do livro de Chicago. Ela vem de um texto curto chamado Tábua de Esmeralda, e a versão mais antiga que conhecemos dela está em árabe, escrita há mais de mil anos.
[B-ROLL: close na frase sobre gravura de alquimista; tradução surgindo letra por letra]
[SAÍDA: risco: dois minutos de definição podem entediar | solução: o gancho já prometeu a virada e a próxima parte vai direto a um personagem]

Comecemos por quem foi Hermes Trismegisto. O nome quer dizer "Hermes, três vezes grande", e ele nunca foi um homem de carne e osso. Nasceu da fusão de dois deuses: o Hermes dos gregos, mensageiro dos deuses, e o Thot dos egípcios, senhor da escrita e da sabedoria. No Egito governado primeiro por gregos e depois por romanos, essa mistura virou uma figura única, tratada como o autor de livros sagrados.
[B-ROLL: estátua de Hermes ao lado de Thot com cabeça de íbis, fusão lenta entre as duas imagens]
[QUEBRA: corte para o mapa do Mediterrâneo antigo com Alexandria destacada]

Esses livros existem. Hoje os chamamos de Corpus Hermeticum, uma coleção de textos gregos que, pela melhor estimativa dos especialistas, foi escrita entre os primeiros séculos depois de Cristo. O primeiro e mais famoso se chama Poimandres e conta uma visão: um ser de luz mostra ao narrador como o universo nasceu da Mente divina e como o ser humano carrega dentro de si algo dessa mesma Mente.
[B-ROLL: gravura de uma figura luminosa diante de um homem sentado, animação de luz suave]
[TELA: "Corpus Hermeticum: séculos I a III"]

E aqui está o primeiro choque para quem chegou pelo Caibalion. O centro desses textos não é manipular a realidade com o pensamento. É a ideia de que conhecer a si mesmo é conhecer Deus, e de que a alma pode se libertar da matéria por meio do conhecimento, o que os gregos chamavam de gnose. O hermetismo antigo se parece muito mais com uma filosofia de salvação pela mente do que com um manual de poderes.
[QUEBRA: pausa de um segundo de silêncio e música baixa antes da frase final]
[SAÍDA: risco: quem veio atrás de "como atrair" pode sair aqui | solução: a frase promete que o interessante está logo adiante, e o teaser vem em seguida]

[TEASER]
Daqui a pouco você vai ver como um erro de data derrubou a fama do hermetismo e como um livro do começo do século vinte tomou o lugar dos textos antigos. Mas antes preciso contar como esses textos voltaram à Europa, porque essa história parece um romance.
[SOM: batida seca de tambor ao dizer "romance"]

Em mil quatrocentos e sessenta e três, em Florença, Cosimo de Médici, o homem mais rico da cidade, recebeu um manuscrito grego do Corpus Hermeticum. Já era velho e queria ler antes de morrer. Ele pediu ao filósofo Marsilio Ficino que parasse a tradução de Platão, que era a grande obra da vida de Ficino, e traduzisse Hermes primeiro. Ficino obedeceu, e isso mostra o quanto os intelectuais da época acreditavam que aquilo era antiquíssimo.
[B-ROLL: pintura renascentista de Florença, palácio dos Médici, mãos virando páginas]
[QUEBRA: corte para retrato de Ficino com legenda "1463"]

E acreditavam por um motivo. Pensavam que Hermes tinha vivido antes de Moisés e antes de Platão, e que os grandes filósofos gregos tinham aprendido com ele. O Corpus seria, então, a raiz secreta de toda a sabedoria humana. Foi essa crença que fez do hermetismo uma das ideias mais influentes da Renascença, e ela inspirou nomes como Giordano Bruno.
[TELA: linha do tempo "Hermes → Moisés → Platão" com um ponto de interrogação sobre a seta]

Então chegamos ao momento em que tudo desmorona. Em mil seiscentos e catorze, um erudito nascido em Genebra chamado Isaac Casaubon examinou o grego dos textos. Ele percebeu que aquele vocabulário e aquelas ideias não eram do Egito antigo. Pertenciam ao mundo greco-romano dos primeiros séculos depois de Cristo. Hermes não era mais velho que Moisés: era mais novo que Platão por séculos.
[SOM: nota de piano que vira silêncio ao dizer "desmorona"]
[QUEBRA: tela escurece por meio segundo e reacende com a data "1614"]

Isso acabou com o hermetismo? Não. Acabou com a lenda da idade, mas não com o conteúdo. Os textos continuam existindo, e o seu valor passou a ser o de um espelho da espiritualidade do Egito romano, uma época em que gregos, egípcios, judeus e cristãos misturavam as suas filosofias. E a Tábua de Esmeralda, aquela frase do começo, seguiu sua própria jornada dentro da alquimia, onde o que está embaixo ser como o que está em cima virou princípio de laboratório e de filosofia.
[B-ROLL: gravura de laboratório de alquimista com a frase da Tábua aparecendo em letras douradas]

E o Caibalion? Ele foi publicado em mil novecentos e oito, em Chicago, assinado apenas como "Três Iniciados". Muitos estudiosos atribuem o livro a William Walker Atkinson, um escritor americano ligado ao movimento do Novo Pensamento, que ensinava que a mente molda a realidade. O livro apresenta sete princípios: mentalismo, correspondência, vibração, polaridade, ritmo, causa e efeito e gênero. Esses sete princípios não aparecem listados assim nos textos antigos. Eles são uma leitura do começo do século vinte, na linguagem do seu tempo.
[TELA: lista dos sete princípios, um por vez, com a etiqueta "1908"]
[SAÍDA: risco: a lista pode soar como aula | solução: cada princípio entra por um segundo, no ritmo da fala, e a etiqueta lembra o contraste com o Corpus]

Isso significa que o Caibalion é mentira? Não, e essa é a parte que quase ninguém diz. Ele é um livro de filosofia prática bem escrito, que usa um nome antigo para apresentar uma ideia moderna. O problema é confundir as duas coisas, achar que está estudando o Egito quando está lendo Chicago de mil novecentos e oito. Quem entende a diferença lê os dois com muito mais proveito.
[QUEBRA: corte para as duas capas lado a lado, uma antiga e uma de 1908]

Então, resumindo o que você ganhou de graça: Hermes Trismegisto é uma figura que mistura dois deuses; o Corpus Hermeticum existe e fala de conhecer a Mente divina; a lenda do Egito antigo caiu em mil seiscentos e catorze; e o Caibalion é uma obra moderna que usou o nome de Hermes. Isso muda a forma de estudar qualquer tradição esotérica: sempre pergunte quem escreveu, quando e para quê.
[TELA: três perguntas — Quem? Quando? Para quê?]

Esse hábito de perguntar pela origem de uma ideia vai ser útil já na próxima vez, porque na sexta-feira começamos uma série com os vinte e dois arcanos maiores do tarô, lidos à luz das máquinas e da inteligência artificial. O primeiro é O Louco, a carta do salto no escuro, e a pergunta dele se parece com a nossa: o que acontece quando alguém dá o primeiro passo sem saber para onde vai? Se este vídeo ajudou você a separar a história da lenda, inscreva-se para não perder o próximo.
[B-ROLL: carta O Louco em gravura, o personagem dando o passo à beira do penhasco]
[TELA: "Sexta: O Louco e o salto no escuro"]
[SOM: acorde final que se resolve devagar]
"""

_MARK = re.compile(r"\[(?:B-ROLL|TELA|SOM|QUEBRA|SAÍDA|TEASER)[^\]]*\]")


def narracao_limpa(marcado: str) -> str:
    """Só o texto falado: tira todas as marcações (B-ROLL, TELA, SOM, QUEBRA, SAÍDA, TEASER) e as linhas que ficam vazias."""
    out = _MARK.sub("", marcado)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", out)]
    return "\n\n".join(p for p in paras if p)


ROTEIROS = [{"video_n": 1, "titulo": "Hermetismo de verdade: o que Hermes Trismegisto ensinou e o que o Caibalion não diz", "duracao_min": 10,
             "quebra_de_padrao_a_cada_s": 60, "marcado": ROTEIRO_MARCADO,
             "pontos_de_saida": [
                 {"ponto": "Abertura até a Tábua de Esmeralda (0:00 a 1:00)", "risco": "Quem veio pelo Caibalion pode achar que o vídeo é ataque.", "solucao": "O gancho promete que o hermetismo fica mais interessante, e a frase famosa aparece logo."},
                 {"ponto": "Quem foi Hermes (1:00 a 2:00)", "risco": "Definição histórica pode parecer aula.", "solucao": "A fusão de dois deuses entra com imagem animada e um corte de mapa."},
                 {"ponto": "O centro dos textos (3:30)", "risco": "Quem esperava técnicas de poder pode sair.", "solucao": "O teaser logo depois promete a virada: o erro de data e o livro de 1908."},
                 {"ponto": "Lista dos sete princípios (8:00)", "risco": "Lista pode soar como aula.", "solucao": "Um princípio por segundo, no ritmo da fala, com a etiqueta '1908'."}]}]


def roteiros() -> list[dict]:
    out = []
    for r in ROTEIROS:
        r = dict(r)
        n = narracao_limpa(r["marcado"])
        r["narracao"], r["palavras"] = n, len(n.split())
        out.append(r)
    return out
