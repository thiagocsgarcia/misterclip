# MisterClip

Transforma um roteiro já escrito num vídeo horizontal (16:9) de ~15 min, com narração em português do Brasil,
legendas, imagens por cena no estilo de um **perfil visual** e clipes animados (LTX / Wan) nas cenas-chave.
Roda na andes (RTX 5060 Ti 16 GB); o desenvolvimento é local, em **modo teste** (sem GPU).

## Endereço na malha (Meshnet)
Dentro da malha NordVPN, o MisterClip abre em **http://misterclip.nord** (apelido da andes na Meshnet + proxy nginx na
porta 80, contêiner `mc-proxy`). O endereço antigo `http://100.70.97.18:8490` continua funcionando. Funciona em qualquer
dispositivo da malha, inclusive o celular. Para mudar o nome: `nordvpn meshnet set nickname <nome>` na andes.

## Rodar localmente (modo teste)

```bash
docker compose up --build        # http://localhost:8490
docker compose run --rm --no-deps misterclip python -m pytest -q
```

No modo `fake` as imagens são placas coloridas, a voz é um tom e os tempos das palavras são estimados;
o resto (cenas, perfis, fila, storyboard, Ken Burns, legendas ASS, mixagem e render FFmpeg) é o código real.

## Fluxo

1. **Novo vídeo**: título, roteiro (use uma linha `[CENA]` para cortes manuais), perfil de estilo, voz e velocidade.
2. **Planejar**: divide em cenas de ~9 s, escreve o prompt visual de cada uma (LLM no modo real) e escolhe quais animar.
3. **Preparar**: narração por cena, tempos por palavra (Whisper alinhado ao texto original) e uma imagem por cena.
4. **Storyboard**: edite texto/prompt/perfil/animação por cena e regere imagens individualmente.
5. **Aprovar e renderizar**: clipes animados (se houver), montagem, legendas, acabamento do perfil, MP4.

Cada etapa é idempotente: só refaz o que está faltando ou foi invalidado por uma edição.

## Estrutura

| Caminho | Função |
|---|---|
| `app/main.py` | API FastAPI + serve a interface; token opcional (`MC_TOKEN`) |
| `app/worker.py`, `app/db.py` | fila de jobs (1 worker, nunca 2 etapas na GPU) e SQLite |
| `app/pipeline/engine.py` | etapas: plan, prepare, regen_image, render, profile_test |
| `app/pipeline/assemble.py` | FFmpeg: Ken Burns, clipes, narração, música, acabamento |
| `app/pipeline/backends/` | `fake` (teste) e `real` (ComfyUI, Kokoro, faster-whisper, Ollama) |
| `app/captions.py` | alinhamento texto original × Whisper e geração do ASS |
| `app/scenes.py`, `app/profiles.py` | divisão em cenas e perfis de estilo |
| `profiles/*.json` | 4 perfis embutidos; os do usuário ficam em `data/profiles/` |
| `web/` | interface Vue 3 (sem build; Vue vendorizado) |

## Perfis de estilo
JSON com bloco de estilo, modelo, parâmetros, motor de clipe (`ltx` rápido / `wan` fiel), % de cenas animadas,
acabamento (cor, grão, vinheta) e legendas. Os embutidos são só leitura: duplique para editar. O botão **Testar**
gera uma imagem de amostra antes de gastar GPU num vídeo.

## Modo real (andes)
Em produção na andes desde 2026-11-21 (`scripts/deploy-node.sh aries@100.70.97.18`). Validado com um vídeo de 4 cenas
(LLM, voz, tempos, imagens FLUX, clipe Wan, FFmpeg 1080p). O teste de ~15 min (119 cenas) está em andamento; os
resultados e a fila de problemas ficam na memória do projeto.

