# MisterClip: análise de aderência, usabilidade e robustez

Data: 2026-11-21. Escopo: tudo o que o Thiago pediu na conversa × o sistema como está (local + nó na andes).
Método: leitura do código, 26 testes automáticos, execução real na andes (vídeo de 4 cenas), inspeção da interface em
tela de celular (375×812) e simulações de falha. O teste de 15 minutos (119 cenas) estava em andamento durante a análise;
**nada foi alterado na andes** (um deploy reiniciaria o contêiner e mataria o job).

## 1. Pedidos × situação

Legenda: ✅ funciona e foi verificado · 🟡 parcial / verificado só em parte · ❌ ausente · ⏳ aguardando o teste de 15 min

| # | Pedido | Situação | Observação |
|---|---|---|---|
| 1 | App tipo Vidrush com LLM open source na andes | 🟡 | Núcleo sim (voz, imagens, clipes, legendas, montagem). Faltam recursos periféricos do Vidrush (seção 2). |
| 2 | Receber o texto pronto e produzir o vídeo | ✅ | Fluxo completo validado com 4 cenas na andes. |
| 3 | Vídeo de ~15 min a cada 3–4 dias | ⏳ | Estimativa ~3 h por vídeo; medição real em andamento. |
| 4 | Português do Brasil, voz pronta | ✅ | Kokoro `pm_alex`. Não dá para ouvir amostras das vozes na interface. |
| 5 | Vídeo horizontal | ✅ | 1920×1080, 24 fps. Resolução fixa. |
| 6 | Nicho filosofia/ocultismo/tecnologia/futurismo | ✅ | 4 perfis cobrindo os temas; o roteiro de teste foi escrito para isso. |
| 7 | Clipes animados híbridos (LTX + Wan) | 🟡 | Wan validado dentro do app. **LTX nunca rodou dentro do app** (só nos testes avulsos); o perfil Cyber-místico depende dele. |
| 8 | Perfis de estilo escolhidos ao configurar a geração | ✅ | Galeria, troca por cena, criar/duplicar/editar, teste rápido (o teste rápido nunca foi executado em modo real). |
| 9 | Nó na andes, acessível pela malha | ✅ | `http://100.70.97.18:8490`, com token. |
| 10 | AudioGlifo não roda junto | 🟡 | Regra respeitada por convenção, mas o contêiner do AudioGlifo segue residente (3,9 GB de RAM) e já houve estouro de memória. |
| 11 | Crossfade real entre cenas | ✅ local · ⏳ andes | 26 testes (duração sem deriva, mistura real, modo em dois níveis com 25 cenas). Em produção, o teste de 119 cenas valida. |
| 12 | Música de fundo que abaixa na fala | ✅ local · ❌ andes | Teste numérico: cai >6 dB na fala. Nenhuma música foi enviada à andes; não rodou em produção. |
| 13 | "Usar o que há de melhor" | 🟡 | FLUX schnell (não dev), Wan 5B a 960×544, LTX 2B, torch 2.7/cu128 (o ComfyUI recomenda ≥2.8/cu130). Há teto de qualidade ainda não explorado. |
| 14 | Mobile first e boa usabilidade | 🟡 | Responsivo e sem rolagem lateral, mas pensado desktop-first e cansativo no celular (seção 3). |

## 2. Paridade com o Vidrush

Referência: documentação e páginas do produto (fontes ao final). Roteiro e análise de vídeos de referência ficam fora de
escopo por decisão do Thiago (os textos vêm de fora).

| Recurso do Vidrush | MisterClip |
|---|---|
| Cenas, locução, visuais, legendas, trilha, transições | ✅ |
| Editor para trocar visuais, ajustar áudio e corrigir texto | 🟡 troca imagem e texto por cena; sem editar a ordem das cenas, sem juntar/dividir, sem ouvir a locução por cena |
| Vozes (centenas) e vozes de nicho | 🟡 3 vozes pt-BR; sem clonagem; sem amostras na interface |
| Música original gerada | ❌ só envia arquivo próprio (sem biblioteca nem geração) |
| Miniatura a partir do título | ❌ |
| Título, descrição e tags do YouTube | ❌ (o qwen3 já instalado poderia gerar) |
| Publicação / agendamento | ❌ |
| Avatar apresentador | ❌ (não pedido) |
| Substituir uma cena sem refazer tudo | ✅ regerar imagem por cena; clipe por cena ainda não |

## 3. Usabilidade e mobile (medido em 375×812)

Bom: sem rolagem horizontal, fonte de 15 px, tema claro/escuro automático, galeria de perfis com prévia, fluxo lógico,
progresso por job, confirmação antes de apagar.

