/** Telas de canais: lista de canais e, dentro de cada canal, Resumo, Calendário, Plano, Métricas e Roteiro. */
import { ref, reactive, computed, watch, onMounted } from './vendor/vue.esm-browser.prod.js';
import { SectionCard, IdeasList, ScriptsView } from './plano.js';
import { usePager, Pager } from './pager.js';
import { YoutubeView } from './youtube.js';

export const CHAN_TABS = [['resumo', 'Resumo'], ['calendario', 'Calendário'], ['shorts', 'Shorts'], ['plano', 'Plano'], ['ideias', 'Ideias'], ['operacao', 'Operação'], ['youtube', 'YouTube'], ['metricas', 'Métricas'], ['roteiro', 'Roteiro e lista']];
const SITUACAO = { planejado: 'Planejado', roteiro: 'Roteiro em andamento', produzindo: 'Em produção', pronto: 'Vídeo pronto', publicado: 'Publicado' };
const PILAR = { tradicoes: 'Tradições e mestres', arcanos: 'Os 22 Arcanos', futuro: 'Futuro e consciência' };
const FORMATO = { ensaio: 'Ensaio 8–12 min', longo: 'Aprofundamento 18–22 min', shorts: 'Shorts' };
const DIA = { ter: 'terça', sex: 'sexta' };
const SHORT_STATUS = { ideia: 'Só ideia', agendado: 'Agendado', gravado: 'Pronto', publicado: 'Publicado' };
const OFFSETS = [[0, 'No dia do vídeo'], [1, '1 dia depois'], [2, '2 dias depois'], [3, '3 dias depois'], [4, '4 dias depois'], [5, '5 dias depois'], [6, '6 dias depois'], [7, '7 dias depois']];
const nf = (n) => Math.round(n || 0).toLocaleString('pt-BR');
const nf1 = (n) => Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
const pct = (a, b) => Math.max(0, Math.min(100, b ? Math.round((a / b) * 100) : 0));
const fdate = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
const fday = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sem armazenamento: segue sem lembrar */ } },
};

export const CanaisView = {
  components: { Pager },
  props: { api: Function, say: Function },
  setup(props) {
    const list = ref([]); const loading = ref(true); const err = ref('');
    const pgL = usePager(list, 10);
    const nova = reactive({ open: false, name: '', niche: '', template: 'ocultismo-tecnologia-90d', start_date: '' });
    const templates = ref([]);
    onMounted(async () => { try { templates.value = await props.api('/api/channel-templates'); } catch {} });
    const load = async () => { try { list.value = await props.api('/api/channels'); } catch (e) { err.value = e.message; } loading.value = false; };
    const create = async () => {
      err.value = '';
      try {
        const c = await props.api('/api/channels', { method: 'POST', body: { name: nova.name, niche: nova.niche, template: nova.template, start_date: nova.start_date || null } });
        props.say('Canal criado'); location.hash = '#/canal/' + c.id;
      } catch (e) { err.value = e.message; }
    };
    onMounted(load);
    return { pgL, list, loading, err, nova, templates, create, nf, fday };
  },
  template: `
  <section>
    <div class="row"><h1>Canais</h1><button class="btn primary" type="button" @click="nova.open = !nova.open">{{ nova.open ? 'Fechar' : '+ Novo canal' }}</button></div>
    <p class="lead">Cada canal tem o seu plano, calendário e números. Os vídeos de cada canal ficam separados. <a href="#/prompts">Modelos de prompt</a> para planejar um canal novo.</p>
    <p v-if="err" class="error-line" role="alert">{{ err }}</p>
    <form v-if="nova.open" class="card chan-new" @submit.prevent="create">
      <label>Nome do canal<input v-model="nova.name" maxlength="80" placeholder="Ex.: Arcano Digital" required></label>
      <label>Assunto do canal<input v-model="nova.niche" maxlength="200" placeholder="Ex.: filosofia, ocultismo e tecnologia"></label>
      <label>Ponto de partida
        <select v-model="nova.template"><option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option></select>
        <small class="hint">{{ (templates.find((t) => t.id === nova.template) || {}).description }} Tudo pode ser editado depois. Para criar um canal a partir de outro, abra o canal e use “Duplicar este canal”.</small></label>
      <label>Primeiro dia do plano<input type="date" v-model="nova.start_date"><small class="hint">Deixe em branco para começar na próxima segunda-feira.</small></label>
      <button class="primary" type="submit">Criar canal</button>
    </form>
    <p v-if="loading" class="muted">Carregando…</p>
    <div class="list">
      <a v-for="c in pgL.items" :key="c.id" class="card item" :href="'#/canal/' + c.id">
        <div class="itext"><strong>{{ c.name }}</strong>
          <span class="muted">{{ c.niche || 'Sem assunto definido' }}</span>
          <span class="muted">{{ c.projetos }} {{ c.projetos === 1 ? 'vídeo' : 'vídeos' }} no MisterClip<template v-if="c.tem_plano"> · {{ c.videos_publicados }} de {{ c.videos_total }} do calendário publicados</template></span></div>
        <span class="stack"><span class="badge" v-if="c.tem_plano">{{ c.dia >= 1 ? 'Dia ' + c.dia + ' de 90' : 'Começa em ' + fday(c.start_date) }}</span>
          <span class="badge">{{ nf(c.horas) }} h · {{ nf(c.inscritos) }} inscritos</span></span>
      </a>
    </div>
    <pager :pg="pgL" label="Páginas dos canais"></pager>
  </section>`,
};