Pontos de atenção:
- a andes tem 30 GB de RAM: voz/legendas rodam em processos filhos (morrem ao fim da etapa) e o ComfyUI sobe com
  `--cache-none --disable-pinned-memory --mmap-torch-files`. Se faltar memória, pare o contêiner `audioglifo-node`;
- o AudioGlifo não deve rodar junto (GPU compartilhada);
- imagem própria com torch >= 2.8 / cu130 ainda é pendência (hoje reaproveita `misterclip-comfy:test`).

## Planejamento editável, clonável e biblioteca de prompts

- **Tudo no plano de um canal é editável** (aba Plano, Ideias, Operação): cada seção tem **Editar** (formulário gerado sozinho para qualquer texto, lista ou objeto) e "editar como texto". O que você edita fica marcado em `plan._edited` e **não é sobrescrito** quando o modelo é atualizado (`channel_plan.upgrade`, versão do plano em `VERSION`).
- **Duplicar canal** (cópia do plano, calendário e ideias, sem vídeos nem números) e **Salvar como modelo** (aparece em Canais > Novo canal). Modelo "Em branco" traz todas as seções vazias. API: `POST /api/channels/{id}/clone`, `POST /api/channels/{id}/save-template`, `GET /api/channel-templates`.
- **Executar o playbook para um canal novo**: o Claude grava o resultado com `POST /api/channels/{id}/plan/import` (várias seções) ou `PUT /api/channels/{id}/plan/{secao}`.
- **Biblioteca de prompts** (`#/prompts`, `app/prompt_library.py`): os 10 prompts do playbook com o **texto original preservado** e uma versão ajustada (contexto do canal, regras de qualidade, formato de entrega), variáveis para preencher e copiar, e o "Playbook completo" que executa os dez em ordem. Edição e "voltar ao de fábrica".
- **Conteúdo do Arcano Digital** (`app/channel_content_a/b/c.py`): nicho (5 nichos comparados), identidade e espectador, 10 tipos de concorrente + 10 lacunas, **100 ideias ranqueadas**, 20 ideias com 3 títulos/miniatura/gancho, algoritmo, produção com IA, monetização por fase + lista de inscrição, revisão semanal/mensal e um roteiro completo marcado (B-roll, tela, som, quebras, teaser, pontos de saída; a narração limpa sai por `GET /api/channels/{id}/roteiros/{n}/narracao`).

## YouTube (API): conexão, envio, publicação pelo calendário e métricas

- **Aba YouTube do canal** (`app/youtube.py`, `app/youtube_jobs.py`, `web/youtube.js`): guia de configuração (projeto Google Cloud com YouTube Data API v3 e YouTube Analytics API, tela de permissão **publicada "Em produção"**, ID do cliente tipo **App para computador**), conexão por login com PKCE e redirecionamento local `http://127.0.0.1:8765` (o navegador mostra erro de conexão; a pessoa cola o endereço da página), dashboard (inscritos, horas só de vídeos longos, Shorts, gráficos de 28/90 dias, tabela por vídeo com views/retenção/CTR/inscritos, os 3 que mais precisam de atenção) e envios feitos.
- **Envio**: Publicar > Enviar ao YouTube (upload resumable em pedaços de 8 MiB com retomada, título, descrição com capítulos, tags, miniatura escolhida, marca de conteúdo sintético, "agendar" = privado + `publishAt`). **Publicação pelo calendário**: com "Enviar sozinho" ligado, o piloto (agendador, a cada 5 min) manda o próximo vídeo pronto na data/hora do calendário, um por vez, máximo 5 por dia (cota: 1.600 de 10.000 unidades por envio).
- **Métricas**: leitura diária automática (e botão), guardada em `youtube_snapshots`; vira uma linha por dia na aba Métricas; vídeos enviados que o YouTube publicou viram "Publicado" no calendário.
- **Limites reais**: projetos de API **não auditados enviam só vídeos privados** (o agendamento público exige a auditoria do Google; o sistema avisa e você publica no Studio); app Google em modo "Teste" gera permissão que vence em 7 dias; a chave do projeto e os tokens ficam em `data/youtube` (permissão 600) e nunca voltam pela API; CTR e o filtro de vídeos longos dependem do que a Analytics API devolver (o sistema avisa e normaliza). Não foi testado contra o YouTube real (precisa das suas credenciais); os testes usam um YouTube falso.

