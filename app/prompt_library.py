"""Biblioteca de prompts do MisterClip: o playbook de 10 prompts para planejar um canal de YouTube.

Cada prompt tem o `original` (do Thiago, preservado) e o `body` ajustado: contexto do canal, regras de qualidade (dados reais, fontes, honestidade),
e o formato de entrega que o módulo Canais entende. Para usar num canal novo, peça ao Claude: "execute o prompt <título> para o canal <nome>".
"""

CONTEXTO = """## Contexto do canal
- Nome do canal: {{nome_do_canal}}
- Nicho: {{nicho}}
- Público: {{publico}}
- Recursos (tempo por semana, orçamento, equipamento): {{recursos}}
- Meta: {{meta}}
- Primeiro dia do plano: {{data_de_inicio}}
- Ferramentas do sistema: MisterClip (voz, imagens, animação, montagem, miniaturas, Shorts, calendário e métricas) rodando numa GPU local."""

REGRAS = """## Regras de qualidade (valem para qualquer resposta)
1. Pesquise na internet antes de afirmar. Use números reais (inscritos, visualizações, regras do YouTube) com a data da coleta e a fonte. Marque como ESTIMATIVA tudo o que não for dado medido.
2. Confirme as regras vigentes do Programa de Parcerias do YouTube, inclusive mudanças futuras já anunciadas, com a data em que valem.
3. Seja honesto sobre probabilidades e prazos. Não prometa resultado; mostre cenários conservador, base e otimista.
4. Escreva em português do Brasil, em linguagem simples. Nada de sensacionalismo, nada de promessa de cura, dinheiro ou previsão.
5. Respeite a política de conteúdo original do YouTube: todo vídeo precisa de uma tese própria, fontes citadas e variação de estrutura.
6. Não invente fatos. Se não souber ou não encontrar, diga."""

SAIDA = """## Entrega
Entregue (a) o texto explicado para eu ler e (b) o conteúdo em JSON nas chaves abaixo, pronto para gravar no módulo Canais do MisterClip (aba Plano, editável) com `PUT /api/channels/{id}/plan/{secao}` ou `POST /api/channels/{id}/plan/import`.
{{chaves}}"""


def _body(papel: str, tarefa: str, chaves: str) -> str:
    return "\n\n".join([papel, CONTEXTO, "## Tarefa\n" + tarefa, REGRAS, SAIDA.replace("{{chaves}}", chaves)])