export const CanalView = {
  components: { SectionCard, IdeasList, ScriptsView, YoutubeView, Pager },
  props: { id: String, tab: String, api: Function, say: Function },
  emits: ['novo-video'],
  setup(props, { emit }) {
    const ch = ref(null); const err = ref(''); const loading = ref(true);
    const ed = reactive({ open: false, name: '', niche: '', start_date: '' });
    const mf = reactive({ day: new Date().toISOString().slice(0, 10), subs: '', hours: '', views: '', ctr: '', avd: '', note: '' });
    const calc = reactive({ views: 2000, avd: 5, rpm: 8 });
    const checks = reactive({}); const pubChecks = reactive({});
    const editing = ref(null);
    const sc = reactive({ views: 20000, conv: 0.5, avd: 5, subs: 3, openN: null, busy: {} });
    const guard = async (fn) => { err.value = ''; try { return await fn(); } catch (e) { err.value = e.message; } };

    const load = () => guard(async () => {
      ch.value = await props.api('/api/channels/' + props.id); loading.value = false; document.title = ch.value.name + ' · MisterClip';
      Object.assign(checks, store.get('mc_chk_' + props.id, {})); Object.assign(pubChecks, store.get('mc_pub_' + props.id, {}));
    });
    onMounted(load);
    watch(() => props.id, load);
    const toggle = (bag, key, name) => { bag[key] = !bag[key]; store.set(name + props.id, { ...bag }); };

    const h = computed(() => ch.value?.hoje || {});
    const plan = computed(() => ch.value?.plan || {});
    const hasPlan = computed(() => (ch.value?.videos || []).length > 0);
    const weeks = computed(() => {
      const byWeek = {};
      for (const v of ch.value?.videos || []) (byWeek[v.semana] ||= []).push(v);
      const info = Object.fromEntries((plan.value.semanas || []).map((s) => [s.n, s]));
      return Object.keys(byWeek).map(Number).sort((a, b) => a - b).map((n) => ({ n, foco: info[n]?.foco || '', tarefas: info[n]?.tarefas || [], videos: byWeek[n], atual: n === h.value.semana }));
    });
    const thisWeek = computed(() => weeks.value.find((w) => w.atual) || null);
    const nextVideo = computed(() => (ch.value?.videos || []).find((v) => v.status === 'planejado' || v.status === 'roteiro') || null);
    const horasPct = computed(() => pct(h.value.horas, 4000));
    const subsPct = computed(() => pct(h.value.inscritos, 1000));
    const ritmo = computed(() => {
      if (!h.value.meta_horas) return null;
      if (h.value.horas >= h.value.meta_horas) return ['ok', 'No ritmo ou à frente da meta'];
      if (h.value.horas >= h.value.piso_horas) return ['warn', 'Abaixo da meta, acima do mínimo aceitável'];
      return ['bad', 'Abaixo do mínimo aceitável para esta semana'];
    });

    // ----- gráfico de horas: meta, mínimo e o que já aconteceu
    const chart = computed(() => {
      const c = plan.value.curva; if (!c || !c.horas || !ch.value) return null;
      const W = 640, H = 250, L = 46, R = 14, T = 14, B = 30;
      const start = new Date(ch.value.start_date + 'T12:00:00');
      const wk = (iso) => (new Date(iso + 'T12:00:00') - start) / 86400000 / 7;
      const maxY = Math.max(5000, ...ch.value.metricas.map((m) => m.hours));
      const X = (w) => L + (w / 13) * (W - L - R); const Y = (v) => H - B - (v / maxY) * (H - T - B);
      const line = (vals, f = 1) => [`${X(0)},${Y(0)}`, ...vals.map((v, i) => `${X(i + 1)},${Y(v * f)}`)].join(' ');
      const feb = wk('2027-02-01');
      return { W, H, L, B, goal: line(c.horas), floor: line(c.horas, c.piso), y4000: Y(4000), yMax: Y(maxY), maxY, xFeb: feb >= 0 && feb <= 13 ? X(feb) : null, X, Y,
        pts: ch.value.metricas.map((m) => ({ x: X(Math.max(0, Math.min(13, wk(m.day)))), y: Y(m.hours), t: fday(m.day) + ': ' + nf(m.hours) + ' h' })),
        ticks: [0, 1000, 2000, 3000, 4000, 5000].filter((t) => t <= maxY).map((t) => ({ t, y: Y(t) })) };
    });
    const calcHours = computed(() => (calc.views * calc.avd) / 60);
    const calcViews = computed(() => (calc.rpm > 0 ? Math.round(1000 / (calc.rpm / 1000)) : 0));

    // ----- Shorts
    const sp = computed(() => plan.value.shorts_plano || null);
    const shortWeeks = computed(() => {
      const g = {};
      for (const x of ch.value?.shorts_cal || []) (g[x.semana] ||= []).push(x);
      return Object.keys(g).map(Number).sort((a, b) => a - b).map((n) => ({ n, items: g[n] }));
    });
    const calcShortHours = computed(() => (sc.views * (sc.conv / 100) * sc.avd) / 60);
    const calcShortSubs = computed(() => (sc.views / 1000) * sc.subs);
    const patchShort = (v, s, body) => guard(async () => { ch.value = await props.api(`/api/channels/${props.id}/videos/${v}/shorts/${s}`, { method: 'PATCH', body }); });
    const videoOf = (n) => (ch.value?.videos || []).find((x) => x.n === n);
    const genIdeas = (v) => guard(async () => {
      sc.busy[v.n] = 'Escrevendo as ideias a partir do roteiro…';
      try {
        let j = await props.api(`/api/channels/${props.id}/videos/${v.n}/shorts/generate`, { method: 'POST' });
        for (let i = 0; i < 400 && j.status !== 'done' && j.status !== 'failed'; i++) {
          await new Promise((r) => setTimeout(r, 1500)); j = await props.api('/api/jobs/' + j.id);
          sc.busy[v.n] = j.status === 'queued' ? 'Na fila da andes…' : (j.message || 'Escrevendo…');
        }
        if (j.status === 'failed') throw new Error(j.message || 'não foi possível gerar as ideias');
        await load(); props.say(j.result && j.result.ideias === 0 ? 'A andes não trouxe ideias novas desta vez; ficaram as ideias-base.' : 'Ideias prontas');
      } finally { delete sc.busy[v.n]; }
    });
    const shortLabel = (n) => { const v = videoOf(n); return v ? (v.serie ? v.serie : v.titulo) : ''; };

    // ----- plano editável, duplicar e modelo
    const saveSection = async (key, value) => {
      ch.value = await props.api(`/api/channels/${props.id}/plan/${key}`, { method: 'PUT', body: { value } });
      props.say('Salvo');
    };
    const isEdited = (k) => (plan.value._edited || []).includes(k);
    const cloneChannel = () => {
      const name = prompt('Nome do novo canal. A cópia leva o plano, o calendário e as ideias; não leva vídeos nem números.', ch.value.name + ' 2');
      if (!name || !name.trim()) return;
      return guard(async () => { const c = await props.api(`/api/channels/${props.id}/clone`, { method: 'POST', body: { name } }); props.say('Canal duplicado'); location.hash = '#/canal/' + c.id; });
    };
    const saveTemplate = () => {
      const name = prompt('Nome do modelo (aparece em Canais > Novo canal):', ch.value.name);
      if (!name || !name.trim()) return;
      return guard(async () => { await props.api(`/api/channels/${props.id}/save-template`, { method: 'POST', body: { name } }); props.say('Modelo salvo: já aparece ao criar um canal'); });
    };
    const novoVideo = (ctx) => emit('novo-video', { channel_id: props.id, ...ctx });

    // ----- ações
    const patch = (n, body) => guard(async () => { ch.value = await props.api(`/api/channels/${props.id}/videos/${n}`, { method: 'PATCH', body }); });
    const saveTitle = async (v, titulo) => { editing.value = null; if (titulo && titulo !== v.titulo) await patch(v.n, { titulo }); };
    const startVideo = (v) => emit('novo-video', { channel_id: props.id, plan_item: v.n, titulo: v.titulo });
    const removeVideo = (v) => confirm('Tirar este vídeo do calendário? O vídeo já criado no MisterClip, se houver, não é apagado.') && guard(async () => { ch.value = await props.api(`/api/channels/${props.id}/videos/${v.n}`, { method: 'DELETE' }); });
    const openEdit = () => { Object.assign(ed, { open: !ed.open, name: ch.value.name, niche: ch.value.niche, start_date: ch.value.start_date }); };
    const saveEdit = () => guard(async () => { ch.value = await props.api('/api/channels/' + props.id, { method: 'PUT', body: { name: ed.name, niche: ed.niche, start_date: ed.start_date } }); ed.open = false; document.title = ch.value.name + ' · MisterClip'; props.say('Salvo'); });
    const removeChannel = () => confirm('Apagar este canal? Só é possível se ele não tiver vídeos.') && guard(async () => { await props.api('/api/channels/' + props.id, { method: 'DELETE' }); location.hash = '#/canais'; });
    const addMetric = () => guard(async () => {
      const num = (x) => (x === '' || x === null ? null : Number(String(x).replace(',', '.')));
      await props.api(`/api/channels/${props.id}/metrics`, { method: 'POST', body: { day: mf.day, subs: Math.round(num(mf.subs) ?? 0), hours: num(mf.hours) ?? 0, views: Math.round(num(mf.views) ?? 0), ctr: num(mf.ctr), avd: num(mf.avd), note: mf.note } });
      Object.assign(mf, { subs: '', hours: '', views: '', ctr: '', avd: '', note: '' }); props.say('Números registrados'); await load();
    });
    const delMetric = (m) => confirm('Apagar este registro?') && guard(async () => { await props.api(`/api/channels/${props.id}/metrics/${m.id}`, { method: 'DELETE' }); await load(); });
    const metricsDesc = computed(() => [...(ch.value?.metricas || [])].reverse());
    const pgM = usePager(metricsDesc, 10);
    const pgW = usePager(weeks, 4);
    const pgS = usePager(shortWeeks, 4);
    const pgV = usePager(computed(() => ch.value?.videos || []), 10);
    const clearPub = () => { Object.keys(pubChecks).forEach((k) => delete pubChecks[k]); store.set('mc_pub_' + props.id, {}); };
    const copyText = (t) => { try { navigator.clipboard.writeText(t); props.say('Copiado'); } catch { /* sem permissão */ } };

    return { load, pgM, pgW, pgS, pgV, saveSection, isEdited, cloneChannel, saveTemplate, novoVideo, ch, err, loading, ed, mf, calc, checks, pubChecks, editing, h, plan, hasPlan, weeks, thisWeek, nextVideo, horasPct, subsPct, ritmo, chart, calcHours, calcViews, metricsDesc,
      sc, sp, shortWeeks, calcShortHours, calcShortSubs, patchShort, genIdeas, shortLabel, SHORT_STATUS, OFFSETS,
      toggle, patch, saveTitle, startVideo, removeVideo, openEdit, saveEdit, removeChannel, addMetric, delMetric, copyText, clearPub,
      SITUACAO, PILAR, FORMATO, DIA, CHAN_TABS, nf, nf1, pct, fdate, fday };
  },
  template: `
  <section class="canal" v-if="ch">
    <a class="back" href="#/canais">← Canais</a>
    <div class="row"><h1>{{ ch.name }}</h1><button type="button" @click="openEdit">{{ ed.open ? 'Fechar' : 'Editar canal' }}</button></div>
    <p class="muted">{{ ch.niche || 'Sem assunto definido' }}</p>
    <form v-if="ed.open" class="card" @submit.prevent="saveEdit">
      <label>Nome do canal<input v-model="ed.name" maxlength="80" required></label>
      <label>Assunto do canal<input v-model="ed.niche" maxlength="200"></label>
      <label>Primeiro dia do plano<input type="date" v-model="ed.start_date"><small class="hint">Muda as datas de todo o calendário e dos marcos.</small></label>
      <div class="row-tight"><button class="primary" type="submit">Salvar</button><button type="button" @click="cloneChannel">Duplicar este canal</button><button type="button" @click="saveTemplate">Salvar como modelo</button><button type="button" class="danger" @click="removeChannel">Apagar canal</button></div>
      <p class="hint">Duplicar cria outro canal com o mesmo planejamento (para editar à vontade). Salvar como modelo guarda esta estrutura para usar ao criar canais novos.</p>
    </form>
    <p v-if="err" class="error-line" role="alert">{{ err }}</p>

    <nav class="ctabs" aria-label="Seções do canal">
      <a v-for="t in CHAN_TABS" :key="t[0]" :href="'#/canal/' + id + '/' + t[0]" :aria-current="tab === t[0] ? 'page' : null">{{ t[1] }}</a>
    </nav>

    <p v-if="!hasPlan && tab !== 'metricas'" class="card muted">Este canal está em branco, sem plano nem calendário. Use a aba Métricas para acompanhar os números, ou crie um canal com o plano de 90 dias.</p>

    <!-- ===================== RESUMO ===================== -->
    <div v-if="tab === 'resumo' && hasPlan" class="cgrid">
      <div class="card hero">
        <p class="eyebrow">Onde você está</p>
        <h2 v-if="h.dia >= 1 && !h.fim_do_plano">Dia {{ h.dia }} de 90 · Semana {{ h.semana }} de 13</h2>
        <h2 v-else-if="h.fim_do_plano">Os 90 dias terminaram</h2>
        <h2 v-else>O plano começa em {{ h.comeca_em }} {{ h.comeca_em === 1 ? 'dia' : 'dias' }} ({{ fday(ch.start_date) }})</h2>
        <p class="muted">{{ h.videos_publicados }} de {{ h.videos_total }} vídeos publicados · {{ h.videos_previstos_ate_hoje }} previstos até hoje</p>
      </div>

      <div class="card">
        <strong>Rumo ao Programa de Parcerias do YouTube</strong>
        <div class="goalrow"><span>Horas de exibição</span><b>{{ nf(h.horas) }} de 4.000</b></div>
        <div class="bar"><div :style="{ width: horasPct + '%' }"></div></div>
        <div class="goalrow"><span>Inscritos</span><b>{{ nf(h.inscritos) }} de 1.000</b></div>
        <div class="bar"><div :style="{ width: subsPct + '%' }"></div></div>
        <p v-if="ritmo" class="pace" :class="ritmo[0]">{{ ritmo[1] }}. Para hoje: meta de {{ nf(h.meta_horas) }} h e {{ nf(h.meta_inscritos) }} inscritos (mínimo {{ nf(h.piso_horas) }} h e {{ nf(h.piso_inscritos) }}).</p>
        <p v-if="h.ypp_ok" class="pace ok">Você já passou dos dois números. Confira no YouTube Studio e envie o pedido de monetização.</p>
        <p v-else-if="h.antes_das_novas_regras" class="hint">Faltam <b>{{ h.dias_ate_31jan }}</b> dias para 31/01/2027. Depois dessa data, quem ainda não entrou no programa precisa de <b>8.000 horas</b>. Detalhes na aba Plano.</p>
        <p v-else class="hint">As novas regras já valem: a meta agora é de <b>8.000 horas</b> em 365 dias. Detalhes na aba Plano.</p>
        <p v-if="ch.projecao.horas_31jan !== null" class="hint">No ritmo recente ({{ nf1(ch.projecao.ritmo_dia) }} h por dia): cerca de {{ nf(ch.projecao.horas_31jan) }} h em 31/01<template v-if="ch.projecao.data_4000">; 4.000 h por volta de {{ fday(ch.projecao.data_4000) }}</template>.</p>
        <p v-else class="hint">Registre os números na aba Métricas em duas datas diferentes para ver a projeção.</p>
      </div>

      <div v-if="nextVideo" class="card">
        <strong>Próximo vídeo</strong>
        <p class="muted">{{ fdate(nextVideo.data) }} · {{ nextVideo.serie || PILAR[nextVideo.pilar] }}</p>
        <p class="vtitle">{{ nextVideo.titulo }}</p>
        <div class="row-tight">
          <a v-if="nextVideo.projeto" class="btn primary" :href="'#/p/' + nextVideo.projeto.id">Abrir o vídeo</a>
          <button v-else class="primary" type="button" @click="startVideo(nextVideo)">Criar este vídeo</button>
          <a class="btn" :href="'#/canal/' + id + '/calendario'">Ver calendário</a></div>
      </div>

      <div v-if="thisWeek" class="card">
        <strong>Esta semana: {{ thisWeek.foco }}</strong>
        <ul class="tasks">
          <li v-for="(t, i) in thisWeek.tarefas" :key="i"><label class="check"><input type="checkbox" :checked="!!checks['s' + thisWeek.n + '_' + i]" @change="toggle(checks, 's' + thisWeek.n + '_' + i, 'mc_chk_')"> <span>{{ t }}</span></label></li>
        </ul>
      </div>

      <div class="card wide2">
        <strong>Marcos do plano</strong>
        <div class="marcos">
          <div v-for="m in ch.marcos" :key="m.dia" class="marco" :class="{ ok: h.horas >= m.horas && h.inscritos >= m.inscritos }">
            <h3>{{ m.titulo }} <small>{{ fday(m.data) }}</small></h3>
            <p class="muted">{{ m.dias_restantes > 0 ? 'Faltam ' + m.dias_restantes + ' dias' : m.dias_restantes === 0 ? 'É hoje' : 'Já passou' }}</p>
            <ul class="mlist">
              <li><b>{{ m.videos }}</b> vídeos no ar</li>
              <li><b>{{ nf(m.horas) }}</b> horas (mínimo {{ nf(m.piso.horas) }})</li>
              <li><b>{{ nf(m.inscritos) }}</b> inscritos (mínimo {{ nf(m.piso.inscritos) }})</li>
              <li>{{ m.ctr }}; {{ m.retencao }}</li>
            </ul>
            <p class="hint">{{ m.entrega }}</p>
            <p class="hint">Você está em: {{ nf(m.atual.horas) }} h · {{ nf(m.atual.inscritos) }} inscritos · {{ m.atual.videos }} vídeos publicados</p>
          </div>
        </div>
        <p class="hint">São metas de planejamento, não promessas. O resultado de um canal novo depende muito de acertar tema, miniatura e retenção.</p>
      </div>

      <div class="card wide2" v-if="plan.cenarios">
        <strong>O que esperar, com honestidade</strong>
        <div class="marcos"><div v-for="c in plan.cenarios" :key="c.nome" class="marco"><h3>{{ c.nome }}</h3><p>{{ c.texto }}</p></div></div>
      </div>
    </div>

    <!-- ===================== CALENDÁRIO ===================== -->
    <div v-if="tab === 'calendario' && hasPlan" class="cal-weeks">
      <p class="lead">Dois vídeos por semana (terça e sexta). Toque em “Criar este vídeo” para abrir o formulário já com o tema. Quando o vídeo estiver no ar no YouTube, marque como “Publicado”.</p>
      <article v-for="w in pgW.items" :key="w.n" class="card week" :class="{ now: w.atual }">
        <header><h2>Semana {{ w.n }} <small>{{ w.foco }}</small></h2><span v-if="w.atual" class="badge">esta semana</span></header>
        <ul class="vlist">
          <li v-for="v in w.videos" :key="v.n" class="vrow" :class="v.status_auto">
            <div class="vtop"><span class="vdate">{{ fdate(v.data) }}</span>
              <span class="tag">{{ v.serie || PILAR[v.pilar] }}</span><span class="tag">{{ FORMATO[v.formato] || v.formato }}</span></div>
            <div v-if="editing === v.n" class="row-tight"><input :value="v.titulo" maxlength="150" @keyup.enter="saveTitle(v, $event.target.value)" @blur="saveTitle(v, $event.target.value)" autofocus></div>
            <p v-else class="vtitle" @dblclick="editing = v.n">{{ v.titulo }}</p>
            <div class="vact">
              <label class="inline">Situação
                <select :value="v.status" @change="patch(v.n, { status: $event.target.value })"><option v-for="(t, k) in SITUACAO" :key="k" :value="k">{{ t }}</option></select></label>
              <span v-if="v.status_auto !== v.status" class="hint">o vídeo ligado a este item está {{ SITUACAO[v.status_auto].toLowerCase() }}</span>
              <a v-if="v.projeto" class="btn" :href="'#/p/' + v.projeto.id">Abrir vídeo</a>
              <button v-else type="button" class="primary" @click="startVideo(v)">Criar este vídeo</button>
              <button v-if="v.projeto" type="button" @click="patch(v.n, { unlink: true })">Desligar</button>
              <select v-else-if="ch.projetos.length" @change="$event.target.value && patch(v.n, { project_id: $event.target.value })" aria-label="Ligar a um vídeo que já existe"><option value="">Ligar a um vídeo existente…</option><option v-for="p in ch.projetos" :key="p.id" :value="p.id">{{ p.title }}</option></select>
              <button type="button" @click="editing = v.n">Editar título</button>
              <button type="button" class="danger" @click="removeVideo(v)" aria-label="Tirar do calendário">Tirar</button>
            </div>
          </li>
        </ul>
        <details v-if="w.tarefas.length"><summary>Tarefas da semana ({{ w.tarefas.filter((t, i) => checks['s' + w.n + '_' + i]).length }} de {{ w.tarefas.length }})</summary>
          <ul class="tasks"><li v-for="(t, i) in w.tarefas" :key="i"><label class="check"><input type="checkbox" :checked="!!checks['s' + w.n + '_' + i]" @change="toggle(checks, 's' + w.n + '_' + i, 'mc_chk_')"> <span>{{ t }}</span></label></li></ul></details>
      </article>
      <pager :pg="pgW" label="Páginas das semanas"></pager>
    </div>

    <!-- ===================== SHORTS ===================== -->
    <div v-if="tab === 'shorts' && hasPlan && sp" class="plano">
      <div class="card">
        <h2>Para que servem os Shorts neste canal</h2>
        <p class="big">{{ sp.estrategia.objetivo }}</p>
        <ol class="how"><li v-for="f in sp.estrategia.funil" :key="f[0]"><b>{{ f[0] }}.</b> {{ f[1] }}</li></ol>
        <p><b>Ritmo:</b> {{ sp.estrategia.cadencia }}</p>
        <p class="hint">{{ ch.shorts_resumo.ideias }} ideias no banco · {{ ch.shorts_resumo.agendados }} agendadas · {{ ch.shorts_resumo.publicados }} publicadas<template v-if="ch.shorts_resumo.do_roteiro"> · {{ ch.shorts_resumo.do_roteiro }} escritas a partir do roteiro</template></p>
        <p class="hint">Para cortar os Shorts direto de um vídeo já pronto, abra o vídeo, vá em Publicar e use “Gerar Shorts”.</p>
      </div>

      <div class="card">
        <h2>Como Shorts e vídeos longos contam para o Programa de Parcerias</h2>
        <p>{{ sp.caminhos.separado }}</p>
        <div class="marcos two">
          <div v-for="c in sp.caminhos.caminhos" :key="c.id" class="marco" :class="{ pick: c.id === 'horas' }">
            <h3>{{ c.nome }}</h3>
            <p><b>Hoje:</b> {{ c.hoje }}</p>
            <p><b>Depois de 1º/02/2027:</b> {{ c.depois }}</p>
            <p><b>O que conta:</b> {{ c.conta }}</p>
            <p class="hint"><b>Esforço:</b> {{ c.esforco }}</p>
          </div>
        </div>
        <p class="hint">{{ sp.caminhos.degrau }}</p>
        <h3>Dinheiro</h3><ul><li v-for="(r, i) in sp.caminhos.receita" :key="i">{{ r }}</li></ul>
        <div class="recom">
          <h3>Qual caminho combina com o seu canal: {{ sp.caminhos.recomendacao.caminho }}</h3>
          <ul><li v-for="(m, i) in sp.caminhos.recomendacao.motivos" :key="i">{{ m }}</li></ul>
          <p class="hint">{{ sp.caminhos.recomendacao.quando_mudar }}</p>
        </div>
        <p class="hint">Números de estimativas de terceiros podem variar, e as páginas do YouTube nem sempre concordam entre si. Confirme o que vale para o seu canal em YouTube Studio > Monetização.
          Fontes: <template v-for="(f, i) in sp.caminhos.fontes" :key="f[1]"><a :href="f[1]" target="_blank" rel="noopener noreferrer">{{ f[0] }}</a><span v-if="i < sp.caminhos.fontes.length - 1">, </span></template>.</p>
      </div>

      <div class="card">
        <h2>Calculadora: quanto os Shorts ajudam</h2>
        <p class="hint">São suposições para você testar. Troque pelos seus números reais depois de algumas semanas (aba Métricas e Análises do YouTube).</p>
        <div class="grid2">
          <label>Visualizações de Shorts por semana<input type="number" min="0" v-model.number="sc.views"></label>
          <label>De cada 100 pessoas, quantas abrem o vídeo longo?<input type="number" min="0" step="0.1" v-model.number="sc.conv"><small class="hint">Costuma ser bem pouco: menos de 1.</small></label>
          <label>Minutos assistidos no vídeo longo<input type="number" min="0" step="0.5" v-model.number="sc.avd"></label>
          <label>Inscritos a cada mil visualizações<input type="number" min="0" step="0.5" v-model.number="sc.subs"></label>
        </div>
        <p>Por semana: cerca de <b>{{ nf1(calcShortHours) }} horas</b> nos vídeos longos e <b>{{ nf1(calcShortSubs) }} inscritos</b>. Em 13 semanas: <b>{{ nf(calcShortHours * 13) }} horas</b> e <b>{{ nf(calcShortSubs * 13) }} inscritos</b>.</p>
      </div>

      <div class="card">
        <h2>Regras de um bom Short</h2>
        <ul><li v-for="(r, i) in sp.estrategia.regras" :key="i">{{ r }}</li></ul>
        <h3>O que acompanhar</h3><ul><li v-for="(r, i) in sp.estrategia.medir" :key="i">{{ r }}</li></ul>
      </div>

      <div class="card">
        <h2>Calendário de Shorts (90 dias)</h2>
        <p class="hint">Cada Short sai 1 e 3 dias depois do vídeo longo a que leva. Mude a situação conforme avança.</p>
        <section v-for="w in pgS.items" :key="w.n" class="swk">
          <h3>Semana {{ w.n }}</h3>
          <ul class="vlist">
            <li v-for="x in w.items" :key="x.id" class="vrow" :class="x.status">
              <div class="vtop"><span class="vdate">{{ fdate(x.data) }}</span><span class="tag">{{ x.nome }}</span><span class="tag">{{ x.duracao }} s</span><span class="tag">leva a: {{ shortLabel(x.video_n) }}</span></div>
              <p class="vtitle">“{{ x.gancho }}”</p>
              <p class="hint"><b>Final em laço:</b> {{ x.final }}</p>
              <div class="vact"><label class="inline">Situação<select :value="x.status" @change="patchShort(x.video_n, x.id, { status: $event.target.value })"><option v-for="(t, k) in SHORT_STATUS" :key="k" :value="k">{{ t }}</option></select></label></div>
            </li>
          </ul>
        </section>
        <pager :pg="pgS" label="Páginas das semanas de Shorts"></pager>
      </div>

      <div class="card">
        <h2>Banco de ideias por vídeo</h2>
        <p class="hint">Cada vídeo longo tem pelo menos 10 ideias de Short, com gancho, duração ideal e final em laço. As ideias “base” seguem modelos e usam só o tema do vídeo; depois que o roteiro existir, toque em “Gerar ideias a partir do roteiro” para a andes escrever ideias baseadas no texto real.</p>
        <details v-for="v in pgV.items" :key="v.n" class="sideas">
          <summary>{{ fdate(v.data) }} · {{ v.titulo }} <span class="badge">{{ v.shorts.length }} ideias</span></summary>
          <div class="row-tight"><button type="button" class="primary" :disabled="!!sc.busy[v.n]" @click="genIdeas(v)">{{ sc.busy[v.n] ? 'Gerando…' : 'Gerar ideias a partir do roteiro' }}</button>
            <span v-if="sc.busy[v.n]" class="hint">{{ sc.busy[v.n] }}</span>
            <span v-else-if="!v.project_id" class="hint">Sem roteiro ligado: as ideias usarão só o título.</span></div>
          <ul class="vlist">
            <li v-for="x in v.shorts" :key="x.id" class="vrow" :class="x.status">
              <div class="vtop"><span class="tag">{{ x.nome }}</span><span class="tag">ideal {{ x.duracao }} s ({{ x.faixa }})</span><span class="tag">{{ x.origem === 'roteiro' ? 'a partir do roteiro' : 'ideia-base' }}</span></div>
              <p class="vtitle">“{{ x.gancho }}”</p>
              <p class="hint"><b>Dica visual:</b> {{ x.visual }}</p>
              <p class="hint"><b>Final em laço:</b> {{ x.final }}</p>
              <p class="hint"><b>Levar ao vídeo longo:</b> {{ x.cta }}</p>
              <div class="vact">
                <label class="inline">Quando<select :value="x.dia === null ? '' : x.dia" @change="$event.target.value === '' ? patchShort(v.n, x.id, { agendar: false }) : patchShort(v.n, x.id, { dia: Number($event.target.value) })"><option value="">Não agendar</option><option v-for="o in OFFSETS" :key="o[0]" :value="o[0]">{{ o[1] }}</option></select></label>
                <label class="inline">Situação<select :value="x.status" @change="patchShort(v.n, x.id, { status: $event.target.value })"><option v-for="(t, k) in SHORT_STATUS" :key="k" :value="k">{{ t }}</option></select></label>
                <button type="button" @click="copyText(x.gancho + String.fromCharCode(10) + x.final)">Copiar gancho e final</button>
              </div>
            </li>
          </ul>
        </details>
        <pager :pg="pgV" label="Páginas dos vídeos"></pager>
      </div>
    </div>

    <!-- ===================== PLANO ===================== -->
    <div v-if="tab === 'plano' && hasPlan" class="plano">
      <p class="lead">Tudo aqui pode ser editado: toque em <b>Editar</b> em qualquer seção. O que você edita não é sobrescrito quando o modelo for atualizado.</p>
      <section-card v-if="plan.estudo_de_temas" :value="plan.estudo_de_temas" section-key="estudo_de_temas" title="Estudo de temas (YouTube, 22/11/2026)" hint="O que a busca no YouTube mostrou sobre cada tema, e o que mudou no plano por causa disso." :saver="saveSection" :edited="isEdited('estudo_de_temas')" open></section-card>
      <section-card v-if="plan.regras_do_canal" :value="plan.regras_do_canal" section-key="regras_do_canal" title="Regras do canal para gerar os vídeos" hint="É o que o MisterClip segue ao montar cada vídeo: voz, estilo, ritmo das cenas, animação, música, título, miniatura, descrição, Shorts e publicação. O seu roteiro nunca é reescrito: as regras só avisam o que foge delas." :saver="saveSection" :edited="isEdited('regras_do_canal')" open></section-card>
      <section-card v-if="plan.posicionamento" :value="plan.posicionamento" section-key="posicionamento" title="Posicionamento" :saver="saveSection" :edited="isEdited('posicionamento')" open></section-card>
      <section-card v-if="plan.nicho" :value="plan.nicho" section-key="nicho" title="Nicho, identidade e espectador ideal" hint="A comparação de 5 nichos, a escolha e a identidade do canal." :saver="saveSection" :edited="isEdited('nicho')"></section-card>
      <section-card v-if="plan.pilares" :value="plan.pilares" section-key="pilares" title="Pilares de conteúdo" :saver="saveSection" :edited="isEdited('pilares')"></section-card>
      <section-card v-if="plan.formatos" :value="plan.formatos" section-key="formatos" title="Formatos de vídeo" :saver="saveSection" :edited="isEdited('formatos')"></section-card>
      <section-card v-if="plan.frequencia" :value="plan.frequencia" section-key="frequencia" title="Frequência de postagem" :saver="saveSection" :edited="isEdited('frequencia')"></section-card>
      <section-card v-if="plan.crescimento" :value="plan.crescimento" section-key="crescimento" title="Como o canal cresce" :saver="saveSection" :edited="isEdited('crescimento')"></section-card>
      <section-card v-if="plan.retencao" :value="plan.retencao" section-key="retencao" title="Estrutura para prender a atenção" :saver="saveSection" :edited="isEdited('retencao')"></section-card>
      <section-card v-if="plan.monetizacao" :value="plan.monetizacao" section-key="monetizacao" title="Monetização e regras do YouTube" :saver="saveSection" :edited="isEdited('monetizacao')"></section-card>
      <section-card v-if="plan.concorrentes" :value="plan.concorrentes" section-key="concorrentes" title="Concorrentes observados" :hint="'Números aproximados, vistos na busca pública do YouTube em ' + (plan.dados_de || '')" :saver="saveSection" :edited="isEdited('concorrentes')"></section-card>
      <section-card v-if="plan.cenarios" :value="plan.cenarios" section-key="cenarios" title="O que esperar (cenários)" :saver="saveSection" :edited="isEdited('cenarios')"></section-card>
      <section-card v-if="plan.semanas && plan.semanas.length" :value="plan.semanas" section-key="semanas" title="Foco e tarefas de cada semana" :saver="saveSection" :edited="isEdited('semanas')"></section-card>
      <section-card v-if="plan.checklist_publicar" :value="plan.checklist_publicar" section-key="checklist_publicar" title="Lista antes de publicar" :saver="saveSection" :edited="isEdited('checklist_publicar')"></section-card>
      <section-card v-if="plan.fontes" :value="plan.fontes" section-key="fontes" title="Fontes" hint="As regras do YouTube mudam. Antes de decidir, confirme em YouTube Studio > Monetização." :saver="saveSection" :edited="isEdited('fontes')"></section-card>
    </div>

    <!-- ===================== IDEIAS ===================== -->
    <div v-if="tab === 'ideias'" class="plano">
      <p class="lead">Banco de ideias, títulos que dão clique, concorrentes a estudar e roteiros prontos. Tudo editável.</p>
      <ideas-list v-if="plan.ideias && plan.ideias.length" :ideas="plan.ideias" :categorias="(plan.nicho && plan.nicho.categorias) || []" :saver="saveSection" :cid="id" :api="api" :say="say" @novo-video="novoVideo" @changed="load"></ideas-list>
      <section-card v-if="plan.titulos" :value="plan.titulos" section-key="titulos" title="20 ideias com 3 títulos, miniatura e gancho" hint="Cada ideia traz 3 opções de título, a miniatura (até 4 palavras), o gancho dos primeiros 15 segundos e o motivo do clique." :saver="saveSection" :edited="isEdited('titulos')"></section-card>
      <section-card v-if="plan.concorrentes_estudo" :value="plan.concorrentes_estudo" section-key="concorrentes_estudo" title="Concorrentes para estudar e lacunas de conteúdo" :saver="saveSection" :edited="isEdited('concorrentes_estudo')"></section-card>
      <scripts-view :roteiros="plan.roteiros || []" :videos="ch.videos || []" :cid="id" :api="api" :saver="saveSection" :say="say" @novo-video="novoVideo" @changed="load"></scripts-view>
      <section-card v-if="plan.roteiros" :value="plan.roteiros" section-key="roteiros" title="Roteiros (editar todos os campos)" :saver="saveSection" :edited="isEdited('roteiros')"></section-card>
      <section-card v-if="plan.ideias" :value="plan.ideias" section-key="ideias" title="Ideias (editar a lista inteira)" :saver="saveSection" :edited="isEdited('ideias')"></section-card>
    </div>

    <!-- ===================== YOUTUBE ===================== -->
    <youtube-view v-if="tab === 'youtube'" :id="id" :api="api" :say="say"></youtube-view>

    <!-- ===================== OPERAÇÃO ===================== -->
    <div v-if="tab === 'operacao'" class="plano">
      <p class="lead">Como o canal funciona no dia a dia: o algoritmo, a produção com IA, a monetização por fase e a revisão semanal. Tudo editável.</p>
      <section-card v-if="plan.algoritmo" :value="plan.algoritmo" section-key="algoritmo" title="Como o algoritmo pensa" :saver="saveSection" :edited="isEdited('algoritmo')" open></section-card>
      <section-card v-if="plan.producao" :value="plan.producao" section-key="producao" title="Fluxo de produção com IA" :saver="saveSection" :edited="isEdited('producao')"></section-card>
      <section-card v-if="plan.monetizacao_fases" :value="plan.monetizacao_fases" section-key="monetizacao_fases" title="Monetização por fase e lista de inscrição" :saver="saveSection" :edited="isEdited('monetizacao_fases')"></section-card>
      <section-card v-if="plan.revisao" :value="plan.revisao" section-key="revisao" title="Revisão semanal e mensal" :saver="saveSection" :edited="isEdited('revisao')"></section-card>
    </div>

    <!-- ===================== MÉTRICAS ===================== -->
    <div v-if="tab === 'metricas'" class="cgrid">
      <form class="card" @submit.prevent="addMetric">
        <strong>Registrar os números da semana</strong>
        <p class="hint">Veja no YouTube Studio > Análises. Faça isto uma vez por semana, no domingo.</p>
        <div class="grid2">
          <label>Data<input type="date" v-model="mf.day" required></label>
          <label>Inscritos agora<input v-model="mf.subs" inputmode="numeric" required placeholder="0"></label>
          <label>Horas de exibição (12 meses)<input v-model="mf.hours" inputmode="decimal" required placeholder="0"><small class="hint">Em Análises > Avançado, “Tempo de exibição (horas)”.</small></label>
          <label>Visualizações (28 dias)<input v-model="mf.views" inputmode="numeric" placeholder="0"></label>
          <label>Taxa de cliques (CTR, %)<input v-model="mf.ctr" inputmode="decimal" placeholder="Ex.: 5,2"></label>
          <label>Tempo médio assistido (%)<input v-model="mf.avd" inputmode="decimal" placeholder="Ex.: 38"></label>
        </div>
        <label>Anotação<input v-model="mf.note" maxlength="200" placeholder="Ex.: vídeo do Mago foi bem"></label>
        <button class="primary" type="submit">Registrar</button>
      </form>

      <div class="card" v-if="chart">
        <strong>Horas de exibição: plano e realidade</strong>
        <svg :viewBox="'0 0 ' + chart.W + ' ' + chart.H" class="chart" role="img" aria-label="Gráfico de horas de exibição por semana">
          <g v-for="t in chart.ticks" :key="t.t"><line :x1="chart.L" :x2="chart.W - 14" :y1="t.y" :y2="t.y" class="grid"/><text :x="chart.L - 6" :y="t.y + 4" text-anchor="end" class="axis">{{ nf(t.t) }}</text></g>
          <line :x1="chart.L" :x2="chart.W - 14" :y1="chart.y4000" :y2="chart.y4000" class="y4000"/><text :x="chart.W - 16" :y="chart.y4000 - 4" text-anchor="end" class="axis">4.000 h</text>
          <g v-if="chart.xFeb"><line :x1="chart.xFeb" :x2="chart.xFeb" y1="14" :y2="chart.H - 30" class="feb"/><text :x="chart.xFeb - 4" y="24" text-anchor="end" class="axis">1º/02: novas regras</text></g>
          <polyline :points="chart.floor" class="floor"/><polyline :points="chart.goal" class="goal"/>
          <circle v-for="(p, i) in chart.pts" :key="i" :cx="p.x" :cy="p.y" r="5" class="pt"><title>{{ p.t }}</title></circle>
          <text v-for="w in [0, 4, 8, 13]" :key="w" :x="chart.X(w)" :y="chart.H - 10" :text-anchor="w === 13 ? 'end' : 'middle'" class="axis">sem. {{ w }}</text>
        </svg>
        <p class="legend"><span class="lg goal"></span> meta <span class="lg floor"></span> mínimo <span class="lg pt"></span> o que você registrou</p>
      </div>

      <div class="card" v-if="ch.projecao.ritmo_dia !== null">
        <strong>Projeção</strong>
        <p>No ritmo de {{ nf1(ch.projecao.ritmo_dia) }} h por dia (de {{ fday(ch.projecao.base_de) }} a {{ fday(ch.projecao.base_ate) }}):</p>
        <ul><li>cerca de <b>{{ nf(ch.projecao.horas_31jan) }} h</b> em 31/01/2027</li><li v-if="ch.projecao.data_4000">4.000 h por volta de <b>{{ fday(ch.projecao.data_4000) }}</b></li><li v-else>no ritmo atual, 4.000 h não são alcançadas</li></ul>
        <p class="hint">É só a continuação do ritmo recente. Um vídeo que dá certo muda tudo para cima; semanas sem publicar, para baixo.</p>
      </div>

      <div class="card">
        <strong>Calculadoras</strong>
        <h3>Quantas horas rende um vídeo?</h3>
        <div class="grid2"><label>Visualizações<input type="number" min="0" v-model.number="calc.views"></label><label>Minutos assistidos por pessoa<input type="number" min="0" step="0.5" v-model.number="calc.avd"></label></div>
        <p>≈ <b>{{ nf(calcHours) }} horas</b>. Para 4.000 horas, são {{ nf(calc.views > 0 && calc.avd > 0 ? 4000 / (calcHours / calc.views) : 0) }} visualizações assim.</p>
        <h3>Quantas views para ganhar R$ 1.000 por mês?</h3>
        <label>Receita por mil visualizações (R$)<input type="number" min="1" step="0.5" v-model.number="calc.rpm"><small class="hint">No Brasil costuma ficar entre R$ 1 e R$ 20 conforme o assunto. Veja o valor real no Studio quando monetizar.</small></label>
        <p>São cerca de <b>{{ nf(calcViews) }} visualizações por mês</b>.</p>
      </div>

      <div class="card wide2" v-if="metricsDesc.length">
        <strong>Registros</strong>
        <table class="mtable"><thead><tr><th>Data</th><th>Inscritos</th><th>Horas</th><th>Views</th><th>CTR</th><th>Assistido</th><th></th></tr></thead>
          <tbody><tr v-for="m in pgM.items" :key="m.id"><td>{{ fday(m.day) }}<small v-if="m.note"> · {{ m.note }}</small></td><td>{{ nf(m.subs) }}</td><td>{{ nf(m.hours) }}</td><td>{{ nf(m.views) }}</td><td>{{ m.ctr ?? '–' }}</td><td>{{ m.avd ?? '–' }}</td><td><button type="button" class="danger" @click="delMetric(m)" aria-label="Apagar registro">✕</button></td></tr></tbody></table>
        <pager :pg="pgM" label="Páginas dos registros"></pager>
      </div>
    </div>

    <!-- ===================== ROTEIRO E LISTA ===================== -->
    <div v-if="tab === 'roteiro'" class="plano">
      <div class="card" v-if="plan.retencao">
        <h2>Modelo de roteiro que prende a atenção</h2>
        <p class="hint">Use como guia ao escrever. O MisterClip transforma o texto em cenas, imagens, voz e legendas.</p>
        <ol class="how"><li v-for="r in plan.retencao.estrutura" :key="r[0]"><b>{{ r[0] }} · {{ r[1] }}.</b> {{ r[2] }}</li></ol>
        <ul><li v-for="(r, i) in plan.retencao.regras" :key="i">{{ r }}</li></ul>
      </div>
      <div class="card" v-if="plan.checklist_publicar">
        <h2>Antes de publicar cada vídeo</h2>
        <p class="hint">Marque tudo antes de enviar ao YouTube. Estes pontos protegem a monetização e ajudam o vídeo a ser clicado e assistido. Suas marcações ficam salvas neste aparelho.</p>
        <ul class="tasks"><li v-for="(t, i) in plan.checklist_publicar" :key="i"><label class="check"><input type="checkbox" :checked="!!pubChecks['p' + i]" @change="toggle(pubChecks, 'p' + i, 'mc_pub_')"> <span>{{ t }}</span></label></li></ul>
        <button type="button" @click="clearPub">Desmarcar tudo para o próximo vídeo</button>
      </div>
    </div>
  </section>
  <section v-else><a class="back" href="#/canais">← Canais</a><p v-if="err" class="error-line" role="alert">{{ err }}</p><p v-else class="muted">Carregando…</p></section>`,
};