## Clipe musical (a história da música em cenas animadas, sem cantor)

- **Novo clipe** (menu): você escolhe a sua música; ela sobe na hora e a andes **transcreve a letra** (Whisper large-v3, sem o filtro de voz, que descartava o canto) e preenche o campo para você **revisar e corrigir** antes de criar. Depois escolhe estilo, ritmo dos cortes (calmo, normal, agitado), animação (todas as cenas, só as partes intensas ou só câmera) e se a letra aparece na tela.
- **Planejar** (`app/pipeline/clipengine.py`, `app/musicclip.py`): analisa a música (andamento, batidas, compassos e partes por intensidade, em numpy, ~1 s), o LLM lê a letra e cria a **bíblia visual** da história (protagonista, cenário, paleta, arco) e cada cena recebe o momento certo do arco; os **cortes caem na batida** (partes intensas cortam mais rápido); a letra é marcada no tempo (alinhamento por Whisper, com fallback proporcional); o movimento: LTX em todas as cenas e Wan nas de maior destaque.
- **Preparar** gera só as imagens; **Renderizar** usa a montagem normal com a música inteira como áudio (sem narração nem ducking) e corte direto por padrão. As cenas seguem a música: não há dividir/juntar/apagar; edita-se letra da cena, descrição da imagem, estilo e movimento. A letra do projeto também pode ser corrigida na aba Roteiro (planeja o clipe de novo).
- Armadilhas: o filtro de voz (VAD) do Whisper devolve zero trechos em música cantada sobre base instrumental (medido na andes: 0 com VAD, letra completa em 5 s sem ele); a análise de partes é aproximada (não identifica estrofe nem refrão). Os envios em rascunho ficam em `data/clip_uploads` e são apagados após 24 h.
- **Animações sem deformação (processo de geração, 2026-11-22):** no primeiro clipe real, algumas animações ficaram deformadas e assustadoras (rosto contorcido numa cena de corrida, braço entortando, "sósia chorando" num espelho). Causas achadas e corrigidas no processo, para todo clipe futuro: (1) o prompt de movimento repetia a ação da cena; agora `musicclip.motion_prompt` pede só câmera lenta e movimento do ambiente, com pessoas quase paradas; (2) semente fixa (7) em todos os clipes: agora cada cena tem a sua (`clip_seed`) e o botão **Refazer a animação** sorteia outra; (3) o prompt negativo do Wan começava com "static" (pede MAIS movimento): trocado por `NEGATIVE_MOTION` (rosto/corpo deformado, derretendo, assustador, movimento brusco); (4) clipes de 3 s em vez de 4 s (a deformação cresce com o tempo; o resto da cena é zoom suave); (5) composição segura nas imagens: plano aberto, pessoas de costas ou de longe, calmas, vida da cena no ambiente, nunca close de rosto, espelhos ou reflexos de outra pessoa; (6) tom da história "poético, nunca terror"; (7) o personagem é descrito SEM rosto e injetado pelo código no lugar de `[P]` (o LLM copiava o rótulo e gastava as palavras). Uma trava automática por diferença de pixels foi testada e **não** separa clipes bons de ruins (não detecta rosto deformado): o controle fino é por cena (Refazer a animação ou "Zoom suave").
- Tempo na andes (estimativa): música de 4 min no ritmo normal ≈ 80 cenas ≈ 2 h (LTX ~1 min/cena, FLUX ~14 s/imagem, Wan ~4 min nas de destaque).

## Shorts (cortes verticais + plano de 90 dias)