PROMPTS = [
    {
        "id": "01-plano-90-dias", "ordem": 1, "titulo": "Plano de 90 dias até o Programa de Parcerias",
        "quando_usar": "No começo de um canal novo. É o prompt principal: gera o plano completo que o módulo Canais mostra e edita.",
        "variaveis": ["nome_do_canal", "nicho", "publico", "recursos", "meta", "data_de_inicio"],
        "secoes_geradas": ["posicionamento", "pilares", "formatos", "frequencia", "crescimento", "retencao", "monetizacao", "concorrentes", "marcos", "curva", "cenarios", "semanas", "videos"],
        "por_que_funciona": "Dá ao Claude os seus limites reais (tempo, dinheiro, equipamento), e o plano sai executável e não genérico.",
        "original": "Aja como um estrategista de YouTube e consultor de monetização de nível mundial. Monte um sistema operacional completo de 90 dias pra levar meu canal do zero até os requisitos do Programa de Parcerias do YouTube. Meu nicho é [nicho]. Meu público é [público]. Meus recursos são [tempo por semana, orçamento, equipamento]. Minha meta é [meta]. Analise meus concorrentes e crie o posicionamento do canal, os pilares de conteúdo, a frequência de postagem, os formatos de vídeo, os sistemas de crescimento, a estrutura de retenção, o plano de monetização e um calendário de execução semana a semana. Me mostre o marco do dia 30, do dia 60 e do dia 90.",
        "body": _body(
            "Aja como um estrategista de YouTube e consultor de monetização de nível mundial.",
            "Monte um sistema operacional completo de 90 dias para levar o canal do zero até os requisitos do Programa de Parcerias do YouTube. Antes de planejar, pesquise os requisitos vigentes (e as mudanças já anunciadas, com data) e analise concorrentes REAIS do nicho, anotando inscritos, visualizações e o que cada um faz melhor ou pior. Crie: o posicionamento do canal, os pilares de conteúdo (com peso em %), a frequência de postagem, os formatos de vídeo, os sistemas de crescimento, a estrutura de retenção, o plano de monetização e um calendário semana a semana (13 semanas, com tarefas). Mostre os marcos do dia 30, do dia 60 e do dia 90 com meta e mínimo aceitável, a curva semanal de horas e inscritos, e três cenários (conservador, base e otimista). Liste os vídeos do calendário (um por data, com título, pilar e formato).",
            "`posicionamento`, `pilares`, `formatos`, `frequencia`, `crescimento`, `retencao`, `monetizacao`, `concorrentes`, `marcos`, `curva`, `cenarios`, `semanas`, `checklist_publicar` e a lista `videos` (n, semana, dia, titulo, pilar, formato)."),
    },
    {
        "id": "02-escolha-do-nicho", "ordem": 2, "titulo": "Escolha o nicho que pode ganhar",
        "quando_usar": "Antes de criar o canal, ou quando quiser testar se o nicho atual é o melhor.",
        "variaveis": ["interesses", "habilidades", "nome_do_canal"],
        "secoes_geradas": ["nicho", "ideias"],
        "por_que_funciona": "Comparar 5 nichos lado a lado, com os mesmos critérios, evita escolher no achismo.",
        "original": "Aja como um pesquisador de mercado de elite e estrategista de YouTube. Me ajude a escolher o melhor nicho e posicionamento pra um canal novo. Meus interesses são [interesses]. Minhas habilidades são [habilidades]. Compare 5 nichos possíveis por demanda do público, nível de concorrência, potencial de busca, aceitação de anúncio, vida útil do conteúdo e formas de se destacar. Escolha o melhor e explique por quê. Depois crie a identidade do meu canal, o perfil do meu espectador ideal, 5 categorias de conteúdo e 100 ideias de vídeo ranqueadas por potencial de crescimento.",
        "body": _body(
            "Aja como um pesquisador de mercado de elite e estrategista de YouTube.",
            "Ajude a escolher o melhor nicho e o melhor posicionamento para o canal. Interesses: {{interesses}}. Habilidades: {{habilidades}}. Compare 5 nichos possíveis (dê uma nota de 1 a 5 a cada um) por demanda do público, nível de concorrência, potencial de busca, aceitação de anúncio, vida útil do conteúdo e formas de se destacar, usando dados reais observados na busca do YouTube. Escolha o melhor e explique por quê. Depois crie a identidade do canal (nome, slogan, descrição, estética, voz, valores), o perfil do espectador ideal (perfil, dores, desejos, onde está, como chega), 5 categorias de conteúdo e 100 ideias de vídeo, ranqueadas por potencial de crescimento (nota de 0 a 100 e o motivo).",
            "`nicho` (aviso, comparacao[], escolhido, motivo, identidade, espectador, categorias[]) e `ideias` (lista com n, titulo, categoria, potencial, motivo)."),
    },
    {
        "id": "03-espione-concorrentes", "ordem": 3, "titulo": "Espione seus concorrentes",
        "quando_usar": "Depois de escolher o nicho, e a cada trimestre.",
        "variaveis": ["nicho"],
        "secoes_geradas": ["concorrentes_estudo"],
        "por_que_funciona": "As reclamações dos comentários e as lacunas mostram o que as pessoas querem antes de você gastar tempo gravando.",
        "original": "Aja como um analista de concorrentes do YouTube. Meu nicho é [nicho]. Liste os 10 tipos de canal que eu devo estudar (pequenos, médios e grandes). Pra cada um, me diga o que observar: os vídeos que mais performam, os padrões de título, o estilo de thumbnail, a duração, o ritmo de postagem e as reclamações nos comentários. Depois encontre 10 lacunas de conteúdo, os temas que o público quer e ninguém cobre bem. Transforme cada lacuna numa ideia de vídeo com título e o motivo pelo qual ela pode superar os vídeos que já existem.",
        "body": _body(
            "Aja como um analista de concorrentes do YouTube.",
            "Liste os 10 tipos de canal que devo estudar (pequenos, médios e grandes), com exemplos REAIS que você encontrou (nome, inscritos e visualizações observados, com a data). Para cada tipo, diga o que observar: os vídeos que mais performam, os padrões de título, o estilo de miniatura, a duração, o ritmo de postagem e as reclamações nos comentários. Inclua um tipo 'modelo a evitar'. Depois encontre 10 lacunas de conteúdo: temas que o público quer e ninguém cobre bem. Transforme cada lacuna numa ideia de vídeo com título e o motivo pelo qual pode superar o que já existe.",
            "`concorrentes_estudo` com `como_usar`, `tipos[]` (tipo, exemplos, observar[]) e `lacunas[]` (lacuna, titulo, motivo)."),
    },
    {
        "id": "04-ganchos-e-titulos", "ordem": 4, "titulo": "Ganchos e títulos que dão clique",
        "quando_usar": "Ao planejar os próximos 20 vídeos ou ao refazer títulos fracos.",
        "variaveis": ["nicho"],
        "secoes_geradas": ["titulos"],
        "por_que_funciona": "Título, miniatura e gancho são planejados juntos, como fazem os criadores de verdade.",
        "original": "Aja como um criador do 1% do topo do YouTube que estuda vídeos virais. Pro meu nicho [nicho], escreva 20 ideias de vídeo. Pra cada uma, me dê 3 opções de título, 1 conceito de thumbnail (no máximo 4 palavras na tela), um gancho pros primeiros 15 segundos e uma linha com o motivo do clique. Use curiosidade, uma promessa clara ou uma surpresa. Não use clickbait falso. O vídeo tem que entregar o que o título promete.",
        "body": _body(
            "Aja como um criador do 1% do topo do YouTube que estuda vídeos virais.",
            "Para o nicho do canal, escreva 20 ideias de vídeo. Para cada uma, dê 3 opções de título (frase normal, sem CAIXA ALTA, até 70 caracteres, com o nome que as pessoas buscam no começo), 1 conceito de miniatura (no máximo 4 palavras na tela), um gancho para os primeiros 15 segundos (uma frase falada que abre um laço) e uma linha com o motivo do clique. Use curiosidade, uma promessa clara ou uma surpresa. Não use clickbait falso: o vídeo tem que entregar o que o título promete. Confira cada fato histórico ou técnico antes de colocá-lo no gancho.",
            "`titulos`: lista de objetos com `ideia`, `titulos` (3), `thumb`, `gancho` e `motivo_clique`."),
    },
    {
        "id": "05-roteiro-de-retencao", "ordem": 5, "titulo": "Roteirize vídeos que as pessoas assistem até o fim",
        "quando_usar": "Para cada vídeo longo, antes de mandar ao MisterClip.",
        "variaveis": ["ideia_do_video", "minutos", "quebra_a_cada_segundos"],
        "secoes_geradas": ["roteiros"],
        "por_que_funciona": "A retenção nasce no roteiro. Marcar onde a pessoa pode sair permite consertar antes de gravar.",
        "original": "Aja como um roteirista de YouTube focado em retenção. Escreva um roteiro completo pra esta ideia de vídeo: [ideia do vídeo]. Duração: [minutos]. Use esta estrutura: gancho, prova rápida, história ou contexto, pontos principais, uma quebra de padrão a cada [X] segundos, um teaser no meio do vídeo e um final forte que leva pro meu próximo vídeo. Escreva em linguagem simples e falada. Marque onde entram B-roll, texto na tela e efeito sonoro. Depois aponte onde o espectador pode sair e como você resolveu isso.",
        "body": _body(
            "Aja como um roteirista de YouTube focado em retenção.",
            "Escreva o roteiro completo desta ideia de vídeo: {{ideia_do_video}}. Duração: {{minutos}} minutos (cerca de 125 palavras por minuto na voz do canal). Estrutura: gancho (primeiros 15 segundos, com laço aberto), prova rápida, história ou contexto, pontos principais, uma quebra de padrão a cada {{quebra_a_cada_segundos}} segundos, um teaser no meio e um final forte que leva ao próximo vídeo do calendário. Linguagem simples e falada, números por extenso (para a voz sintética ler certo), frases completas. Cite as fontes dentro da narração e defenda uma tese própria. Marque no texto, em linhas separadas, onde entram [B-ROLL: ...], [TELA: ...], [SOM: ...], [QUEBRA: ...], [TEASER] e [SAÍDA: risco | solução]. Depois liste os pontos onde o espectador pode sair e como cada um foi resolvido.",
            "`roteiros`: lista com `video_n`, `titulo`, `duracao_min`, `quebra_de_padrao_a_cada_s`, `marcado` (texto com as marcações) e `pontos_de_saida[]` (ponto, risco, solucao). O sistema gera a narração limpa (sem marcações) para colar em Novo vídeo."),
    },
    {
        "id": "06-algoritmo", "ordem": 6, "titulo": "Entenda como o algoritmo pensa",
        "quando_usar": "No início, e sempre que as visitas travarem.",
        "variaveis": ["porte_do_canal"],
        "secoes_geradas": ["algoritmo"],
        "por_que_funciona": "Quando você sabe o que o YouTube mede, para de chutar e começa a testar.",
        "original": "Aja como um especialista no algoritmo do YouTube. Explique em linguagem simples como funcionam impressões, taxa de cliques, duração média da visualização, retenção do público, espectadores recorrentes, tráfego de busca, recursos de navegação e vídeos sugeridos. Depois monte uma estratégia de crescimento pra um canal com menos de 100 inscritos: com que frequência postar, o que testar primeiro, como ler os resultados e como transformar espectador em inscrito. Termine com uma lista dos 5 erros mais comuns de canal novo.",
        "body": _body(
            "Aja como um especialista no algoritmo do YouTube.",
            "Explique em linguagem simples como funcionam impressões, taxa de cliques, duração média da visualização, percentual assistido, retenção do público, espectadores recorrentes, tráfego de busca, recursos de navegação e vídeos sugeridos, com faixas de referência comuns (marcadas como referência, não regra). Depois monte uma estratégia de crescimento para um canal com porte {{porte_do_canal}}: com que frequência postar, o que testar primeiro, como ler os resultados (quando olhar cada número) e como transformar espectador em inscrito. Termine com os 5 erros mais comuns de canal novo.",
            "`algoritmo` com `ideia_central`, `termos[]` (termo, significa, como_agir), `estrategia_menos_de_100_inscritos` (frequencia, testar_primeiro[], como_ler_os_resultados[], de_espectador_a_inscrito[]) e `erros_comuns_de_canal_novo[]`."),
    },
    {
        "id": "07-shorts", "ordem": 7, "titulo": "Use os Shorts para alimentar o canal",
        "quando_usar": "Logo depois do plano de 90 dias, para ligar os Shorts aos vídeos longos.",
        "variaveis": ["nicho", "temas_dos_videos_longos"],
        "secoes_geradas": ["shorts_plano", "videos[].shorts"],
        "por_que_funciona": "Os Shorts trazem gente nova rápido, e ligar cada Short a um vídeo longo ajuda a somar horas de exibição.",
        "original": "Aja como um estrategista de YouTube Shorts. Meu nicho é [nicho] e meus vídeos longos falam de [temas]. Crie um plano de Shorts de 90 dias que leve gente nova pros meus vídeos longos. Me dê 30 ideias de Shorts, um gancho pra cada, a duração ideal e um loop ou final que faça a pessoa assistir de novo. Me mostre como as visualizações de Shorts e as horas de exibição dos vídeos longos contam separado pro Programa de Parcerias e qual caminho combina mais com o meu canal.",
        "body": _body(
            "Aja como um estrategista de YouTube Shorts.",
            "Os vídeos longos do canal falam de {{temas_dos_videos_longos}}. Crie um plano de Shorts de 90 dias que leve gente nova aos vídeos longos: cadência (amarrada à data de cada vídeo longo), regras de um bom Short, o que medir e, para CADA vídeo longo do calendário, pelo menos 10 ideias de Short com gancho (primeira frase), duração ideal, final em laço (uma frase aberta que continua no gancho), dica visual e como levar ao vídeo longo. Mostre, com fontes oficiais e a data de cada regra, como as visualizações de Shorts e as horas de exibição dos vídeos longos contam separadas para o Programa de Parcerias (hoje e depois das mudanças anunciadas) e qual caminho combina mais com este canal, com a conta de esforço.",
            "`shorts_plano` (estrategia, caminhos com recomendação) e, em cada item de `videos`, a lista `shorts` (id, tipo, nome, gancho, duracao, faixa, final, visual, cta, dia, status)."),
    },
    {
        "id": "08-fluxo-de-producao-com-ia", "ordem": 8, "titulo": "Monte um fluxo de produção com IA",
        "quando_usar": "Para organizar a semana e garantir a constância sem estourar o seu tempo.",
        "variaveis": ["videos_por_semana", "horas_por_semana", "ferramentas_que_ja_tem"],
        "secoes_geradas": ["producao"],
        "por_que_funciona": "Um sistema claro economiza tempo, e a regra de originalidade protege das políticas do YouTube sobre conteúdo repetitivo.",
        "original": "Aja como um gerente de produção profissional de YouTube. Desenhe um fluxo com IA pra eu publicar [número] vídeos por semana em menos de [horas] horas. Cubra pesquisa de tema, roteiro, narração ou gravação, edição, thumbnail, publicação, análise de dados e reaproveitamento em Shorts, TikTok e Reels. Recomende ferramentas grátis ou baratas pra cada etapa. Me dê modelos e um checklist de qualidade. Inclua uma regra pra manter meu conteúdo original e humano, pra ele não parecer produzido em massa nem repetitivo.",
        "body": _body(
            "Aja como um gerente de produção profissional de YouTube.",
            "Desenhe um fluxo com IA para publicar {{videos_por_semana}} vídeos por semana em menos de {{horas_por_semana}} horas do meu tempo. Ferramentas que já tenho: {{ferramentas_que_ja_tem}}. Cubra pesquisa de tema, roteiro, narração ou gravação, edição, miniatura, publicação, análise de dados e reaproveitamento em Shorts, TikTok e Reels, com quem faz cada etapa (eu, Claude, o sistema) e o tempo estimado. Recomende ferramentas grátis ou baratas. Dê modelos (título, descrição, comentário fixado) e um checklist de qualidade. Inclua uma regra de originalidade para o conteúdo continuar humano e não parecer produzido em massa nem repetitivo.",
            "`producao` com `meta`, `etapas[]` (etapa, quem, tempo_min, ferramenta, saida), `tempo_por_semana_horas`, `ferramentas_gratis_ou_baratas[]`, `modelos` e `regra_de_originalidade[]`."),
    },
    {
        "id": "09-plano-de-monetizacao", "ordem": 9, "titulo": "Planeje como você vai ganhar dinheiro",
        "quando_usar": "Cedo, para preparar a conta e a ordem das fontes de renda.",
        "variaveis": ["pais", "tipo_de_audiencia"],
        "secoes_geradas": ["monetizacao_fases"],
        "por_que_funciona": "Adicionar as fontes de renda na ordem certa mantém o foco no começo e deixa tudo pronto depois.",
        "original": "Aja como um estrategista de negócios pra criadores. Desenhe um plano de monetização pro meu canal. Inclua como se preparar pro Programa de Parcerias do YouTube e o AdSense, além de links de afiliado, patrocínios, produtos digitais, cursos, assinaturas, newsletters e comunidades. Me diga exatamente quando adicionar cada um: de 0 a 500 inscritos, de 500 a 1.000 e de 1.000 pra cima. Inclua um checklist pra inscrição: verificação em 2 etapas, nenhum aviso e as políticas em dia.",
        "body": _body(
            "Aja como um estrategista de negócios para criadores.",
            "Desenhe o plano de monetização do canal (país do criador: {{pais}}). Inclua como se preparar para o Programa de Parcerias do YouTube e o AdSense, além de links de afiliado, patrocínios, produtos digitais, cursos, assinaturas, newsletters e comunidades. Diga exatamente quando adicionar cada um: de 0 a 500 inscritos, de 500 a 1.000 e de 1.000 para cima. Inclua um checklist de inscrição (verificação em duas etapas, nenhum aviso, políticas em dia, dados fiscais, requisitos vigentes com a data). Mostre a conta de quantas visualizações o canal precisa para chegar à meta de renda, com o RPM estimado e a fonte.",
            "`monetizacao_fases` com `por_faixa[]` (faixa, foco, acoes[]) e `checklist_inscricao_ypp[]`; atualize também `monetizacao.meta_reais` se a meta mudou."),
    },
    {
        "id": "10-revisao-semanal", "ordem": 10, "titulo": "Revise seus números toda semana",
        "quando_usar": "Todo domingo, e no fim do mês.",
        "variaveis": ["dados_colados"],
        "secoes_geradas": ["revisao"],
        "por_que_funciona": "Pequenos ajustes toda semana somam: você repete o que funciona e corta o que não funciona.",
        "original": "Aja como um analista de dados do YouTube. Crie um sistema de revisão semanal e mensal pro meu canal. Eu vou colar meus dados: impressões, CTR, duração média da visualização, anotações do gráfico de retenção, inscritos ganhos por fonte e engajamento. Me diga o que cada número significa, o que é bom ou ruim pra o tamanho do meu canal e o que corrigir primeiro. Encontre padrões nos meus melhores vídeos. Me dê um plano pra melhorar os meus 3 vídeos mais fracos com títulos, thumbnails ou introduções novas.",
        "body": _body(
            "Aja como um analista de dados do YouTube.",
            "Crie o sistema de revisão semanal e mensal do canal. Dados desta semana: {{dados_colados}} (impressões, CTR, duração média da visualização, anotações do gráfico de retenção, inscritos ganhos por fonte, engajamento). Diga o que cada número significa, o que é bom ou ruim para o tamanho do canal (com faixas de referência comuns, marcadas como referência) e o que corrigir primeiro. Encontre padrões nos melhores vídeos. Dê um plano para melhorar os 3 vídeos mais fracos com títulos, miniaturas ou introduções novas, mudando uma coisa por vez.",
            "`revisao` com `semanal`, `mensal`, `metricas[]`, `padroes_nos_melhores_videos[]` e `melhorar_os_3_piores[]`."),
    },
    {
        "id": "00-playbook-completo", "ordem": 0, "titulo": "Playbook completo: projetar um canal novo",
        "quando_usar": "Quando for criar OUTRO canal. Executa os 10 prompts em sequência e grava o resultado no módulo Canais.",
        "variaveis": ["nome_do_canal", "nicho", "publico", "recursos", "meta", "data_de_inicio", "interesses", "habilidades", "videos_por_semana", "horas_por_semana", "pais"],
        "secoes_geradas": ["todas"],
        "por_que_funciona": "Um só pedido gera o planejamento inteiro, editável e clonável, em vez de dez conversas soltas.",
        "original": "",
        "body": "Execute o playbook completo de planejamento de canal para o canal descrito abaixo.\n\n" + CONTEXTO + "\n- Interesses: {{interesses}}\n- Habilidades: {{habilidades}}\n- Vídeos por semana: {{videos_por_semana}}\n- Horas por semana: {{horas_por_semana}}\n- País do criador: {{pais}}\n\n"
                + "## Como executar\n1. Crie o canal no MisterClip (Canais > Novo canal, ou `POST /api/channels` com template `vazio` ou um modelo salvo) com o nome e o assunto acima.\n"
                + "2. Execute, NESTA ORDEM, os prompts 02 (nicho), 03 (concorrentes), 01 (plano de 90 dias), 04 (ganchos e títulos), 05 (roteiro do primeiro vídeo), 06 (algoritmo), 07 (Shorts), 08 (produção com IA), 09 (monetização) e 10 (revisão semanal). Cada um está na biblioteca de prompts; use o campo `body` de cada um com os dados deste contexto.\n"
                + "3. Grave cada resultado na seção certa do canal com `POST /api/channels/{id}/plan/import` (ou `PUT /api/channels/{id}/plan/{secao}`) e os vídeos do calendário em `plan.videos`.\n"
                + "4. Mostre um resumo do que foi criado, os números reais encontrados (com data e fonte) e o que precisa de confirmação minha.\n\n" + REGRAS,
    },
]
