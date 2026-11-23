/** Visualizador e editor genérico das seções do plano de um canal (qualquer texto, lista ou objeto do plano pode ser lido e editado). */
import { ref, reactive, computed, watch } from './vendor/vue.esm-browser.prod.js';
import { usePager, Pager } from './pager.js';

const LABELS = {
  promessa: 'Promessa', publico: 'Para quem', voz: 'Como falar', diferencial: 'Por que pode funcionar', evitar: 'O que evitar', nome: 'Nome', peso: 'Peso (%)', papel: 'Papel', texto: 'Texto',
  duracao: 'Duração', uso: 'Para que serve', videos_por_semana: 'Vídeos por semana', shorts_por_semana: 'Shorts por semana', dias: 'Dias', horario: 'Horário', titulo: 'Título', itens: 'Itens',
  estrutura: 'Estrutura', regras: 'Regras', ypp: 'Requisitos do Programa de Parcerias', politica: 'Conteúdo autêntico', etapas: 'Etapas', meta_reais: 'Meta de renda', dados: 'Dados', licao: 'O que aprender',
  aviso: 'Aviso', comparacao: 'Comparação de nichos', nicho: 'Nicho', nota: 'Nota', demanda: 'Demanda', concorrencia: 'Concorrência', busca: 'Busca', anuncios: 'Anúncios', vida_util: 'Vida útil',
  destaque: 'Como se destacar', escolhido: 'Nicho escolhido', motivo: 'Motivo', identidade: 'Identidade', slogan: 'Slogan', descricao_do_canal: 'Descrição do canal', estetica: 'Estética', valores: 'Valores',
  espectador: 'Espectador ideal', perfil: 'Quem é', dores: 'Dores', desejos: 'Desejos', onde_esta: 'Onde está', como_chega: 'Como chega', categorias: 'Categorias', descricao: 'Descrição', exemplos: 'Exemplos',
  como_usar: 'Como usar', tipos: 'Tipos de canal', tipo: 'Tipo', observar: 'O que observar', lacunas: 'Lacunas de conteúdo', lacuna: 'Lacuna', ideia_central: 'Ideia central', termos: 'Termos',
  termo: 'Termo', significa: 'O que significa', como_agir: 'Como agir', estrategia_menos_de_100_inscritos: 'Estratégia para menos de 100 inscritos', frequencia: 'Frequência',
  testar_primeiro: 'Testar primeiro', como_ler_os_resultados: 'Como ler os resultados', de_espectador_a_inscrito: 'De espectador a inscrito', erros_comuns_de_canal_novo: 'Erros comuns de canal novo',
  meta: 'Meta', etapa: 'Etapa', quem: 'Quem faz', tempo_min: 'Tempo (min)', ferramenta: 'Ferramenta', saida: 'Resultado', tempo_por_semana_horas: 'Horas por semana',
  ferramentas_gratis_ou_baratas: 'Ferramentas grátis ou baratas', modelos: 'Modelos', regra_de_originalidade: 'Regra de originalidade', descricao_modelo: 'Descrição', comentario_fixado: 'Comentário fixado',
  por_faixa: 'Por faixa de inscritos', faixa: 'Faixa', foco: 'Foco', acoes: 'Ações', checklist_inscricao_ypp: 'Lista para o pedido ao Programa de Parcerias', semanal: 'Revisão semanal',
  mensal: 'Revisão mensal', quando: 'Quando', passos: 'Passos', metricas: 'Números', metrica: 'Número', bom_ou_ruim: 'O que é bom ou ruim', corrigir_primeiro: 'Corrigir primeiro',
  padroes_nos_melhores_videos: 'Padrões nos melhores vídeos', melhorar_os_3_piores: 'Melhorar os 3 piores', menos_de_1000_inscritos: 'Menos de 1.000 inscritos', '1000_a_10000': '1.000 a 10.000', acima_de_10000: 'Mais de 10.000',
  ideia: 'Ideia', titulos: 'Títulos', thumb: 'Miniatura (até 4 palavras)', gancho: 'Gancho (15 s)', motivo_clique: 'Motivo do clique', potencial: 'Potencial (0 a 100)', categoria: 'Categoria',
  video_n: 'Vídeo nº', duracao_min: 'Duração (min)', quebra_de_padrao_a_cada_s: 'Quebra de padrão a cada (s)', marcado: 'Roteiro marcado', pontos_de_saida: 'Pontos de saída', ponto: 'Ponto', risco: 'Risco', solucao: 'Solução',
  data: 'Data', como_foi_feito: 'Como foi feito', limites: 'Limites do estudo', achados: 'O que a busca mostrou', decisoes: 'O que mudou no plano', visualizacoes: 'Visualizações', leitura: 'Leitura', tema: 'Tema',
  juridico: 'Segurança jurídica', pessoas_vivas: 'Pessoas vivas (exigem fonte)', acusacoes: 'Termos de acusação', odio_grave: 'Estereótipos e ódio (proibido)', conspiracao: 'Linguagem de conspiração', certeza_indevida: 'Certeza sem fonte', aviso_editorial: 'Aviso editorial (entra em toda descrição)',
  ativo: 'Ligado', neutralidade: 'Neutralidade', palavras_de_campanha: 'Palavras de campanha', palavras_de_ataque: 'Palavras de ataque', politica: 'Política do canal',
  n: 'Nº', semana: 'Semana', tarefas: 'Tarefas', foco_da_semana: 'Foco', dia: 'Dia', videos: 'Vídeos', inscritos: 'Inscritos', horas: 'Horas', entrega: 'Entrega', piso: 'Mínimo', ctr: 'CTR', retencao: 'Retenção',
};
export const label = (k) => LABELS[k] || String(k).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const TITLE_KEYS = ['nome', 'titulo', 'tipo', 'termo', 'etapa', 'faixa', 'ideia', 'lacuna', 'metrica', 'ponto', 'foco', 'nicho', 'categoria', 'tema'];
const itemTitle = (it, i) => { for (const k of TITLE_KEYS) if (typeof it?.[k] === 'string' && it[k]) return it[k]; return `Item ${i + 1}`; };
const kind = (v) => (v === null || v === undefined ? 'str' : Array.isArray(v) ? 'list' : typeof v === 'object' ? 'obj' : typeof v === 'number' ? 'num' : typeof v === 'boolean' ? 'bool' : 'str');
const listKind = (a) => (!a.length || a.every((x) => typeof x === 'string' || typeof x === 'number') ? 'str' : a.every((x) => Array.isArray(x)) ? 'row' : 'obj');
const blankLike = (v) => (Array.isArray(v) ? [] : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, blankLike(x)])) : typeof v === 'number' ? 0 : typeof v === 'boolean' ? false : '');