- **Gerar Shorts** (vídeo pronto > Publicar): o MisterClip escolhe de 1 a 5 trechos de 30 a 45 s (o LLM da andes escolhe; se falhar, uma pontuação por texto), sempre em limites de cena, e monta cada Short em 1080×1920 só com FFmpeg: vídeo sem legendas + narração (+ música) com legendas verticais grandes e uma frase de gancho no topo. Formato: imagem inteira com fundo desfocado (padrão) ou preencher a tela. Código: `app/shorts.py`, `generate_shorts` em `engine.py`, `short_render` em `assemble.py`; arquivos em `shorts/` do projeto; metadados em `meta.shorts`.
- **Aba Shorts do canal**: estratégia, comparação dos dois caminhos do Programa de Parcerias (horas de vídeos longos × visualizações de Shorts, contagens separadas, recomendação para o canal), calculadora, regras, calendário de 90 dias (4 Shorts por semana, 1 e 3 dias depois de cada vídeo longo) e banco de **12 ideias por vídeo** (gancho, duração ideal, final em laço, dica visual, como levar ao vídeo longo). As ideias-base vêm de modelos (`app/shorts_plan.py`); "Gerar ideias a partir do roteiro" pede ao LLM da andes ideias baseadas no texto real (job `shorts_ideas`).
- Planos de canais antigos são atualizados sozinhos na inicialização (`channel_plan.upgrade`), preservando títulos, situações e notas.
- Regra do `main.py`: o `app.mount("/")` de arquivos estáticos fica SEMPRE no fim do arquivo, senão engole as rotas escritas depois dele.

## Canais (plano de 90 dias por canal)

- Aba **Canais**: cada canal tem **Resumo** (dia do plano, rumo ao Programa de Parcerias, próximo vídeo, tarefas da semana, marcos dos dias 30/60/90), **Calendário** (26 vídeos, terça e sexta, ligados aos vídeos do MisterClip), **Plano** (posicionamento, pilares, formatos, crescimento, retenção, monetização, concorrentes, fontes), **Métricas** (registro semanal, gráfico meta × realidade, projeção, calculadoras) e **Roteiro e lista** (modelo de roteiro e lista de verificação antes de publicar).
- O primeiro canal, "Arcano Digital" (nome editável), recebeu todos os vídeos já criados. Novos canais: Canais > + Novo canal (plano pronto ou em branco). Cada vídeo pertence a um canal (`projects.channel_id`); a lista de vídeos ganha filtro por canal quando há mais de um.
- Código: `app/channel_plan.py` (modelo do plano: só dado, copiado para cada canal), `app/channels.py` (dia/semana, progresso, projeção), rotas `/api/channels*` em `app/main.py`, interface em `web/canal.js`.
- Metas são de planejamento, não promessas. Regras do YouTube: 4.000 h + 1.000 inscritos hoje; a partir de 01/02/2027 novos entrantes precisam de 8.000 h qualificadas (confirmar no Studio).

## Andamento, roteiro ao vivo e processamento sem você

- Cada tarefa mostra uma **barra por etapa** (voz, tempos das legendas, imagens, animação, montagem, vídeo final) com "x de y"; a API guarda isso em `jobs.stages` e o expõe em `/status`.
- Enquanto produz, o painel **Roteiro em produção** mostra o roteiro completo, destaca a cena atual e marca voz/imagem/animação prontas (`GET /api/projects/{id}/scenes-state`). Na lista de vídeos, cada projeto em andamento tem uma barra pequena.
- **Tudo roda no servidor (andes)**: fechar a página, atualizar a tela ou desligar o seu computador não interrompe nada. Se a própria andes ou o container reiniciar, `db.resume_interrupted()` recoloca as tarefas na fila e elas seguem (máx. 3 tentativas, para não entrar em laço).
- `POST /api/projects/{id}/run-all` ("Fazer tudo agora") cria um agendamento imediato: prepara o que falta e renderiza sem parar para revisão.
- Agenda: o card "Dia selecionado" é paginado (começa com 5; opções 5/10/20).