| Achado | Evidência | Gravidade |
|---|---|---|
| Página do projeto gigante no celular | 4 cenas = 2.877 px de altura; 119 cenas ≈ 80 mil px, sem índice, filtro, colapso nem paginação | Alta |
| Ação principal some ao rolar | Botões "Preparar / Aprovar e renderizar / Apagar" ficam só no topo; "Apagar" ao lado do botão principal | Alta |
| Sem passo-a-passo guiado | Todos os botões aparecem juntos; a ordem correta não é evidente | Média |
| Alvos de toque pequenos | 26 elementos entre 34 e 38 px na tela do projeto (mínimo recomendado: 44 px) | Média |
| Cabeçalho quebra em duas linhas | Menu desce para a segunda linha ao lado do título | Baixa |
| Sem endereço por tela | Recarregar a página volta à lista; o botão "voltar" do navegador sai do app | Média |
| Não dá para ouvir a narração nem ver o clipe | Só existem `<video>` do final e `<audio>` da música | Alta (decide-se a aprovação sem ouvir) |
| Voz/velocidade/roteiro só na criação | Depois, só o perfil é editável | Média |
| Escolha de perfil inacessível ao teclado | `input[type=radio]{display:none}` | Média |
| Sem anúncios para leitor de tela | 0 atributos `aria-*`/`role` (toast e erros não são "vivos") | Média |
| Token pedido por `prompt()` do navegador | Pouco amigável no celular | Baixa |
| Sem aviso do custo antes de renderizar | Nada diz "~3 h de GPU, AudioGlifo parado" | Média |
| Sem notificação ao terminar | Em tarefas de horas, o usuário precisa ficar abrindo a página | Média |

## 4. Defeitos funcionais e de robustez

| # | Defeito | Evidência | Gravidade |
|---|---|---|---|
| 1 | **Projeto fica preso em "rendering" após reinício** (deploy, queda, falta de memória) | Simulado: job vira "falhou", projeto continua `rendering`; os botões exigem `storyboard`/`done` | Alta |
| 2 | Não há como cancelar um job nem tentar de novo | Sem endpoint de cancelar/retry; parar exige reiniciar o contêiner, que cai no defeito 1 | Alta |
| 3 | Clipe animado de ~4 s repete em *loop* em cenas de ~10 s | Visto no vídeo de teste (cena 1) | Média |
| 4 | LTX nunca exercitado dentro do app | Nenhum teste e2e usa `ltx`; o backend de teste faz zoom nos dois | Média |
| 5 | Atualização do projeto inteiro a cada 1,5 s | Polling busca o JSON completo (com os tempos de todas as palavras) enquanto a página está aberta; no celular é bateria e dados | Média |
| 6 | Intermediários nunca são apagados | Projeto de 37 s ocupa 32 MB; estimativa para 15 min: 3–4 GB (segmentos, vídeo bruto, temporários do crossfade) | Média |
| 7 | Falha em `prepare` num projeto já em storyboard regride o status para "planned" | Leitura do `worker.py` | Baixa |
| 8 | Sem backup de `/mnt/apoio` | Dados e modelos num único disco | Média |
| 9 | Token em cookie sem HttpOnly e tráfego em HTTP | Aceitável só porque a malha é privada | Baixa |

## 5. Backlog priorizado (esforço: P pequeno, M médio, G grande)

**P0, antes do uso diário**
1. Recuperar projetos presos no startup + botão **Cancelar** + **Tentar de novo** (P).
2. Rodar LTX dentro do app (e2e real) e resolver o loop dos clipes (clipes mais longos ou vai-e-volta) (M).
3. Mostrar estimativa de tempo e avisos antes de renderizar; notificação ao concluir (P).

**P1, usabilidade e mobile**
4. Rotas com URL (`#/projeto/ID`), passo-a-passo (Roteiro → Cenas → Storyboard → Vídeo) e barra de ação fixa no rodapé do celular (M).
5. Cenas compactas no celular: lista colapsável, filtro "com problema", paginação, alvos de 44 px (M).
6. Ouvir a narração por cena, ver o clipe, ouvir amostra das vozes antes de criar (P–M).
7. Editar roteiro/voz/velocidade depois de criado; adicionar, remover, juntar e dividir cenas (M).
8. Endpoint leve de progresso (polling barato) (P).
9. Acessibilidade: foco visível nos cartões de perfil, `aria-live`, tela de login no lugar do `prompt()` (P).

**P2, paridade com o Vidrush**
10. Título, descrição, capítulos e tags do YouTube gerados pelo qwen3 a partir do roteiro (P–M).
11. Miniatura com FLUX + título (M).
12. Publicação/agendamento no YouTube (G; exige OAuth do Google e sempre com a sua confirmação).
13. Música: biblioteca própria ou geração local; mais vozes / clonagem local (M cada).

**P3, infraestrutura e qualidade**
14. Política de limpeza de intermediários e backup do apoio (P).
15. Imagem própria com torch ≥ 2.8 / cu130; FLUX dev, Wan 1280×704, LTX 13B (M).

## 6. O que esta análise não verificou
- Vídeo de 15 min completo (teste em andamento): tempo real, memória, disco e crossfade com 119 cenas.
- Música com *ducking* em produção; teste rápido de perfil em modo real; LTX no app.
- Uso real em um celular físico dentro da malha (a inspeção foi por emulação de 375×812).
- Os números do Vidrush vêm de páginas de terceiros e da documentação; descrições divergem entre as fontes.