/** Leitura: mostra qualquer estrutura de forma legível. */
export const PlanView = {
  name: 'PlanView',
  props: { value: null, name: { type: String, default: '' }, depth: { type: Number, default: 0 } },
  setup(props) {
    const k = computed(() => kind(props.value));
    const lk = computed(() => (k.value === 'list' ? listKind(props.value) : ''));
    return { k, lk, label, itemTitle, entries: computed(() => (k.value === 'obj' ? Object.entries(props.value) : [])) };
  },
  template: `
  <div class="pv" :class="'d' + Math.min(depth, 3)">
    <p v-if="k === 'str' || k === 'num' || k === 'bool'" class="pv-line"><b v-if="name">{{ label(name) }}: </b>{{ value === true ? 'sim' : value === false ? 'não' : value }}</p>
    <div v-else-if="k === 'list' && lk === 'str'"><b v-if="name" class="pv-h">{{ label(name) }}</b><ul><li v-for="(x, i) in value" :key="i">{{ x }}</li></ul></div>
    <div v-else-if="k === 'list' && lk === 'row'"><b v-if="name" class="pv-h">{{ label(name) }}</b><ol class="how"><li v-for="(r, i) in value" :key="i"><template v-for="(c, j) in r" :key="j"><b v-if="j === 0">{{ c }}</b><span v-else> · {{ c }}</span></template></li></ol></div>
    <div v-else-if="k === 'list'"><b v-if="name" class="pv-h">{{ label(name) }}</b>
      <details v-for="(it, i) in value" :key="i" class="pv-item"><summary>{{ itemTitle(it, i) }}</summary><plan-view :value="it" :depth="depth + 1"></plan-view></details></div>
    <div v-else-if="k === 'obj'"><b v-if="name && depth > 0" class="pv-h">{{ label(name) }}</b>
      <plan-view v-for="[kk, vv] in entries" :key="kk" :value="vv" :name="kk" :depth="depth + 1"></plan-view></div>
  </div>`,
};