## O canal comanda a geração (regras do canal)

O usuário escreve o roteiro; o sistema monta o vídeo com base nas premissas do canal. O roteiro **nunca é reescrito**: as regras só verificam e avisam.

- As regras ficam na seção editável **Regras do canal** da aba Plano (`regras_do_canal`, defaults em `app/channel_rules.py`): voz e velocidade, estilo visual, segundos por cena, proporção animada, motor de animação, transição, legendas, música, regras de título/miniatura/descrição/roteiro e de publicação.
- **Novo vídeo**: mostra as premissas do canal e verifica o roteiro na hora (`POST /api/channels/{id}/lint`). Dois botões: *Criar e revisar as cenas* ou *Montar o vídeo sozinho* (`run-all`: divide, prepara, renderiza, gera título/descrição, miniaturas e Shorts conforme as regras).
- **Publicar**: cartão “Regras do canal” (`GET /api/projects/{id}/checks`) e “Revisar o roteiro com a IA” (`script_review`). Título, miniatura e hashtags devolvidos pela IA são corrigidos pelas regras.
- **YouTube**: envio com erro nas regras é barrado (409); o usuário pode enviar mesmo assim (`ignorar_regras`). O piloto automático nunca sobe sozinho um vídeo com erro e marca o item do calendário como “revisar”.

## Calendário da Agenda (modelo do SIGEM)
A aba **Agenda** tem, no mesmo modelo do calendário do SIGEM: **linha do tempo** do mês (faixas "Agendados e em andamento" e
"Já aconteceram", marcador de "hoje"), **grade mensal** (Dom–Sáb, 5 ou 6 semanas, dias de outro mês esmaecidos, hoje em círculo,
dia selecionado com anel; no celular cada dia mostra pontos coloridos por situação e em tela maior, os títulos), navegação de mês
com botão **Hoje**, **legenda** e **painel do dia** com os itens (abrir o vídeo, cancelar o agendamento) e o botão
**"Agendar um vídeo neste dia"**. Os itens são agendamentos e também execuções feitas na hora (preparar/criar o vídeo).
O carregamento é por mês, com cache e pré-carga dos meses vizinhos (`web/agenda-mes.js`, equivalente ao `useAgendaMes` do SIGEM);
o servidor só entrega horários em epoch e o navegador separa por dia no fuso do usuário. API: `GET /api/calendar?month=AAAA-MM`.
Referência no SIGEM (somente leitura): `/home/phoenix/docker-projects/sigem/resources/js/Components/Sigem/CalendarioInterativo.vue`.

## Trocou o estilo ou a voz de um vídeo pronto? Dá para desfazer
Trocar o estilo (ou a voz/velocidade) não apaga nada: as imagens (ou narrações) ficam marcadas como **desatualizadas** e um aviso
oferece três saídas: **voltar ao estilo/voz anterior** (aceita o que já existe e desfaz a troca), **manter como está** (continua com
o estilo novo só daqui para frente) ou **gerar de novo**. Cada cena também tem "Manter esta imagem". O status do vídeo não é
rebaixado e criar o vídeo com itens desatualizados é recusado com uma explicação (em vez de virar um job que falha).
API: `POST /api/projects/{id}/style/revert`, `/voice/revert`, `/stale/keep`. Cada imagem guarda o estilo com que foi feita
(`image_profile`), então voltar ao estilo certo limpa a pendência sozinho.