## Fontes (Vidrush)
- https://docs.vidrush.ai/docs/understanding-vidrush
- https://vidrush.ai/features/ai-video-editor
- https://topai.tools/t/vidrush-ai
- https://pollo.ai/m/vidrush

## 7. Status do P0 (atualizado em 2026-11-21, ainda sem deploy)
Implementado e testado localmente (39 testes passam); **não foi para a andes** porque o teste de 15 min está rodando lá.

| Item | Situação |
|---|---|
| Recuperar projetos presos após reinício | ✅ `recover_stuck()` no startup + status calculado pelo que existe |
| Cancelar job (fila e em execução, interrompe o ComfyUI) | ✅ |
| Tentar de novo, retomando de onde parou | ✅ (preparar agora salva a cada cena) |
| Clipe sem loop | ✅ local (continua em zoom a partir do último quadro); validar na andes |
| LTX dentro do app | 🟡 workflows validados contra o retrato do ComfyUI da andes (testes); execução real fica para depois do teste de 15 min |
| Estimativa de tempo, aviso antes de renderizar, ETA, aviso ao terminar | ✅ |

Achado novo: com `--cache-none` no ComfyUI, cada imagem leva ~30 s (era 12–13 s), porque o FLUX de 17 GB é recarregado a cada
prompt. Reavaliar as flags (provavelmente manter só `--disable-pinned-memory`) quando a andes estiver livre.

## 8. Vídeo real de 30 s (2026-11-21): resultados e correções
Projeto "Teste 30s: Wan + LTX + música" (93 palavras, 4 cenas, perfil Cinemático sombrio, crossfade 0,6 s, trilha sintetizada).
Arquivo: `teste-real/video-30s-wan-ltx-musica.mp4` (37,7 s, 1080p, estéreo).

| Etapa | Tempo |
|---|---|
| Planejar (LLM, incluindo a carga fria) | ~80 s |
| Preparar (voz, tempos, 4 imagens) | 71 s |
| Clipe Wan (cena 1) | 237 s |
| Clipe LTX (cena 4), primeira vez dentro do app | 52 s |
| Montagem final (crossfade + música + legendas) | ~30 s |

Defeitos achados nesse teste e **corrigidos e deployados** (42 testes):
1. **OOM ao trocar de motor de clipe** (Wan -> LTX): o ComfyUI chegou a 25 GB de RAM e o kernel o matou. Agora o app descarrega o ComfyUI quando o motor muda e sempre que a RAM disponível cai abaixo de 12 GB (teste de regressão).
2. **Legendas empilhando em duas linhas** (11 de 16 trechos se sobrepunham em até 0,16 s): o "segura" de 0,15 s agora nunca invade o trecho seguinte.
3. **Áudio baixo** (narração -26,6 dB de média, mix -29 dB): estágio final `loudnorm` leva o vídeo a -16,3 LUFS.
4. `--cache-none` do ComfyUI dobrava o tempo por imagem (30 s vs 12 s); removido do padrão do deploy.

Não verificado: a redução de volume da música na fala foi comprovada numericamente nos testes, mas o resultado
auditivo no vídeo real depende de você ouvir (não há como medir o "gosto" aqui).

## 9. Mobile e usabilidade (P1) implementados e deployados em 2026-11-21 (47 testes)
| Item da análise | Situação |
|---|---|
| Página gigante no celular | ✅ cenas em linhas compactas, filtros (todas / animadas / problemas), "mostrar mais"; 119 cenas = ~2.900 px de página (eram ~80.000) |
| Ação principal some ao rolar | ✅ barra de ação fixa embaixo com um botão principal por estado; Apagar/Replanejar ficam no menu "⋯" |
| Sem passo-a-passo | ✅ Roteiro, Cenas, Opções e Vídeo, com contador de pendências |
| Alvos de toque pequenos | ✅ mínimo de 44 px em todos os controles (medido: só o link "pular" invisível fica abaixo) |
| Sem endereço por tela | ✅ rotas `#/p/ID/cenas` etc.; recarregar e "voltar" funcionam |
| Não ouve narração nem vê o clipe | ✅ player de narração e de clipe por cena; amostra de voz antes de criar |
| Voz/velocidade/roteiro só na criação | ✅ passo "Roteiro" edita título, texto, voz e velocidade |
| Adicionar/remover/juntar/dividir cenas | ✅ (arquivos por id: nenhuma cena sobrescreve a de outra) |
| Polling pesado | ✅ endpoint `/status` de ~200 bytes; projeto enxuto cai de 143 KB para 89 KB no projeto real; miniaturas com cache |
| Radios inacessíveis ao teclado, sem aria, `prompt()` do token | ✅ foco visível, `aria-live`/`role`, tela de login |
| Endereço difícil | ✅ `http://misterclip.nord` (apelido Meshnet + proxy na porta 80) |

Ainda pendente do P1: nada crítico. Do restante: metadados/miniatura/publicação YouTube (P2), limpeza de intermediários e backup (P3).