/** Edição: um campo (texto, número, lista ou objeto) dentro de um contêiner; altera o contêiner no lugar. */
export const PlanField = {
  name: 'PlanField',
  props: { obj: null, k: null, lab: { type: String, default: '' } },
  setup(props) {
    const val = computed(() => props.obj[props.k]);
    const kd = computed(() => kind(val.value));
    const lk = computed(() => (kd.value === 'list' ? listKind(val.value) : ''));
    const name = computed(() => props.lab || label(props.k));
    const long = computed(() => typeof val.value === 'string' && (val.value.length > 70 || val.value.includes('\n')));
    const rows = computed(() => Math.min(14, Math.max(3, Math.ceil(String(val.value || '').length / 70) + 1)));
    const add = () => {
      const a = props.obj[props.k], f = a[0];
      a.push(f === undefined ? '' : Array.isArray(f) ? f.map(() => '') : blankLike(f));
    };
    const del = (i) => props.obj[props.k].splice(i, 1);
    const move = (i, d) => { const a = props.obj[props.k]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; };
    return { val, kd, lk, name, long, rows, add, del, move, itemTitle, keys: computed(() => (kd.value === 'obj' ? Object.keys(val.value) : [])), label };
  },
  template: `
  <div class="pf">
    <label v-if="kd === 'str'">{{ name }}<textarea v-if="long" :rows="rows" v-model="obj[k]"></textarea><input v-else v-model="obj[k]"></label>
    <label v-else-if="kd === 'num'">{{ name }}<input type="number" step="any" v-model.number="obj[k]"></label>
    <label v-else-if="kd === 'bool'" class="check"><input type="checkbox" v-model="obj[k]"> {{ name }}</label>
    <fieldset v-else-if="kd === 'obj'"><legend>{{ name }}</legend><plan-field v-for="kk in keys" :key="kk" :obj="val" :k="kk"></plan-field></fieldset>
    <fieldset v-else-if="kd === 'list'" class="plist"><legend>{{ name }} <small>({{ val.length }})</small></legend>
      <template v-if="lk === 'str'"><div v-for="(x, i) in val" :key="i" class="lrow"><input v-model="val[i]"><button type="button" class="mini" @click="move(i, -1)" aria-label="Subir">↑</button><button type="button" class="mini" @click="move(i, 1)" aria-label="Descer">↓</button><button type="button" class="mini danger" @click="del(i)" aria-label="Remover">✕</button></div></template>
      <template v-else-if="lk === 'row'"><div v-for="(r, i) in val" :key="i" class="lrow wrap"><input v-for="(c, j) in r" :key="j" v-model="r[j]"><button type="button" class="mini danger" @click="del(i)" aria-label="Remover">✕</button></div></template>
      <template v-else><details v-for="(it, i) in val" :key="i" class="pv-item"><summary>{{ itemTitle(it, i) }}</summary>
        <plan-field v-for="kk in Object.keys(it)" :key="kk" :obj="it" :k="kk"></plan-field>
        <div class="row-tight"><button type="button" class="mini" @click="move(i, -1)">↑ Subir</button><button type="button" class="mini" @click="move(i, 1)">↓ Descer</button><button type="button" class="mini danger" @click="del(i)">Remover este item</button></div></details></template>
      <button type="button" class="mini" @click="add">+ Adicionar</button>
    </fieldset>
  </div>`,
};

/** Cartão de uma seção do plano: lê, edita (formulário ou texto) e salva. */
export const SectionCard = {
  name: 'SectionCard',
  components: { PlanView, PlanField },
  props: { value: null, sectionKey: String, title: String, hint: { type: String, default: '' }, saver: Function, edited: { type: Boolean, default: false }, open: { type: Boolean, default: false } },
  setup(props) {
    const editing = ref(false); const holder = reactive({ v: null }); const raw = ref(''); const err = ref(''); const busy = ref(false);
    const start = () => { holder.v = JSON.parse(JSON.stringify(props.value ?? {})); raw.value = JSON.stringify(props.value ?? {}, null, 2); err.value = ''; editing.value = true; };
    const save = async (v) => { busy.value = true; err.value = ''; try { await props.saver(props.sectionKey, v); editing.value = false; } catch (e) { err.value = e.message; } finally { busy.value = false; } };
    const saveForm = () => save(holder.v);
    const saveRaw = () => { try { save(JSON.parse(raw.value)); } catch { err.value = 'O texto não é um JSON válido.'; } };
    return { editing, holder, raw, err, busy, start, saveForm, saveRaw };
  },
  template: `
  <section class="card seccard">
    <header class="sechead"><h2>{{ title }}</h2><span v-if="edited" class="badge">editado por você</span>
      <button type="button" @click="editing ? (editing = false) : start()">{{ editing ? 'Cancelar' : 'Editar' }}</button></header>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <template v-if="editing">
      <plan-field :obj="holder" k="v" lab=" "></plan-field>
      <p v-if="err" class="error-line" role="alert">{{ err }}</p>
      <div class="row-tight"><button class="primary" type="button" :disabled="busy" @click="saveForm">Salvar</button><button type="button" @click="editing = false">Cancelar</button></div>
      <details class="adv"><summary>Editar como texto (avançado)</summary><textarea rows="14" v-model="raw" spellcheck="false"></textarea><button type="button" :disabled="busy" @click="saveRaw">Salvar o texto</button></details>
    </template>
    <details v-else :open="open" class="secbody"><summary>Ver conteúdo</summary><plan-view :value="value"></plan-view></details>
  </section>`,
};