## Publicar (título, descrição, tags e miniatura)
Aba **Publicar** de cada vídeo. O LLM da andes sugere 5 títulos (até 100 caracteres), a introdução da descrição, 15 tags
(até 500 caracteres no total), 3 hashtags e **capítulos** (um a cada ~90 s, com os horários calculados sozinhos pela linha do
tempo do vídeo; só em vídeos a partir de ~5 min, pois o YouTube exige 3 capítulos de 10 s ou mais, o primeiro em 0:00).
Tudo é editável; a descrição final é montada na hora (intro + capítulos + hashtags) e há botões de copiar.
A **miniatura** sai em 1280×720 (até 2 MB), em 3 opções geradas pelo FLUX com o texto por cima (até 4 palavras, editável sem
gastar GPU). O MisterClip **não publica** no YouTube: você copia e cola no YouTube Studio (publicar exigiria o login do
Google e é sempre uma ação sua). API: `GET /api/projects/{id}/publish`, `POST .../metadata/generate`, `PUT .../metadata`,
`POST .../thumbnail/generate|compose|select`, `GET .../thumbnail/download`.

## Legendas editáveis, pausa por cena, rascunho de roteiro e voz/imagem mais seguras
- **Editar as legendas** (aba Vídeo, vídeo pronto): corrige texto e tempo de cada linha e grava só as legendas (`recaption`, FFmpeg, segundos, sem GPU). A edição fica em `meta.captions_edit` e só vale enquanto a duração do vídeo não muda; `DELETE /api/projects/{id}/captions` volta às automáticas.
- **Pausa depois da fala** por cena (`PATCH .../scenes/{n}` com `pause`, 0 a 3 s; padrão 0,45 s). Muda a duração: o vídeo fica marcado `render_stale` até ser criado de novo (as animações prontas são reaproveitadas).
- **Rascunho de roteiro** (`POST /api/channels/{cid}/videos/{n}/draft`, job `script_draft`): o LLM da andes escreve esboço (tese, gancho, seções) e depois cada seção, dentro das regras do canal; vai para `plan.roteiros` com a marca `rascunho` (tese, fontes, incertezas, avisos do lint). Nunca troca um roteiro sem a marca (só com `force`). É rascunho: os fatos precisam ser conferidos.
- **Voz**: o texto que vai para a voz passa por `ptnum` (anos, valores, porcentagens e decimais por extenso) e pela tabela `regras_do_canal.narracao.pronuncias` (`{"Thiel": "Tíl"}`); a legenda e o roteiro do autor não mudam.
- **Imagens**: `imagecheck` recusa quadro preto, branco ou liso e gera de novo com outra semente (até 3 tentativas); se continuar ruim, a cena ganha o aviso `image_warning`.

## Roteiros por ideia, modal de edição e paginação
- Na aba Ideias do canal, cada ideia tem **Escrever roteiro** (ou **Editar roteiro**, quando já existe) e há o botão **Escrever os roteiros** das próximas 3, 5 ou 10 ideias de maior potencial (`POST /api/channels/{cid}/ideas/scripts`, job `idea_scripts`, uma ideia por vez na fila da andes; cada roteiro é salvo assim que sai). O texto fica em arquivo (`data/idea_scripts/{canal}/{n}.json`), fora do plano.
- O prompt segue o playbook de roteiro (gancho com laço aberto, prova rápida, contexto, pontos, teaser no meio, final forte, marcações `[B-ROLL]`, `[TELA]`, `[SOM]`, `[QUEBRA]`, `[TEASER]`, `[SAÍDA]`) e usa o roteiro aprovado do canal (`app/estilo_exemplo.txt`) como referência de ritmo; retenção: abertura concreta, tensão entre seções, laço aberto no início e fechado no fim. O modelo local pode errar fatos: o rascunho traz tese, fontes e incertezas para conferir.
- O modal **Editar roteiro** mostra o texto marcado, edita, salva (`PUT .../ideas/{n}/script`), confere as regras do canal e deixa criar o vídeo com a narração limpa.
- **Duração dos vídeos: 8 a 12 minutos** (pode passar disso quando o tema pede, até 30: `roteiro.minutos_maximo`) (`regras_do_canal.roteiro.minutos_por_formato`; 125 palavras por minuto ≈ 1000 a 1500 palavras).
- **Paginação** (componente `web/pager.js`, 10/20/50 por página) em todas as listas de registros: vídeos, cenas, legendas, agenda, Shorts, canais, calendário, ideias, roteiros, métricas, prompts e vídeos do YouTube.