const MARKS = /\[(?:B-ROLL|TELA|SOM|QUEBRA|SAÍDA|TEASER)[^\]]*\]/g;
/** Só o texto falado de um roteiro marcado (igual ao que o servidor faz). */
export const cleanScript = (marked) => String(marked || '').replace(MARKS, '').split(/\n\s*\n/).map((p) => p.split(/\s+/).filter(Boolean).join(' ')).filter(Boolean).join('\n\n');
const nf = (n) => Math.round(n || 0).toLocaleString('pt-BR');
const IDEA_STATUS = { ideia: 'Só ideia', roteiro: 'Em roteiro', publicado: 'Publicada', descartada: 'Descartada' };

/** Banco de ideias ranqueado: filtro, paginação, roteiro de cada ideia (escrever com a IA, editar num modal) e atalho para criar o vídeo. */
export const IdeasList = {
  name: 'IdeasList',
  components: { Pager },
  props: { ideas: Array, categorias: Array, saver: Function, cid: String, api: Function, say: Function },
  emits: ['novo-video', 'changed'],
  setup(props, { emit }) {
    const cat = ref(''); const q = ref('');
    const catName = (id) => (props.categorias || []).find((c) => c.id === id)?.nome || id;
    const cats = computed(() => [...new Set((props.ideas || []).map((i) => i.categoria))]);
    const shown = computed(() => (props.ideas || []).filter((i) => (!cat.value || i.categoria === cat.value) && (!q.value || i.titulo.toLowerCase().includes(q.value.toLowerCase()))));
    const pg = usePager(shown, 10);
    watch([cat, q], () => pg.reset());
    const setStatus = (i, st) => props.saver('ideias', props.ideas.map((x) => (x.n === i.n ? { ...x, status: st } : x))).catch(() => {});
    const use = (i) => emit('novo-video', { titulo: i.titulo });
    const withScript = computed(() => (props.ideas || []).filter((i) => i.roteiro).length);

    // ---- escrever roteiros com a IA (fila na andes)
    const gen = reactive({ busy: false, msg: '', err: '', jobId: '', count: 5 });
    const waitJob = async (j) => {
      gen.jobId = j.id;
      for (let k = 0; k < 4000 && !['done', 'failed', 'cancelled'].includes(j.status); k++) {
        await new Promise((r) => setTimeout(r, 3000)); j = await props.api('/api/jobs/' + j.id);
        gen.msg = j.status === 'queued' ? 'Na fila da andes…' : (j.message || 'Escrevendo…');
        if (k % 10 === 9) emit('changed');
      }
      return j;
    };
    const writeScripts = async (body) => {
      if (gen.busy) return;
      gen.busy = true; gen.err = ''; gen.msg = 'Na fila da andes…';
      try {
        const j = await waitJob(await props.api(`/api/channels/${props.cid}/ideas/scripts`, { method: 'POST', body }));
        if (j.status === 'done') props.say(`Roteiro(s) pronto(s): ${(j.result?.feitos || []).length}${(j.result?.erros || []).length ? ', com erro: ' + j.result.erros.length : ''}`);
        else if (j.status === 'cancelled') props.say('Cancelado (os roteiros já prontos ficaram salvos)'); else gen.err = j.message || 'Não deu certo';
      } catch (e) { gen.err = e.message; } finally { gen.busy = false; gen.jobId = ''; emit('changed'); }
    };
    const writeOne = (i) => writeScripts({ ns: [i.n] });
    const writeNext = () => writeScripts({ count: gen.count });
    const cancelGen = async () => { try { await props.api(`/api/jobs/${gen.jobId}/cancel`, { method: 'POST' }); } catch { /* já terminou */ } };

    // ---- o que conferir antes de gerar o vídeo (por ideia)
    const chk = reactive({});
    const loadCheck = async (i) => {
      if (chk[i.n]) return;
      try { chk[i.n] = (await props.api(`/api/channels/${props.cid}/ideas/${i.n}/script`)).conferir; } catch { chk[i.n] = []; }
    };
    const toggleCheck = async (n, it, feito) => {
      try {
        const v = await props.api(`/api/channels/${props.cid}/ideas/${n}/conferir`, { method: 'POST', body: { id: it.id, feito } });
        chk[n] = v.conferir; if (ed.open && ed.n === n && ed.info) ed.info.conferir = v.conferir; emit('changed');
      } catch (e) { props.say(e.message); }
    };

    // ---- modal de edição do roteiro
    const ed = reactive({ open: false, n: null, titulo: '', text: '', info: null, loading: false, busy: false, err: '', dirty: false });
    const words = computed(() => cleanScript(ed.text).split(/\s+/).filter(Boolean).length);
    const openEdit = async (i) => {
      Object.assign(ed, { open: true, n: i.n, titulo: i.titulo, text: '', info: null, loading: true, err: '', dirty: false });
      try { const e = await props.api(`/api/channels/${props.cid}/ideas/${i.n}/script`); ed.text = e.marcado; ed.info = e; chk[i.n] = e.conferir; } catch (e) { ed.err = e.message; } finally { ed.loading = false; }
    };
    const closeEdit = () => { if (ed.dirty && !confirm('Há mudanças não salvas. Fechar mesmo assim?')) return; ed.open = false; };
    const saveEdit = async (revisado) => {
      ed.busy = true; ed.err = '';
      try { ed.info = await props.api(`/api/channels/${props.cid}/ideas/${ed.n}/script`, { method: 'PUT', body: { marcado: ed.text, revisado } }); ed.dirty = false; props.say('Roteiro salvo'); emit('changed'); }
      catch (e) { ed.err = e.message; } finally { ed.busy = false; }
    };
    const copyNarr = () => { try { navigator.clipboard.writeText(cleanScript(ed.text)); props.say('Narração copiada'); } catch { /* sem permissão */ } };
    const pend = computed(() => (ed.info?.conferir || []).filter((x) => !x.feito).length);
    const makeVideo = () => { if (pend.value && !confirm(`Ainda há ${pend.value} item(ns) para conferir antes de gerar o vídeo. Criar o vídeo mesmo assim?`)) return; const t = ed.titulo; const txt = cleanScript(ed.text); ed.open = false; emit('novo-video', { titulo: t, texto: txt }); };
    const onKey = (e) => { if (e.key === 'Escape') closeEdit(); };
    return { chk, loadCheck, toggleCheck, pend, cat, q, pg, catName, cats, shown, setStatus, use, IDEA_STATUS, withScript, gen, writeOne, writeNext, cancelGen, ed, words, openEdit, closeEdit, saveEdit, copyNarr, makeVideo, onKey, nf };
  },
  template: `
  <section class="card ideas">
    <h2>As {{ (ideas || []).length }} ideias, da melhor para a pior</h2>
    <p class="hint">O potencial (0 a 100) é um julgamento de procura, diferencial, vida útil e chance de virar série. Não é medição: confira com os seus números.</p>
    <div v-if="cid" class="card draftbox">
      <strong>Roteiros das ideias ({{ withScript }} de {{ (ideas || []).length }})</strong>
      <p class="hint">A andes escreve cada roteiro com o prompt de roteiro do playbook e o roteiro de referência do canal: gancho com laço aberto, fatos concretos, tensão entre as partes, marcações de B-roll, tela, som, quebra e saída, de 8 a 12 minutos. É rascunho: o modelo pode errar fatos, então confira cada afirmação em “Editar roteiro”. Leva alguns minutos por ideia.</p>
      <div class="row-tight"><label class="inline">Escrever as próximas<select v-model.number="gen.count" :disabled="gen.busy"><option :value="3">3</option><option :value="5">5</option><option :value="10">10</option></select> ideias sem roteiro (as de maior potencial)</label>
        <button type="button" class="primary" :disabled="gen.busy" @click="writeNext">{{ gen.busy ? 'Escrevendo…' : 'Escrever os roteiros' }}</button>
        <button v-if="gen.busy && gen.jobId" type="button" @click="cancelGen">Cancelar</button></div>
      <p v-if="gen.busy" class="muted" role="status">{{ gen.msg }}</p><p v-if="gen.err" class="error" role="alert">{{ gen.err }}</p>
    </div>
    <div class="chips" role="group" aria-label="Filtrar por categoria"><button type="button" :class="{ on: !cat }" @click="cat = ''">Todas</button>
      <button v-for="c in cats" :key="c" type="button" :class="{ on: cat === c }" @click="cat = c">{{ catName(c) }}</button></div>
    <label>Buscar<input v-model="q" placeholder="Ex.: alquimia"></label>
    <ol class="idl"><li v-for="i in pg.items" :key="i.n" class="idea" :class="i.status">
      <div class="itop"><span class="rank">#{{ i.n }}</span><span class="score" :title="'Potencial ' + i.potencial"><i :style="{ width: i.potencial + '%' }"></i></span><b>{{ i.potencial }}</b>
        <span class="tag">{{ catName(i.categoria) }}</span><span v-if="i.no_calendario" class="tag">no calendário</span>
        <span v-if="i.roteiro" class="tag" :class="{ warn: i.roteiro.rascunho }">{{ i.roteiro.rascunho ? 'roteiro: rascunho' : 'roteiro pronto' }} · {{ nf(i.roteiro.palavras) }} palavras</span>
        <span v-if="i.roteiro && i.roteiro.total" class="tag" :class="i.roteiro.pendentes ? 'warn' : 'okk'">{{ i.roteiro.pendentes ? 'conferir: ' + i.roteiro.pendentes + ' pendente(s)' : 'tudo conferido' }}</span></div>
      <p class="vtitle">{{ i.titulo }}</p><p class="hint">{{ i.motivo }}</p>
      <details v-if="i.roteiro && i.roteiro.total" class="conferir" @toggle="$event.target.open && loadCheck(i)">
        <summary><b>O que conferir antes de gerar o vídeo</b> ({{ i.roteiro.total - i.roteiro.pendentes }} de {{ i.roteiro.total }} conferidos)</summary>
        <ul class="chklist"><li v-for="it in (chk[i.n] || [])" :key="it.id"><label class="check"><input type="checkbox" :checked="it.feito" @change="toggleCheck(i.n, it, $event.target.checked)"> <span><small class="tag">{{ it.origem === 'regras' ? 'regras do canal' : 'pesquisa' }}</small> {{ it.texto }}</span></label></li></ul>
        <p v-if="!chk[i.n]" class="muted">Carregando…</p>
      </details>
      <div class="vact"><label class="inline">Situação<select :value="i.status" @change="setStatus(i, $event.target.value)"><option v-for="(t, k) in IDEA_STATUS" :key="k" :value="k">{{ t }}</option></select></label>
        <button v-if="cid && i.roteiro" type="button" class="primary" @click="openEdit(i)">Editar roteiro</button>
        <button v-else-if="cid" type="button" :disabled="gen.busy" @click="writeOne(i)">Escrever roteiro</button>
        <button type="button" @click="use(i)">Criar vídeo com este tema</button></div></li></ol>
    <pager :pg="pg" label="Páginas das ideias"></pager>
    <p v-if="!shown.length" class="muted">Nenhuma ideia neste filtro.</p>

    <div v-if="ed.open" class="modal" role="dialog" aria-modal="true" aria-labelledby="sc-t" @keydown="onKey">
      <div class="card editor scriptmodal">
        <button type="button" class="modal-x" aria-label="Fechar" title="Fechar" @click="closeEdit">✕</button>
        <h2 id="sc-t">Roteiro: {{ ed.titulo }}</h2>
        <p v-if="ed.loading" class="muted">Carregando…</p><p v-if="ed.err" class="error" role="alert">{{ ed.err }}</p>
        <template v-if="ed.info">
          <div v-if="ed.info.rascunho" class="card rulecheck draftinfo">
            <strong>📝 Rascunho da IA, ainda não revisado</strong>
            <p class="hint">Tese: {{ ed.info.rascunho.tese }}</p>
            <p v-if="(ed.info.rascunho.incertezas || []).length" class="hint"><b>Confira antes de gravar:</b> {{ ed.info.rascunho.incertezas.join(' · ') }}</p>
            <p v-if="(ed.info.rascunho.fontes || []).length" class="hint"><b>Fontes que o modelo disse conhecer (confirme que existem):</b> {{ ed.info.rascunho.fontes.join(' · ') }}</p>
          </div>
          <div v-if="ed.info.notas" class="card rulecheck draftinfo">
            <strong>🔎 {{ ed.info.notas.origem || 'Roteiro com pesquisa' }}</strong>
            <p class="hint">Tese: {{ ed.info.notas.tese }}</p>
            <details v-if="(ed.info.notas.fontes || []).length"><summary>Fontes ({{ ed.info.notas.fontes.length }})</summary><ul><li v-for="(x, k) in ed.info.notas.fontes" :key="k">{{ x }}</li></ul></details>
          </div>
          <div v-if="(ed.info.conferir || []).length" class="card rulecheck conferir-box">
            <strong>✅ O que conferir antes de gerar o vídeo ({{ ed.info.conferir.length - pend }} de {{ ed.info.conferir.length }})</strong>
            <ul class="chklist"><li v-for="it in ed.info.conferir" :key="it.id"><label class="check"><input type="checkbox" :checked="it.feito" @change="toggleCheck(ed.n, it, $event.target.checked)"> <span><small class="tag">{{ it.origem === 'regras' ? 'regras do canal' : 'pesquisa' }}</small> {{ it.texto }}</span></label></li></ul>
          </div>
          <label>Roteiro marcado (edite à vontade)
            <textarea rows="18" v-model="ed.text" spellcheck="true" :disabled="ed.busy" @input="ed.dirty = true"></textarea>
            <small class="hint">{{ nf(words) }} palavras de fala ≈ {{ (words / 125).toFixed(1) }} min (o canal pede de 8 a 12 e aceita até 30 quando o tema pede). Linhas como [B-ROLL: …], [TELA: …], [SOM: …], [QUEBRA: …], [TEASER] e [SAÍDA: risco | solução] são marcações de produção e não são narradas.</small></label>
          <ul v-if="(ed.info.achados || []).length && !ed.dirty" class="checks"><li v-for="(a, k) in ed.info.achados" :key="k" :class="'lv-' + a.nivel"><span>{{ a.nivel === 'ok' ? '✅' : a.nivel === 'erro' ? '⛔' : '⚠️' }}</span> {{ a.mensagem }}</li></ul>
          <p v-if="ed.dirty" class="hint">Salve para conferir de novo este texto nas regras do canal.</p>
        </template>
        <div class="actions">
          <button type="button" class="primary" :disabled="ed.busy || !ed.info || !ed.dirty" @click="saveEdit(false)">Salvar</button>
          <button v-if="ed.info && ed.info.rascunho" type="button" :disabled="ed.busy" @click="saveEdit(true)">Salvar e marcar como revisado</button>
          <button type="button" :disabled="!ed.info" @click="copyNarr">Copiar a narração</button>
          <button type="button" :disabled="!ed.info || ed.dirty" @click="makeVideo">Criar vídeo com esta narração</button>
          <button type="button" @click="closeEdit">Fechar</button>
        </div>
      </div>
    </div>
  </section>`,
};