## Esqueci o token (login)
A tela de login tem o botão "Não tenho o token: enviar para o meu e-mail" (`POST /api/auth/send-token`, público). O destinatário é sempre `MC_TOKEN_EMAIL` do servidor, nunca vem do pedido; no máximo 1 envio a cada 2 min e 5 por hora; a página nunca mostra o token nem o motivo de falha do SMTP (fica no log). Configure no `.env` da andes (`~/docker-projects/misterclip/.env`): `MC_TOKEN_EMAIL`, `MC_SMTP_HOST`, `MC_SMTP_PORT` (587 com STARTTLS ou 465), `MC_SMTP_USER`, `MC_SMTP_PASSWORD`, `MC_SMTP_FROM`; depois rode o deploy de novo. Sem isso o botão responde que o envio não foi configurado.

## Agendamento (por vídeo)
Em cada vídeo, **⏰ Agendar** escolhe o dia e a hora em que o MisterClip prepara o que faltar (voz e imagens) e cria o vídeo
sozinho. A tela **Agenda** lista tudo. Regras: um agendamento roda por vez e só com a fila vazia (a GPU é uma só); se a andes
estava desligada na hora, ainda roda até 12 h depois (depois vira "perdido"); uma queda no meio reenvia a etapa uma vez;
cancelar um agendamento em execução interrompe o job. Há um agendamento pendente por vídeo (agendar de novo substitui).
API: `PUT/GET/DELETE /api/projects/{id}/schedule`, `GET /api/schedules`.

## Interface em linguagem simples
Toda tela diz o que está acontecendo e qual é o próximo passo (cartão "Próximo passo"), tem dicas dobráveis, textos de apoio
nos campos, página **Ajuda** (botão "?") com passo a passo, tempos de referência, glossário e dúvidas comuns, e mensagens de
erro que explicam o que fazer. Um teste automático (`tests/test_ui_copy.py`) impede termos técnicos (modelos, ferramentas,
siglas) de voltarem à interface.

## Opções do vídeo (painel no projeto)
- **Transição entre cenas**: *crossfade* real (padrão), fade pelo preto, dissolve ou corte seco, com duração de 0,2 a 2 s
  (por padrão herda do perfil). Implementado com `xfade`; em vídeos longos junta 10 cenas por vez, em dois níveis.
- **Música de fundo**: envie mp3/wav/m4a/ogg/flac pela interface (fica em `data/music/`), escolha o volume e ligue
  **"baixar o volume quando há fala"**: a narração comanda um compressor (*sidechain*) e a música abaixa sozinha.
  Use apenas músicas que você tem direito de usar.
- As opções valem na próxima renderização (não invalidam imagens nem clipes).

## Robustez (P0)
- **Cancelar** qualquer job em andamento (a geração do ComfyUI é interrompida na hora); o que já foi gerado fica salvo.
- **Tentar de novo** continua de onde parou (voz, tempos, imagens e clipes já prontos não são refeitos).
- Se o serviço reiniciar no meio de um job, o projeto **não fica mais preso**: no startup ele volta a um estado utilizável.
- **Estimativas** nos botões (calibradas com a andes) e aviso antes de uma renderização longa.
- **Aviso ao terminar**: título da aba, bip e vibração; opcionalmente um POST para `MC_NOTIFY_URL`
  (ex.: um tópico do ntfy que você escolher). Vem desligado; só envia título do projeto, tipo do job e resultado.
- Clipes animados curtos **não repetem em loop**: o movimento se acomoda num zoom lento a partir do último quadro.

## Limitações conhecidas do esqueleto
- Sem fila de várias GPUs nem cancelamento de job em andamento.