/** Roteiros marcados: lê, edita, copia a narração limpa e cria o vídeo no MisterClip com ela. */
export const ScriptsView = {
  name: 'ScriptsView',
  components: { Pager },
  props: { roteiros: Array, saver: Function, say: Function, videos: Array, cid: String, api: Function },
  emits: ['novo-video', 'changed'],
  setup(props, { emit }) {
    const pgR = usePager(computed(() => props.roteiros || []), 10);
    const pick = ref(''); const busy = ref(''); const derr = ref('');
    const candidates = computed(() => (props.videos || []).filter((v) => { const r = (props.roteiros || []).find((x) => x.video_n === v.n); return !r || r.rascunho; }));
    const writeDraft = async () => {
      if (!pick.value || busy.value) return;
      derr.value = ''; busy.value = 'Na fila da andes…';
      try {
        let j = await props.api(`/api/channels/${props.cid}/videos/${pick.value}/draft`, { method: 'POST', body: {} });
        for (let i = 0; i < 1500 && !['done', 'failed', 'cancelled'].includes(j.status); i++) {
          await new Promise((r) => setTimeout(r, 2000)); j = await props.api('/api/jobs/' + j.id);
          busy.value = j.status === 'queued' ? 'Na fila da andes…' : (j.message || 'Escrevendo…');
        }
        if (j.status === 'done') { props.say('Rascunho pronto: confira os fatos antes de usar'); open.value = Number(pick.value); emit('changed'); } else derr.value = j.message || 'Não deu certo';
      } catch (e) { derr.value = e.message; } finally { busy.value = ''; }
    };
    const approve = (r) => props.saver('roteiros', props.roteiros.map((x) => (x.video_n === r.video_n ? Object.fromEntries(Object.entries(x).filter(([k]) => k !== 'rascunho')) : x))).then(() => emit('changed')).catch(() => {});
    const open = ref(null); const mode = ref('limpa'); const draft = ref(''); const editing = ref(false);
    const words = (r) => cleanScript(r.marcado).split(/\s+/).filter(Boolean).length;
    const clean = (r) => cleanScript(r.marcado);
    const startEdit = (r) => { draft.value = r.marcado; editing.value = true; };
    const save = async (r) => { await props.saver('roteiros', props.roteiros.map((x) => (x === r || x.video_n === r.video_n ? { ...x, marcado: draft.value } : x))); editing.value = false; };
    const copy = (r) => { try { navigator.clipboard.writeText(clean(r)); props.say('Narração copiada'); } catch { /* sem permissão */ } };
    const make = (r) => emit('novo-video', { titulo: r.titulo, texto: clean(r), plan_item: r.video_n });
    return { pgR, open, mode, draft, editing, words, clean, startEdit, save, copy, make, nf, pick, busy, derr, candidates, writeDraft, approve };
  },
  template: `
  <section class="card scripts">
    <h2>Roteiros prontos</h2>
    <p class="hint">O roteiro marcado mostra onde entram B-roll, texto na tela, som, quebras de ritmo, o teaser e os pontos de saída. A narração limpa é só o texto falado: é ela que vai para o MisterClip.</p>
    <div v-if="cid && (videos || []).length" class="card draftbox">
      <strong>Rascunho de roteiro com a IA</strong>
      <p class="hint">Escolha um vídeo do calendário. A andes escreve um rascunho dentro das regras do canal (esboço, seções, fontes e números por extenso) em alguns minutos. É só um começo: o texto pode conter erros de fato. Você revisa, confere cada afirmação e edita antes de virar vídeo. Um roteiro seu nunca é trocado.</p>
      <div class="row-tight"><label class="inline">Vídeo<select v-model="pick" :disabled="!!busy"><option value="">escolha…</option><option v-for="v in candidates" :key="v.n" :value="v.n">{{ v.n }}. {{ v.titulo }}</option></select></label>
        <button type="button" class="primary" :disabled="!pick || !!busy" @click="writeDraft">{{ busy ? 'Escrevendo…' : 'Escrever o rascunho' }}</button></div>
      <p v-if="busy" class="muted" role="status">{{ busy }}</p><p v-if="derr" class="error" role="alert">{{ derr }}</p>
    </div>
    <p v-if="!(roteiros || []).length" class="muted">Nenhum roteiro ainda. Peça ao Claude para executar o prompt “Roteirize vídeos que as pessoas assistem até o fim”.</p>
    <article v-for="r in pgR.items" :key="r.video_n" class="script">
      <header><button type="button" class="linkbtn" @click="open = open === r.video_n ? null : r.video_n">{{ open === r.video_n ? '▾' : '▸' }} <b>{{ r.titulo }}</b></button><span v-if="r.rascunho" class="tag warn">rascunho</span>
        <span class="muted">{{ nf(words(r)) }} palavras · ~{{ Math.round(words(r) / 125) }} min · quebra a cada {{ r.quebra_de_padrao_a_cada_s }} s</span></header>
      <div v-if="open === r.video_n">
        <div v-if="r.rascunho" class="card rulecheck draftinfo">
          <strong>📝 Rascunho da IA, ainda não revisado</strong>
          <p class="hint">Tese: {{ r.rascunho.tese }}</p>
          <ul v-if="(r.rascunho.avisos || []).length" class="checks"><li v-for="(a, i) in r.rascunho.avisos" :key="i" :class="'lv-' + a.nivel"><span>{{ a.nivel === 'erro' ? '⛔' : '⚠️' }}</span> {{ a.mensagem }}</li></ul>
          <p v-if="(r.rascunho.incertezas || []).length" class="hint"><b>Confira antes de gravar:</b></p>
          <ul v-if="(r.rascunho.incertezas || []).length"><li v-for="(x, i) in r.rascunho.incertezas" :key="i">{{ x }}</li></ul>
          <p v-if="(r.rascunho.fontes || []).length" class="hint"><b>Fontes que o modelo disse conhecer (confirme que existem):</b> {{ r.rascunho.fontes.join(' · ') }}</p>
          <button type="button" @click="approve(r)">Já revisei: tirar a marca de rascunho</button>
        </div>
        <div class="row-tight"><button type="button" :class="{ on: mode === 'limpa' }" @click="mode = 'limpa'">Narração limpa</button><button type="button" :class="{ on: mode === 'marcado' }" @click="mode = 'marcado'">Roteiro marcado</button>
          <button type="button" @click="copy(r)">Copiar a narração</button><button type="button" class="primary" @click="make(r)">Criar vídeo com esta narração</button></div>
        <template v-if="mode === 'limpa'"><pre class="final">{{ clean(r) }}</pre></template>
        <template v-else>
          <template v-if="editing"><textarea rows="22" v-model="draft"></textarea><div class="row-tight"><button class="primary" type="button" @click="save(r)">Salvar roteiro</button><button type="button" @click="editing = false">Cancelar</button></div></template>
          <template v-else><pre class="final marked">{{ r.marcado }}</pre><button type="button" @click="startEdit(r)">Editar o roteiro</button></template>
        </template>
        <h3>Onde o espectador pode sair, e como foi resolvido</h3>
        <ul><li v-for="(p, i) in r.pontos_de_saida" :key="i"><b>{{ p.ponto }}.</b> Risco: {{ p.risco }} Solução: {{ p.solucao }}</li></ul>
      </div>
    </article>
    <pager :pg="pgR" label="Páginas dos roteiros"></pager>
  </section>`,
};
