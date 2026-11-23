import { usePager, Pager } from './pager.js';
import { createApp, ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from './vendor/vue.esm-browser.prod.js';
import { useAgendaMes, deslocarMes } from './agenda-mes.js';
import { CanaisView, CanalView, CHAN_TABS } from './canal.js';
import { ClipeNovo } from './clipe.js';
import { PromptsView } from './prompts.js';

// ------------------------------------------------------------------ API
const authNeeded = ref(false);

function friendly(status, msg) {
  if (status === 409) return /ocupado|em andamento/i.test(msg) ? 'Este vídeo está ocupado com outra tarefa. Espere terminar ou cancele pela barra de baixo.' : msg;
  if (status >= 500) return 'Algo deu errado no servidor. Tente de novo; se repetir, avise quem cuida da andes.';
  if (status === 404) return 'Não encontrei o que você pediu. Talvez tenha sido apagado: volte à lista e tente de novo.';
  return msg;
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      credentials: 'same-origin',
      headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {},
      ...opts,
      body: opts.body instanceof FormData ? opts.body : opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new Error('Não consegui falar com o MisterClip. Confira se a andes está ligada e se este aparelho está conectado à rede mesh.');
  }
  if (res.status === 401) { authNeeded.value = true; throw new Error('Digite a senha de acesso para continuar.'); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(friendly(res.status, msg));
  }
  return res.status === 204 ? null : res.json();
}

const STATUS = { draft: 'rascunho', planned: 'em preparo', storyboard: 'pronto para revisar', rendering: 'criando o vídeo', done: 'vídeo pronto' };
const STEPS = [{ id: 'roteiro', label: 'Roteiro' }, { id: 'cenas', label: 'Cenas' }, { id: 'opcoes', label: 'Ajustes' }, { id: 'video', label: 'Vídeo' }, { id: 'publicar', label: 'Publicar' }];
const fmt = (s) => (s == null ? '–' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);
const dur = (sec) => { sec = Math.max(0, Math.round(sec)); const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60; return h ? `${h} h ${String(m).padStart(2, '0')} min` : m ? `${m} min ${String(s).padStart(2, '0')} s` : `${s} s`; };

// ---- datas no fuso do usuário (o servidor só entrega epoch; quem separa por dia é o navegador)
const p2 = (n) => String(n).padStart(2, '0');
const isoLocal = (d) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const monthOfIso = (iso) => iso.slice(0, 7);
const WEEKDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const ddmm = (ts) => new Date(ts * 1000).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
const dayTitle = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const monthTitle = (ym) => new Date(ym + '-01T12:00:00').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
const JOB_TITLE = { recaption: 'Gravando as legendas', script_draft: 'Escrevendo o rascunho do roteiro', youtube_upload: 'Enviando ao YouTube', script_review: 'Revisando o roteiro', youtube_sync: 'Lendo os números do YouTube', shorts: 'Criando os Shorts', shorts_ideas: 'Escrevendo ideias de Short', plan: 'Dividindo o roteiro em cenas', prepare: 'Gerando voz e imagens', render: 'Criando o vídeo', regen_image: 'Gerando outra imagem', scene_clip: 'Animando a cena',
  metadata: 'Gerando título, descrição e tags', thumbnail: 'Gerando as miniaturas', voice_sample: 'Gerando a amostra de voz', profile_test: 'Gerando o exemplo do estilo' };
const LIVE_KINDS = ['plan', 'prepare', 'render', 'regen_image', 'scene_clip'];
const CAL_STATUS = { pending: 'Agendado', running: 'Em andamento', done: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado', missed: 'Perdido' };
const CAL_KIND = { completo: 'Preparar e criar o vídeo', preparar: 'Preparação (voz e imagens)', renderizar: 'Criação do vídeo' };

function parseHash() {
  const parts = (location.hash || '#/').replace(/^#\/?/, '').split('/').filter(Boolean);
  if (!parts.length) return { name: 'projects' };
  if (parts[0] === 'novo') return { name: 'new' };
  if (parts[0] === 'clipe') return { name: 'clip' };
  if (parts[0] === 'prompts') return { name: 'prompts' };
  if (parts[0] === 'perfis') return { name: 'profiles' };
  if (parts[0] === 'agenda') return { name: 'agenda' };
  if (parts[0] === 'canais') return { name: 'channels' };
  if (parts[0] === 'canal' && parts[1]) return { name: 'channel', id: parts[1], tab: CHAN_TABS.some((t) => t[0] === parts[2]) ? parts[2] : 'resumo' };
  if (parts[0] === 'ajuda') return { name: 'ajuda' };
  if (parts[0] === 'p' && parts[1]) return { name: 'project', id: parts[1], step: STEPS.some((s) => s.id === parts[2]) ? parts[2] : null };
  return { name: 'projects' };
}

createApp({
  components: { CanaisView, CanalView, ClipeNovo, PromptsView, Pager },
  setup() {
    // ---------------------------------------------------------- estado
    const route = ref(parseHash());
    const cfg = ref({ mode: '', voices: [], default_voice: 'pm_alex', default_speed: 0.85 });
    const profiles = ref([]);
    const projects = ref([]);
    const channels = ref([]);
    const isClip = computed(() => project.value?.meta?.kind === 'clip');
    const clipInfo = computed(() => project.value?.meta?.clip || null);
    const clipSections = computed(() => (clipInfo.value?.analise?.sections || []).map((x) => ({ ...x, len: Math.round(x.end - x.start) })));
    const chanFilter = ref('');
    const newCtx = reactive({ channel_id: '', plan_item: null });
    const project = ref(null);
    const clipLyrics = ref('');
    watch(() => project.value?.text, (t) => { clipLyrics.value = t || ''; }, { immediate: true });
    const saveLyrics = () => {
      if (!confirm('Planejar o clipe de novo apaga as cenas e as imagens atuais e cria a história outra vez com a letra nova. Continuar?')) return;
      return guard(async () => {
        await api(`/api/projects/${project.value.id}/lyrics`, { method: 'PUT', body: { lyrics: clipLyrics.value } });
        await planNow();
      });
    };
    const job = ref(null);
    const estimate = ref(null);
    const music = ref([]);
    const error = ref('');
    const toast = ref('');
    const loading = ref(false);
    const nowTs = ref(Date.now() / 1000);
    const tokenInput = ref('');
    const testImages = reactive({});
    const editing = ref(null);
    const form = reactive({ title: '', text: '', profile_id: '', voice: 'pm_alex', speed: 0.85 });
    const edit = reactive({ title: '', text: '', voice: 'pm_alex', speed: 0.85 });
    const opts = reactive({ transition: 'profile', transition_seconds: 0.5, music: { file: '', volume: 0.25, duck: true } });
    const sample = reactive({ busy: false, url: '' });
    const schedule = ref(null);
    const pub = ref(null);
    const shortsState = ref(null);
    const shortPg = usePager(computed(() => (shortsState.value ? shortsState.value.items : [])), 6);
    const ytState = ref(null);
    const yt = reactive({ privacidade: 'agendado', publish_at: '', sintetico: false });
    const shortsLayout = ref('blur');
    const shortsCount = ref(3);
    const ytEdit = reactive({ title: '', intro: '', tags_text: '', hashtags_text: '', chapters: [] });
    const thumbText = ref('');
    const agenda = ref([]);
    const agPg = usePager(agenda, 10);
    const liveRaw = ref(null);
    const liveOpen = ref((() => { try { return localStorage.getItem('mc_live_open') !== '0'; } catch { return true; } })());
    const liveFollow = ref(true);
    const dayPage = ref(1);
    const daySize = ref(5);
    let listTimer = null;
    const calApi = useAgendaMes({ fetcher: (ym) => api(`/api/calendar?month=${ym}`) });
    const calHoje = ref(isoLocal(new Date()));
    const cal = reactive({ mes: monthOfIso(isoLocal(new Date())), sel: isoLocal(new Date()) });
    const ndlg = reactive({ open: false, date: '', time: '23:00', project_id: '', est: null, error: '' });
    const dlg = reactive({ open: false, value: '', error: '' });
    const view = reactive({ filter: 'todas', limit: 20, open: null, newText: '' });
    let timer = null, lastFull = 0;

    const profileMap = computed(() => Object.fromEntries(profiles.value.map((p) => [p.id, p])));
    const step = computed(() => route.value.step || (project.value?.status === 'done' ? 'video' : project.value?.scenes?.length ? 'cenas' : 'roteiro'));
    const wordCount = computed(() => (form.text.trim() ? form.text.trim().split(/\s+/).length : 0));
    const estMinutes = computed(() => (wordCount.value / (2.75 * (form.speed / 0.85)) / 60).toFixed(1));
    // ---- premissas do canal: o roteiro é seu e não é reescrito; o resto (voz, estilo, cenas, música, título) segue as regras do canal
    const rulesInfo = ref(null), scriptCheck = ref(null), formTouched = reactive({ profile: false, voice: false, speed: false });
    const loadRules = async (cid) => {
      rulesInfo.value = null;
      if (!cid) return;
      try {
        const r = await api(`/api/channels/${cid}/rules`);
        if (newCtx.channel_id !== cid) return;
        rulesInfo.value = r;
        if (!formTouched.voice && r.padroes.voice) form.voice = r.padroes.voice;
        if (!formTouched.speed && r.padroes.speed) form.speed = r.padroes.speed;
        if (!formTouched.profile && r.padroes.profile_id && profiles.value.some((x) => x.id === r.padroes.profile_id)) form.profile_id = r.padroes.profile_id;
      } catch { rulesInfo.value = null; }
    };
    let lintTimer = null, lintSeq = 0;
    const runLint = async () => {
      const cid = newCtx.channel_id, text = form.text.trim(), seq = ++lintSeq;
      if (!cid || text.split(/\s+/).length < 5) { scriptCheck.value = null; return; }
      try { const r = await api(`/api/channels/${cid}/lint`, { method: 'POST', body: { kind: 'roteiro', text: form.text } }); if (seq === lintSeq) scriptCheck.value = r; } catch { if (seq === lintSeq) scriptCheck.value = null; }
    };
    watch(() => newCtx.channel_id, (cid) => { loadRules(cid); runLint(); });
    watch(() => form.text, () => { clearTimeout(lintTimer); lintTimer = setTimeout(runLint, 700); });
    const scriptErrors = computed(() => (scriptCheck.value?.achados || []).filter((x) => x.nivel === 'erro'));
    const elapsed = computed(() => (job.value?.started ? nowTs.value - job.value.started : 0));
    const eta = computed(() => (job.value && job.value.progress > 0.04 ? elapsed.value / job.value.progress - elapsed.value : null));
    const stopped = computed(() => !project.value?.busy && job.value && ['failed', 'cancelled'].includes(job.value.status));
    // ------------------------------------------- imagens/narrações desatualizadas (e como sair disso)
    const hasWords = (s) => !!(s.has_words || s.words);
    const outdatedImg = computed(() => (project.value?.scenes || []).filter((s) => s.image && s.dirty_image));
    const outdatedAud = computed(() => (project.value?.scenes || []).filter((s) => s.audio && hasWords(s) && s.dirty_audio));
    const styleOutdated = computed(() => outdatedImg.value.filter((s) => !s.profile_id).length);
    const styleChange = computed(() => project.value?.meta?.style_change || null);
    const voiceChange = computed(() => project.value?.meta?.voice_change || null);
    const revertTo = ref('');
    const revertDefault = computed(() => {
      const sc = styleChange.value;
      if (sc && profileMap.value[sc.from]) return sc.from;
      const n = {};
      outdatedImg.value.forEach((s) => { if (s.image_profile) n[s.image_profile] = (n[s.image_profile] || 0) + 1; });
      const best = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
      return best ? best[0] : (profiles.value.find((p) => p.id !== project.value?.profile_id) || {}).id || '';
    });
    const revertSel = computed({ get: () => (profileMap.value[revertTo.value] ? revertTo.value : revertDefault.value), set: (v) => { revertTo.value = v; } });
    const styleName = (id) => profileMap.value[id]?.name || id;
    const keepStale = (kind, scenes) => guard(async () => {
      project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}/stale/keep`, { method: 'POST', body: { kind, scenes: scenes || null } })) };
      await loadEstimate(); say(kind === 'image' ? 'Pronto: as imagens atuais foram mantidas.' : 'Pronto: as narrações atuais foram mantidas.');
    });
    const revertStyle = () => guard(async () => {
      project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}/style/revert`, { method: 'POST', body: { profile_id: revertSel.value } })) };
      revertTo.value = ''; await loadEstimate(); say(`Voltou ao estilo "${styleName(project.value.profile_id)}". Nada foi refeito.`);
    });
    const revertVoice = () => guard(async () => {
      const vc = voiceChange.value;
      project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}/voice/revert`, { method: 'POST', body: { voice: vc.from_voice, speed: vc.from_speed } })) };
      syncForms(project.value); await loadEstimate(); say('Voltou à voz anterior. Nada foi refeito.');
    });
    const canAskNotifications = computed(() => window.isSecureContext && window.Notification && Notification.permission === 'default');

    // ---------------------------------------------------- textos de apoio (linguagem simples)
    const VOICE_LABEL = { pm_alex: 'Alex (voz masculina)', pm_santa: 'Santa (voz masculina)', pf_dora: 'Dora (voz feminina)' };
    const voiceLabel = (v) => VOICE_LABEL[v] || v;
    const MOTION_OPTS = [['ken_burns', 'Zoom suave na imagem'], ['ltx', 'Animar a imagem (rápido)'], ['wan', 'Animar a imagem (mais fiel)']];
    const TRANSITION_OPTS = [['profile', 'Padrão do estilo escolhido'], ['crossfade', 'Dissolver suavemente'], ['fade_black', 'Escurecer entre as cenas'], ['dissolve', 'Dissolver granulado'], ['cut', 'Corte direto']];
    const transLabel = (k) => (TRANSITION_OPTS.find((t) => t[0] === k) || [k, k])[1];
    const FILTERS = [{ id: 'todas', label: 'Todas' }, { id: 'animadas', label: 'Animadas' }, { id: 'problemas', label: 'Pendentes' }];
    const NEXT = { draft: 'Falta dividir o roteiro em cenas', planned: 'Próximo: gerar voz e imagens', storyboard: 'Próximo: revisar e criar o vídeo', rendering: 'Criando o vídeo…', done: 'Vídeo pronto: baixe e prepare a publicação' };
    const nextHint = (p) => (p.meta?.kind === 'clip' && p.status === 'planned' ? 'Próximo: gerar as imagens' : p.scene_count === 0 ? NEXT.draft : NEXT[p.status] || '');
    let seen = {}; try { seen = JSON.parse(localStorage.getItem('mc_tips') || '{}'); } catch {}
    const tips = reactive(seen);
    const showTip = (id) => !tips[id];
    const dismissTip = (id) => { tips[id] = true; try { localStorage.setItem('mc_tips', JSON.stringify(tips)); } catch {} };
    const guide = computed(() => {
      const p = project.value, e = estimate.value;
      if (!p) return null;
      if (p.busy) {
        const k = job.value?.kind;
        const title = k === 'render' ? 'Criando o vídeo' : k === 'prepare' ? (isClip.value ? 'Gerando as imagens do clipe' : 'Gerando voz e imagens') : k === 'plan' ? (isClip.value ? 'Ouvindo a música e criando a história' : 'Dividindo o roteiro em cenas') : 'Trabalhando';
        return { icon: '⏳', tone: 'busy', title, text: 'Você pode fechar esta página ou até desligar o seu computador: o trabalho continua na andes, enquanto ela estiver ligada, e o resultado fica salvo. Para parar, use Cancelar na barra de baixo.' };
      }
      if (stopped.value) return { icon: '⚠️', tone: 'warn', title: 'A tarefa parou', text: 'Nada do que já foi gerado se perdeu. Toque em "Tentar de novo" na barra de baixo para continuar de onde parou.' };
      if ((p.status === 'storyboard' || p.status === 'done') && (outdatedImg.value.length || outdatedAud.value.length)) {
        return { icon: '⚠️', tone: 'warn', title: 'Algumas coisas estão desatualizadas', text: 'Você mudou o estilo ou a voz, e o que já foi gerado continua como era. Nada foi apagado. Escolha abaixo: voltar atrás, manter como está ou gerar de novo.' };
      }
      if (!p.scenes.length) return isClip.value ? { icon: '🎵', tone: '', title: 'Falta planejar o clipe', text: 'Toque em "Planejar cenas" na barra de baixo: a andes ouve a música, cria a história e divide as cenas no ritmo.' } : { icon: '📝', tone: '', title: 'Falta dividir o roteiro em cenas', text: 'Toque em "Planejar cenas" na barra de baixo. É rápido.' };
      if (isClip.value && p.status === 'planned') return { icon: '🖼️', tone: '', title: 'Próximo passo: gerar as imagens', text: `O MisterClip vai desenhar uma imagem para cada cena da história${e && e.seconds.prepare ? ', o que leva ' + e.human.prepare : ''}. Depois você revisa tudo antes de animar e montar o clipe.` };
      if (p.status === 'planned') return { icon: '🎙️', tone: '', title: 'Próximo passo: gerar voz e imagens', text: `O MisterClip vai narrar cada cena e desenhar uma imagem para ela${e && e.seconds.prepare ? ', o que leva ' + e.human.prepare : ''}. Você ainda poderá revisar tudo antes de criar o vídeo.` };
      if (p.status === 'storyboard') return { icon: '👀', tone: '', title: 'Revise as cenas e aprove', text: 'Veja cada imagem e leia o texto (toque numa cena para editar, trocar o estilo ou gerar outra imagem). Quando estiver bom, toque em "Aprovar e criar o vídeo".' };
      if (p.status === 'done') return { icon: '✅', tone: 'ok', title: 'Seu vídeo está pronto', text: 'Veja e baixe na aba Vídeo. Depois, na aba Publicar, gere o título, a descrição e a miniatura. Quer mudar algo? Edite as cenas ou os ajustes e crie o vídeo de novo.' };
      return null;
    });

    const guard = async (fn) => { error.value = ''; try { return await fn(); } catch (e) { error.value = e.message; } };
    const say = (m) => { toast.value = m; clearTimeout(say.t); say.t = setTimeout(() => (toast.value = ''), 3500); };
    const go = (h) => { location.hash = h; };
    const media = (path, ver) => `/media/${project.value.id}/${path}?v=${ver ?? 0}`;

    // ----------------------------------------------------- cenas: filtros e problemas
    const issues = (s) => {
      const out = [];
      if (!s.image) out.push('sem imagem'); else if (s.dirty_image) out.push('imagem desatualizada');
      if (!s.audio || s.dirty_audio) out.push('sem narração');
      if (s.clip_error) out.push('clipe falhou');
      if (s.image_warning) out.push('imagem suspeita');
      return out;
    };
    const counts = computed(() => {
      const sc = project.value?.scenes || [];
      return { todas: sc.length, animadas: sc.filter((s) => s.motion !== 'ken_burns').length, problemas: sc.filter((s) => issues(s).length).length };
    });
    const filtered = computed(() => {
      const sc = project.value?.scenes || [];
      if (view.filter === 'animadas') return sc.filter((s) => s.motion !== 'ken_burns');
      if (view.filter === 'problemas') return sc.filter((s) => issues(s).length);
      return sc;
    });
    const scenePg = usePager(filtered, 10);
    const visible = computed(() => scenePg.items);
    watch(() => view.filter, () => { scenePg.reset(); });
    const toggleScene = (n) => { view.open = view.open === n ? null : n; view.newText = ''; };

    // --------------------------------------------------------- carregamento
    async function loadBase() {
      cfg.value = await api('/api/config');
      profiles.value = await api('/api/profiles');
      try { channels.value = await api('/api/channels'); } catch { channels.value = []; }
      form.voice = cfg.value.default_voice; form.speed = cfg.value.default_speed;
      if (!form.profile_id && profiles.value.length) form.profile_id = profiles.value[0].id;
    }
    const loadProjects = () => guard(async () => { loading.value = true; projects.value = await api('/api/projects'); loading.value = false; });
    const chanName = (id) => channels.value.find((c) => c.id === id)?.name || '';
    const projectsAll = computed(() => (chanFilter.value ? projects.value.filter((p) => p.channel_id === chanFilter.value) : projects.value));
    const projPg = usePager(projectsAll, 10);
    const projectsShown = computed(() => projPg.items);
    watch(chanFilter, () => projPg.reset());
    const onNewVideo = (ctx) => { newCtx.channel_id = ctx.channel_id; newCtx.plan_item = ctx.plan_item ?? null; form.title = ctx.titulo || ''; form.text = ctx.texto || ''; go('#/novo'); };
    const loadMusic = async () => { try { music.value = await api('/api/music'); } catch {} };
    const loadEstimate = async () => { try { estimate.value = await api(`/api/projects/${project.value.id}/estimate`); } catch { estimate.value = null; } };
    const refresh = async () => { lastFull = Date.now(); project.value = await api(`/api/projects/${project.value.id}?slim=1`); };

    function syncForms(p) {
      Object.assign(edit, { title: p.title, text: p.text, voice: p.voice, speed: p.speed });
      const o = p.meta?.options || {};
      opts.transition = o.transition || 'profile';
      opts.transition_seconds = o.transition_seconds ?? 0.5;
      opts.music.file = o.music?.file || '';
      opts.music.volume = o.music?.volume ?? 0.25;
      opts.music.duck = o.music?.duck ?? true;
    }

    async function loadProject(id) {
      stopPolling();
      project.value = null; job.value = null; estimate.value = null; error.value = ''; sample.url = '';
      view.filter = 'todas'; scenePg.reset(); view.open = null;
      await guard(async () => {
        project.value = await api(`/api/projects/${id}?slim=1`);
        const st = await api(`/api/projects/${id}/status`);
        job.value = st.job;
        schedule.value = await api(`/api/projects/${id}/schedule`).catch(() => null);
        syncForms(project.value);
        loadMusic(); loadEstimate(); loadPublish();
        if (project.value.busy) { startPolling(); loadLive(); }
      });
    }

    // ------------------------------------------------------------- polling leve
    function stopPolling() { clearInterval(timer); timer = null; }
    function startPolling() { stopPolling(); timer = setInterval(tick, 1500); }
    async function tick() {
      if (route.value.name !== 'project' || !project.value) { stopPolling(); document.title = 'MisterClip'; return; }
      nowTs.value = Date.now() / 1000;
      let st;
      try { st = await api(`/api/projects/${project.value.id}/status`); } catch { return; }
      const wasBusy = project.value.busy;
      job.value = st.job;
      if ((st.schedule?.status || null) !== (schedule.value && ['pending', 'running'].includes(schedule.value.status) ? schedule.value.status : null)) schedule.value = await api(`/api/projects/${project.value.id}/schedule`).catch(() => null);
      if (st.busy) {
        if (LIVE_KINDS.includes(st.job?.kind)) loadLive();
        document.title = `(${Math.round((st.job?.progress || 0) * 100)}%) MisterClip`;
        if (st.updated !== project.value.updated && Date.now() - lastFull > 5000) await refresh();  // miniaturas novas aparecem aos poucos
        else project.value = { ...project.value, busy: true };
        return;
      }
      stopPolling();
      await refresh(); await loadEstimate(); await loadPublish();
      if (wasBusy) finished(project.value, st.job);
    }
    function finished(p, j) {
      const ok = j?.status === 'done';
      document.title = `${ok ? '✓ pronto' : j?.status === 'cancelled' ? '■ cancelado' : '⚠ falhou'} · MisterClip`;
      say(ok ? `Concluído: ${p.title}` : (j?.message || 'O job parou'));
      try { navigator.vibrate?.([200, 100, 200]); } catch {}
      try {
        const ac = new (window.AudioContext || window.webkitAudioContext)(); const o = ac.createOscillator(); const g = ac.createGain();
        o.connect(g); g.connect(ac.destination); g.gain.value = 0.08; o.frequency.value = ok ? 880 : 330; o.start(); o.stop(ac.currentTime + 0.35);
      } catch {}
      try { if (window.Notification && Notification.permission === 'granted') new Notification('MisterClip', { body: ok ? `Concluído: ${p.title}` : (j?.message || 'O job parou') }); } catch {}
    }
    onUnmounted(stopPolling);

    // --------------------------------------------------------------- ações do projeto
    const act = (path, msg) => guard(async () => {
      await api(`/api/projects/${project.value.id}/${path}`, { method: 'POST' });
      say(msg); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
    });
    const planNow = () => act('plan', 'Dividindo o roteiro em cenas…');
    const closeMenus = () => document.querySelectorAll('details.menu[open]').forEach((d) => (d.open = false));
    const replan = () => { closeMenus(); if (confirm('Dividir o roteiro de novo apaga as cenas atuais e as suas edições. Continuar?')) return planNow(); };
    const prepare = () => act('prepare', 'Gerando voz e imagens…');
    const render = () => {
      const e = estimate.value;
      if (e && e.seconds.render > 600 && !confirm(`Criar o vídeo deve levar ${e.human.render} (${e.clips.wan + e.clips.ltx} clipes animados) e usa a GPU da andes o tempo todo.\n\nPare o AudioGlifo antes. Pode continuar?`)) return;
      return act('render', 'Criando o vídeo…');
    };
    const primary = computed(() => {
      const p = project.value, e = estimate.value;
      if (!p || p.busy) return null;
      if (!p.scenes.length) return { label: 'Planejar cenas', run: planNow };
      if (p.status === 'planned') return { label: isClip.value ? 'Gerar as imagens' : 'Preparar voz e imagens', sub: e?.seconds.prepare ? e.human.prepare : '', run: prepare };
      if ((p.status === 'storyboard' || p.status === 'done') && (outdatedImg.value.length || outdatedAud.value.length)) return { label: 'Atualizar o que mudou', sub: e?.seconds.prepare ? e.human.prepare : '', run: prepare };
      if (p.status === 'storyboard') return { label: 'Aprovar e criar o vídeo', sub: e ? e.human.render : '', run: render };
      if (p.status === 'done') return { label: 'Criar o vídeo de novo', sub: e ? e.human.render : '', run: render };
      return null;
    });
    const removeProject = () => { closeMenus(); if (confirm('Apagar este projeto e todos os seus arquivos?')) return guard(async () => { await api(`/api/projects/${project.value.id}`, { method: 'DELETE' }); go('#/'); }); };
    const cancelJob = () => confirm('Parar este job agora? O que já foi gerado fica salvo e você pode continuar depois.') && guard(async () => { await api(`/api/jobs/${job.value.id}/cancel`, { method: 'POST' }); say('Cancelando…'); });
    const retryJob = () => guard(async () => { await api(`/api/jobs/${job.value.id}/retry`, { method: 'POST' }); say('Continuando de onde parou…'); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling(); });
    const askNotifications = () => window.Notification?.requestPermission?.();

    // ------------------------------------------------------- publicar (título, descrição, tags, miniatura)
    const th = computed(() => pub.value?.thumbnail || null);
    const tagsChars = computed(() => ytEdit.tags_text.split(/[,\n]/).map((t) => t.trim()).filter(Boolean).join(',').length);
    function syncYt() {
      const y = pub.value?.youtube;
      if (y) {
        Object.assign(ytEdit, { title: y.title, intro: y.intro, tags_text: y.tags.join(', '), hashtags_text: y.hashtags.join(' ') });
        ytEdit.chapters = (pub.value.chapters_resolved || []).map((c) => ({ scene: c.scene, title: c.title }));
      }
      const t = pub.value?.thumbnail;
      if (t) { const v = t.variants.find((x) => x.i === t.selected) || t.variants[0]; thumbText.value = v?.text || ''; }
    }
    const ruleChecks = ref(null);
    const loadChecks = async () => { try { ruleChecks.value = await api(`/api/projects/${project.value.id}/checks`); } catch { ruleChecks.value = null; } };
    const reviewScript = () => act('review-script', 'A IA está lendo o roteiro… leva cerca de um minuto');
    const loadPublish = async () => { loadChecks(); try { pub.value = await api(`/api/projects/${project.value.id}/publish`); syncYt(); } catch {} try { shortsState.value = await api(`/api/projects/${project.value.id}/shorts`); } catch {} try { ytState.value = await api(`/api/projects/${project.value.id}/youtube`); if (!yt.publish_at && ytState.value.config) yt.sintetico = !!ytState.value.config.conteudo_sintetico; } catch {} };
    const sendYoutube = () => guard(async () => {
      const body = { privacidade: yt.privacidade, conteudo_sintetico: yt.sintetico };
      if (yt.privacidade === 'agendado') body.publish_at = yt.publish_at;
      const bad = ruleChecks.value && !ruleChecks.value.pode_enviar ? ruleChecks.value.achados.filter((x) => x.nivel === 'erro') : [];
      if (bad.length) {
        if (!confirm(`As regras do canal barram este vídeo:\n\n• ${bad.map((x) => x.mensagem).join('\n• ')}\n\nEnviar mesmo assim?`)) return;
        body.ignorar_regras = true;
      }
      await api(`/api/projects/${project.value.id}/youtube/upload`, { method: 'POST', body });
      say('Enviando ao YouTube… você pode fechar esta página'); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
    });
    const ytPriv = { agendado: 'Agendar para uma data (recomendado)', privado: 'Enviar como privado', nao_listado: 'Enviar como não listado', publico: 'Publicar na hora' };
    const ytStatus = { enviando: 'Enviando…', enviado: 'Enviado', publicado: 'Publicado', erro: 'Deu erro' };
    const genShorts = () => guard(async () => {
      await api(`/api/projects/${project.value.id}/shorts/generate`, { method: 'POST', body: { count: shortsCount.value, layout: shortsLayout.value } });
      say('Criando os Shorts…'); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
    });
    const genMeta = () => act('metadata/generate', 'Gerando sugestões de título, descrição e tags…');
    const genThumbs = () => guard(async () => {
      await api(`/api/projects/${project.value.id}/thumbnail/generate`, { method: 'POST', body: { count: 3 } });
      say('Gerando as miniaturas…'); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
    });
    const saveMeta = () => guard(async () => {
      pub.value = await api(`/api/projects/${project.value.id}/metadata`, { method: 'PUT', body: { title: ytEdit.title, intro: ytEdit.intro, tags: ytEdit.tags_text, hashtags: ytEdit.hashtags_text, chapters: ytEdit.chapters } });
      syncYt(); say('Alterações salvas');
    });
    const pickThumb = (i) => guard(async () => { pub.value = await api(`/api/projects/${project.value.id}/thumbnail/select`, { method: 'POST', body: { index: i } }); syncYt(); });
    const applyThumbText = () => guard(async () => {
      pub.value = await api(`/api/projects/${project.value.id}/thumbnail/compose`, { method: 'POST', body: { index: th.value.selected, text: thumbText.value } }); say('Texto aplicado à miniatura');
    });
    async function copy(text, msg) {
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
        else { const ta = document.createElement('textarea'); ta.value = text; ta.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
        say(msg);
      } catch { error.value = 'Não consegui copiar. Selecione o texto e copie manualmente.'; }
    }

    // ------------------------------------------------ andamento por etapa + roteiro ao vivo
    const CLIP_JOB = { plan: 'Ouvindo a música e criando a história do clipe', prepare: 'Gerando as imagens do clipe' };
    const jobTitle = computed(() => (job.value?.status === 'queued' ? 'Na fila' : (isClip.value && CLIP_JOB[job.value?.kind]) || JOB_TITLE[job.value?.kind] || 'Trabalhando'));
    const stageItems = computed(() => job.value?.stages?.items || []);
    const stagePct = (it) => (it.total ? Math.round((it.done / it.total) * 100) : 100);
    const scriptParas = computed(() => (project.value?.text || '').split(String.fromCharCode(10)).filter((x) => x.trim()));
    const showLive = computed(() => !!project.value?.busy && !!job.value && LIVE_KINDS.includes(job.value.kind));
    const liveMap = computed(() => Object.fromEntries((liveRaw.value?.scenes || []).map((r) => [r[0], { a: r[1], w: r[2], i: r[3], c: r[4], m: r[5] }])));
    const liveCurrent = computed(() => liveRaw.value?.current ?? job.value?.stages?.current ?? null);
    const liveVoice = (n) => !!(liveMap.value[n]?.a && liveMap.value[n]?.w);
    const liveImage = (n) => !!liveMap.value[n]?.i;
    const liveClip = (n) => !!liveMap.value[n]?.c;
    const liveAnimated = (n) => (liveMap.value[n]?.m || 'ken_burns') !== 'ken_burns';
    const liveDone = (n) => liveVoice(n) && liveImage(n) && (!liveAnimated(n) || liveClip(n) || job.value?.kind !== 'render');
    const toggleLive = () => { liveOpen.value = !liveOpen.value; try { localStorage.setItem('mc_live_open', liveOpen.value ? '1' : '0'); } catch {} };
    const loadLive = async () => { try { liveRaw.value = await api(`/api/projects/${project.value.id}/scenes-state`); } catch {} };
    watch(liveCurrent, async (n) => {         // a tela acompanha a cena em produção
      if (!n || !liveFollow.value || !liveOpen.value) return;
      await nextTick();
      const el = document.getElementById(`ls-${n}`), box = document.querySelector('.live-script');
      if (el && box) box.scrollTo({ top: Math.max(0, el.offsetTop - box.clientHeight / 3), behavior: 'smooth' });
    });
    const canRunAll = computed(() => {
      const p = project.value;
      return !!p && !p.busy && p.scenes.length > 0 && ['planned', 'storyboard'].includes(p.status) && !outdatedImg.value.length && !outdatedAud.value.length
        && !(schedule.value && schedule.value.status === 'running');
    });
    const runAll = () => {
      const e = estimate.value;
      const total = e ? (e.seconds.prepare || 0) + e.seconds.render : 0;
      if (total > 600 && !confirm(`Isso deve levar ${e.human.prepare && e.seconds.prepare ? e.human.prepare + ' para preparar e ' : ''}${e.human.render} para criar o vídeo, e usa a GPU da andes o tempo todo.\n\nPare o AudioGlifo antes. Pode continuar?`)) return;
      return guard(async () => {
        await api(`/api/projects/${project.value.id}/run-all`, { method: 'POST' });
        say('Combinado: a andes cuida de tudo. Pode fechar esta página, ou até desligar o seu computador.');
        schedule.value = await api(`/api/projects/${project.value.id}/schedule`).catch(() => null);
        await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
      });
    };
    const silentList = async () => { if (route.value.name !== 'projects') return; try { projects.value = await api('/api/projects'); } catch {} };
    const miniPct = (j) => Math.round((j.progress || 0) * 100);

    // -------------------------------------------------------------- calendário da agenda
    const calTitle = computed(() => monthTitle(cal.mes));
    const calWeeks = computed(() => {           // grade de 6 semanas começando no domingo; some a última se for toda de outro mês
      const first = new Date(`${cal.mes}-01T12:00:00`);
      const start = new Date(first); start.setDate(1 - first.getDay());
      const days = [];
      for (let i = 0; i < 42; i++) { const d = new Date(start); d.setDate(start.getDate() + i); days.push(isoLocal(d)); }
      const rows = Array.from({ length: 6 }, (_, i) => days.slice(i * 7, i * 7 + 7));
      return rows[5].every((d) => monthOfIso(d) !== cal.mes) ? rows.slice(0, 5) : rows;
    });
    const calItems = computed(() => {           // itens do mês e dos vizinhos (dias de outro mês aparecem na grade), sem repetir
      const seen = new Map();
      for (const ym of [deslocarMes(cal.mes, -1), cal.mes, deslocarMes(cal.mes, 1)]) for (const e of calApi.itens(ym)) seen.set(e.id, e);
      return [...seen.values()];
    });
    const calByDay = computed(() => {           // um item que atravessa a meia-noite aparece nos dois dias
      const map = {};
      for (const e of calItems.value) {
        const a = new Date(e.inicio * 1000), b = new Date(Math.max(e.fim, e.inicio) * 1000);
        for (let d = new Date(a.getFullYear(), a.getMonth(), a.getDate(), 12); isoLocal(d) <= isoLocal(b); d.setDate(d.getDate() + 1)) (map[isoLocal(d)] ||= []).push(e);
      }
      for (const k in map) map[k].sort((x, y) => x.inicio - y.inicio);
      return map;
    });
    const eventsOfDay = (iso) => calByDay.value[iso] || [];
    const dayEvents = computed(() => eventsOfDay(cal.sel));
    const dayPages = computed(() => Math.max(1, Math.ceil(dayEvents.value.length / daySize.value)));
    const dayShown = computed(() => dayEvents.value.slice((dayPage.value - 1) * daySize.value, dayPage.value * daySize.value));
    const dayFrom = computed(() => (dayEvents.value.length ? (dayPage.value - 1) * daySize.value + 1 : 0));
    const dayTo = computed(() => Math.min(dayEvents.value.length, dayPage.value * daySize.value));
    const dayGo = (delta) => { dayPage.value = Math.min(dayPages.value, Math.max(1, dayPage.value + delta)); };
    watch(() => cal.sel, () => { dayPage.value = 1; });
    watch(daySize, () => { dayPage.value = 1; });
    const daySummary = computed(() => {
      const n = dayEvents.value.length;
      return n ? `${n} ${n === 1 ? 'item' : 'itens'} neste dia` : 'Nada agendado neste dia';
    });
    const dayAria = (iso) => { const n = eventsOfDay(iso).length; return `${new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' })}${n ? ', ' + n + (n === 1 ? ' item' : ' itens') : ''}`; };
    const calMove = (delta) => { cal.mes = deslocarMes(cal.mes, delta); };
    const calToday = () => { calHoje.value = isoLocal(new Date()); cal.mes = monthOfIso(calHoje.value); cal.sel = calHoje.value; };
    const selectDay = (iso) => { cal.sel = iso; if (monthOfIso(iso) !== cal.mes) cal.mes = monthOfIso(iso); };
    // linha do tempo do mês: cada item é uma faixa do início ao fim (estimado, se ainda não terminou)
    const tlRange = computed(() => { const [y, m] = cal.mes.split('-').map(Number); const a = new Date(y, m - 1, 1).getTime() / 1000; const b = new Date(y, m, 1).getTime() / 1000; return [a, b]; });
    const tlPos = (t) => Math.min(100, Math.max(0, ((t - tlRange.value[0]) / (tlRange.value[1] - tlRange.value[0])) * 100));
    const tlTicks = computed(() => { const days = Math.round((tlRange.value[1] - tlRange.value[0]) / 86400); return [1, 5, 10, 15, 20, 25, 30].filter((d) => d <= days).map((d) => ({ n: d, left: ((d - 1) / days) * 100 })); });
    const tlToday = computed(() => { const t = Date.now() / 1000; return t >= tlRange.value[0] && t < tlRange.value[1] ? tlPos(t) : null; });
    const tlLanes = computed(() => {
      const inMonth = calItems.value.filter((e) => e.fim >= tlRange.value[0] && e.inicio < tlRange.value[1])
        .map((e) => ({ ...e, left: tlPos(e.inicio), width: Math.max(0.9, tlPos(e.fim) - tlPos(e.inicio)) }));
      return [
        { name: 'Agendados e em andamento', items: inMonth.filter((e) => ['pending', 'running'].includes(e.status)) },
        { name: 'Já aconteceram', items: inMonth.filter((e) => !['pending', 'running'].includes(e.status)) },
      ];
    });
    const evTime = (e) => {
      const sameDay = isoLocal(new Date(e.inicio * 1000)) === isoLocal(new Date(e.fim * 1000));
      const end = `${sameDay ? '' : ddmm(e.fim) + ' '}${hhmm(e.fim)}`;
      return e.fim_estimado ? `${hhmm(e.inicio)} · termina por volta de ${end}` : `${hhmm(e.inicio)} até ${end}`;
    };
    const evTitle = (e) => `${CAL_STATUS[e.status] || e.status} · ${e.project_title || 'vídeo apagado'} · ${evTime(e)}`;
    async function calRefresh() { calApi.invalidar(); await Promise.all([calApi.carregar(cal.mes), loadAgenda()]); }
    const cancelCalEvent = (e) => confirm(`Cancelar o agendamento de "${e.project_title}"?`) && guard(async () => {
      await api(`/api/projects/${e.project_id}/schedule`, { method: 'DELETE' }); say('Agendamento cancelado'); await calRefresh();
    });
    const eligible = computed(() => projects.value.filter((p) => p.scene_count > 0));
    const ndlgProject = computed(() => projects.value.find((p) => p.id === ndlg.project_id) || null);
    const ndlgTs = computed(() => { const t = new Date(`${ndlg.date}T${ndlg.time || '00:00'}`).getTime() / 1000; return Number.isFinite(t) ? t : null; });
    const ndlgEnds = computed(() => (ndlgTs.value && ndlg.est ? ndlgTs.value + ndlg.est.seconds.prepare + ndlg.est.seconds.render : null));
    async function openNew(iso) {
      if (!projects.value.length) await loadProjects();
      const today = isoLocal(new Date()), now = new Date();
      ndlg.date = iso < today ? today : iso; ndlg.error = ''; ndlg.est = null;
      ndlg.time = ndlg.date === today && now.getHours() >= 22 ? `${p2((now.getHours() + 1) % 24)}:00` : '23:00';
      ndlg.project_id = eligible.value[0]?.id || '';
      ndlg.open = true;
      if (ndlg.project_id) loadNdlgEstimate();
    }
    async function loadNdlgEstimate() { ndlg.est = null; if (!ndlg.project_id) return; try { ndlg.est = await api(`/api/projects/${ndlg.project_id}/estimate`); } catch {} }
    async function saveNew() {
      ndlg.error = '';
      if (!ndlg.project_id) { ndlg.error = 'Escolha um vídeo.'; return; }
      if (!ndlgTs.value || ndlgTs.value < Date.now() / 1000 + 30) { ndlg.error = 'Escolha uma data e hora no futuro.'; return; }
      try {
        await api(`/api/projects/${ndlg.project_id}/schedule`, { method: 'PUT', body: { run_at: ndlgTs.value } });
        ndlg.open = false; selectDay(ndlg.date); say(`Agendado para ${fmtWhen(ndlgTs.value)}`); await calRefresh(); await loadProjects();
      } catch (e) { ndlg.error = e.message; }
    }
    watch(() => cal.mes, (ym) => { if (route.value.name === 'agenda') calApi.carregar(ym); });

    // ------------------------------------------------------------ agendamento
    const SCHED_STATUS = { pending: 'pendente', running: 'em execução', done: 'concluído', failed: 'falhou', cancelled: 'cancelado', missed: 'perdido' };
    const fmtWhen = (ts) => new Date(ts * 1000).toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const pad2 = (n) => String(n).padStart(2, '0');
    const toLocalInput = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
    const nextAt = (hour) => { const d = new Date(); d.setHours(hour, 0, 0, 0); if (d.getTime() < Date.now() + 5 * 60000) d.setDate(d.getDate() + 1); return d; };
    const presets = computed(() => [{ h: 23, label: 'Noite' }, { h: 2, label: 'Madrugada' }, { h: 6, label: 'Manhã cedo' }].map((p) => {
      const d = nextAt(p.h); return { ...p, date: d, text: `${p.label} · ${d.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' })} ${pad2(p.h)}:00` };
    }));
    const dlgTs = computed(() => { const t = new Date(dlg.value).getTime() / 1000; return Number.isFinite(t) ? t : null; });
    const dlgEnds = computed(() => (dlgTs.value && estimate.value ? dlgTs.value + estimate.value.seconds.prepare + estimate.value.seconds.render : null));
    const minLocal = computed(() => toLocalInput(new Date(Date.now() + 60000)));
    function openSchedule() {
      const cur = schedule.value && schedule.value.status === 'pending' ? new Date(schedule.value.run_at * 1000) : nextAt(23);
      dlg.value = toLocalInput(cur); dlg.error = ''; dlg.open = true;
    }
    const pickPreset = (p) => { dlg.value = toLocalInput(p.date); };
    async function saveSchedule() {
      dlg.error = '';
      if (!dlgTs.value || dlgTs.value < Date.now() / 1000 + 30) { dlg.error = 'Escolha uma data e hora no futuro.'; return; }
      try {
        schedule.value = await api(`/api/projects/${project.value.id}/schedule`, { method: 'PUT', body: { run_at: dlgTs.value } });
        dlg.open = false; say(`Agendado para ${fmtWhen(dlgTs.value)}`); calApi.invalidar();
      } catch (e) { dlg.error = e.message; }
    }
    const cancelSchedule = () => confirm('Cancelar o agendamento deste vídeo?' + (schedule.value?.status === 'running' ? ' O job em andamento será interrompido.' : '')) && guard(async () => {
      schedule.value = await api(`/api/projects/${project.value.id}/schedule`, { method: 'DELETE' }); say('Agendamento cancelado'); calApi.invalidar();
      if (route.value.name === 'agenda') await calRefresh();
    });
    const loadAgenda = () => guard(async () => { agenda.value = await api('/api/schedules'); });
    const cancelFromAgenda = (sc) => confirm(`Cancelar o agendamento de "${sc.project_title}"?`) && guard(async () => { await api(`/api/projects/${sc.project_id}/schedule`, { method: 'DELETE' }); say('Agendamento cancelado'); await calRefresh(); });
    const activeSchedule = computed(() => schedule.value && ['pending', 'running'].includes(schedule.value.status) ? schedule.value : null);
    const stoppedSchedule = computed(() => schedule.value && ['failed', 'missed'].includes(schedule.value.status) ? schedule.value : null);
    const eta2 = (sc) => (sc.eta_seconds != null ? fmtWhen(sc.run_at + sc.eta_seconds) : null);

    // -------------------------------------------------------------- roteiro e voz
    async function saveScript() {
      await guard(async () => {
        const textChanged = edit.text.trim() !== project.value.text.trim();
        project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}`, { method: 'PUT', body: { title: edit.title, text: edit.text, voice: edit.voice, speed: edit.speed } })) };
        say(outdatedAud.value.length ? 'Salvo. As narrações atuais continuam com a voz antiga. No aviso, você pode voltar atrás.' : 'Roteiro salvo');
        if (textChanged && project.value.scenes.length && confirm('O texto mudou. Replanejar as cenas agora? (as cenas atuais e as edições serão perdidas)')) await planNow();
        await refresh(); await loadEstimate();
      });
    }
    async function playSample(voice, speed) {
      sample.busy = true;
      await guard(async () => {
        let j = await api('/api/voice-sample', { method: 'POST', body: { voice, speed } });
        while (['queued', 'running'].includes(j.status)) { await new Promise((r) => setTimeout(r, 700)); j = await api(`/api/jobs/${j.id}`); }
        if (j.status !== 'done') throw new Error(j.message);
        sample.url = `/media/${j.result.audio}?t=${Date.now()}`;
        await nextTick(); document.getElementById('sample-audio')?.play().catch(() => {});
      });
      sample.busy = false;
    }

    // --------------------------------------------------------------------- cenas
    // ---- legendas editáveis (só refaz as legendas do vídeo pronto, leva segundos)
    const cap = reactive({ items: [], edited: false, stale: false, total: 0, dirty: false, loaded: false });
    const capLoad = () => guard(async () => {
      const r = await api(`/api/projects/${project.value.id}/captions`);
      Object.assign(cap, { items: r.items, edited: r.edited, stale: r.stale_edit, total: r.total, dirty: false, loaded: true });
    });
    watch(() => project.value?.id, () => { cap.loaded = false; cap.items = []; cap.dirty = false; });
    const capPg = usePager(computed(() => cap.items), 20);
    const capTouch = () => { cap.dirty = true; };
    const capDel = (i) => { cap.items.splice(i, 1); cap.dirty = true; };
    const capApply = () => guard(async () => {
      const id = project.value.id;
      await api(`/api/projects/${id}/captions`, { method: 'PUT', body: { items: cap.items.map((x) => ({ start: Number(x.start), end: Number(x.end), text: x.text })) } });
      await api(`/api/projects/${id}/captions/apply`, { method: 'POST' });
      say('Gravando as legendas no vídeo…'); cap.dirty = false; await refresh(); job.value = (await api(`/api/projects/${id}/status`)).job; startPolling();
    });
    const capReset = () => guard(async () => {
      if (!confirm('Voltar às legendas automáticas? As suas edições serão apagadas.')) return;
      await api(`/api/projects/${project.value.id}/captions`, { method: 'DELETE' }); await capLoad();
      await api(`/api/projects/${project.value.id}/captions/apply`, { method: 'POST' });
      say('Gravando as legendas automáticas…'); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling();
    });
    const setPause = (s, v) => guard(async () => {
      Object.assign(s, await api(`/api/projects/${project.value.id}/scenes/${s.n}`, { method: 'PATCH', body: { pause: v === '' ? null : Number(v) } }));
      await refresh(); say('Pausa salva. Crie o vídeo de novo para ela valer (as animações prontas são reaproveitadas)');
    });
    const patchScene = (s, data) => guard(async () => { Object.assign(s, await api(`/api/projects/${project.value.id}/scenes/${s.n}`, { method: 'PATCH', body: data })); await loadEstimate(); });
    const animateScene = (s) => guard(async () => { await api(`/api/projects/${project.value.id}/scenes/${s.n}/animate`, { method: 'POST' }); say(`Animando a cena ${s.n}… Depois, crie o vídeo de novo para ele sair com esta animação`); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling(); });
    const regen = (s) => guard(async () => { await api(`/api/projects/${project.value.id}/scenes/${s.n}/regenerate`, { method: 'POST', body: { new_seed: true } }); say(`Regerando a cena ${s.n}…`); await refresh(); job.value = (await api(`/api/projects/${project.value.id}/status`)).job; startPolling(); });
    const sceneOp = (method, path, body) => guard(async () => { project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}/${path}`, { method, body })) }; view.open = null; await loadEstimate(); });
    const mergeNext = (s) => sceneOp('POST', `scenes/${s.n}/merge`).then(() => say('Cenas mescladas: a narração será refeita'));
    const removeScene = (s) => confirm(`Apagar a cena ${s.n}?`) && sceneOp('DELETE', `scenes/${s.n}`);
    const addScene = (s) => view.newText.trim() && sceneOp('POST', 'scenes', { after: s.n, text: view.newText }).then(() => say('Cena adicionada'));
    function splitScene(s) {
      const ta = document.getElementById(`ta-${s.n}`);
      const at = ta?.selectionStart ?? 0;
      if (at <= 0 || at >= (ta?.value.length || 0)) return say('Toque no texto, no ponto onde quer cortar, e tente de novo');
      return sceneOp('POST', `scenes/${s.n}/split`, { at }).then(() => say('Cena dividida'));
    }
    const savePrefs = (data) => guard(async () => {
      project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}`, { method: 'PUT', body: data })) }; await loadEstimate();
      if ('profile_id' in data && outdatedImg.value.length) say('Estilo trocado. As imagens atuais continuam como estão. No aviso, você pode voltar atrás.');
    });

    // ------------------------------------------------------------------- opções
    const saveOpts = () => guard(async () => {
      const body = { options: { transition: opts.transition, transition_seconds: opts.transition_seconds, music: { ...opts.music, file: opts.music.file || null } } };
      project.value = { ...project.value, ...(await api(`/api/projects/${project.value.id}`, { method: 'PUT', body })) };
      say('Opções salvas: valem na próxima renderização');
    });
    async function uploadMusic(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      await guard(async () => {
        const fd = new FormData(); fd.append('file', f);
        const r = await fetch('/api/music', { method: 'POST', body: fd, credentials: 'same-origin' });
        if (r.status === 401) { authNeeded.value = true; throw new Error('Digite a senha de acesso para continuar.'); }
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || r.statusText);
        await loadMusic(); opts.music.file = j.name; say('Música enviada');
      });
      ev.target.value = '';
    }
    const deleteMusic = (name) => confirm(`Apagar a música "${name}"?`) && guard(async () => { await api(`/api/music/${encodeURIComponent(name)}`, { method: 'DELETE' }); if (opts.music.file === name) opts.music.file = ''; await loadMusic(); });

    // ------------------------------------------------------------------ novo projeto
    async function createProject(auto = false) {
      if (scriptErrors.value.length && !confirm(`O roteiro tem ${scriptErrors.value.length} ponto(s) que as regras do canal não aceitam:\n\n• ${scriptErrors.value.map((x) => x.mensagem).join('\n• ')}\n\nCriar o vídeo mesmo assim?`)) return;
      if (auto === true && wordCount.value / 2.75 / 60 > 5 && !confirm(`Isso usa a GPU da andes por um bom tempo (cerca de ${estMinutes.value} min de vídeo). Pare o AudioGlifo antes. Pode continuar?`)) return;
      await guard(async () => {
        const body = { ...form, channel_id: newCtx.channel_id || null, plan_item: newCtx.channel_id ? newCtx.plan_item : null };
        const p = await api('/api/projects', { method: 'POST', body });
        newCtx.plan_item = null;
        Object.assign(form, { title: '', text: '' });
        if (auto === true) {
          await api(`/api/projects/${p.id}/run-all`, { method: 'POST' });
          say('Combinado: a andes monta o vídeo sozinha, do jeito que o canal pede. Pode fechar esta página.');
          go(`#/p/${p.id}`);
        } else {
          await api(`/api/projects/${p.id}/plan`, { method: 'POST' });
          go(`#/p/${p.id}/cenas`);
        }
      });
    }

    // -------------------------------------------------------------------- perfis
    const blank = () => ({ name: '', description: '', style_prompt: '', base_model: 'flux1-schnell-fp8', params: { width: 1344, height: 768, steps: 4, cfg: 1 }, motion: { animated_ratio: 0.35, clip_engine: 'ltx' }, finishing: { grade: 'none', grain: 0.1, vignette: 0.2 }, captions: { font: 'sans', color: '#FFFFFF' } });
    const editProfile = (p) => (editing.value = JSON.parse(JSON.stringify(p || blank())));
    async function saveProfile() {
      await guard(async () => {
        const p = editing.value;
        p.id && !p.builtin ? await api(`/api/profiles/${p.id}`, { method: 'PUT', body: p }) : await api('/api/profiles', { method: 'POST', body: { ...p, id: undefined, builtin: undefined } });
        editing.value = null; profiles.value = await api('/api/profiles'); say('Perfil salvo');
      });
    }
    const dupProfile = (p) => guard(async () => { await api(`/api/profiles/${p.id}/duplicate`, { method: 'POST', body: {} }); profiles.value = await api('/api/profiles'); say('Perfil duplicado'); });
    const delProfile = (p) => confirm(`Apagar o perfil "${p.name}"?`) && guard(async () => { await api(`/api/profiles/${p.id}`, { method: 'DELETE' }); profiles.value = await api('/api/profiles'); });
    async function testProfile(p) {
      await guard(async () => {
        let j = await api(`/api/profiles/${p.id}/test`, { method: 'POST', body: {} });
        testImages[p.id] = 'loading';
        while (['queued', 'running'].includes(j.status)) { await new Promise((r) => setTimeout(r, 1000)); j = await api(`/api/jobs/${j.id}`); }
        testImages[p.id] = j.status === 'done' ? `/media/${j.result.image}?v=${Date.now()}` : '';
        if (j.status !== 'done') error.value = j.message;
      });
    }

    // ---------------------------------------------------------------- autenticação
    const tokenMsg = ref(''); const tokenBusy = ref(false);
    async function mailToken() {
      tokenBusy.value = true; tokenMsg.value = '';
      try {
        const r = await fetch('/api/auth/send-token', { method: 'POST' });
        const j = await r.json().catch(() => ({}));
        tokenMsg.value = r.ok ? j.message : (j.detail || 'Não foi possível enviar o e-mail.');
      } catch { tokenMsg.value = 'Sem conexão com o servidor.'; } finally { tokenBusy.value = false; }
    }
    async function login() {
      document.cookie = `mc_token=${encodeURIComponent(tokenInput.value.trim())}; path=/; SameSite=Strict; Max-Age=31536000`;
      authNeeded.value = false; tokenInput.value = '';
      await onRoute();
    }

    // ------------------------------------------------------------------- rotas
    async function onRoute() {
      error.value = '';
      const r = route.value;
      clearInterval(listTimer); listTimer = null;
      if (r.name === 'projects') { stopPolling(); document.title = 'MisterClip'; await guard(loadBase); await loadProjects(); listTimer = setInterval(silentList, 4000); }
      else if (r.name === 'project') { if (!profiles.value.length) await guard(loadBase); if (project.value?.id !== r.id) await loadProject(r.id); }
      else if (r.name === 'agenda') { stopPolling(); document.title = 'Agenda · MisterClip'; calToday(); calApi.invalidar(); loadProjects(); await Promise.all([loadAgenda(), calApi.carregar(cal.mes)]); }
      else if (r.name === 'clip') { stopPolling(); document.title = 'Novo clipe · MisterClip'; await guard(loadBase); }
      else if (r.name === 'prompts') { stopPolling(); document.title = 'Modelos de prompt · MisterClip'; }
      else if (r.name === 'channels' || r.name === 'channel') { stopPolling(); document.title = 'Canais · MisterClip'; }
      else { stopPolling(); document.title = 'MisterClip'; await guard(loadBase); if (r.name === 'new' && !newCtx.channel_id && channels.value.length) newCtx.channel_id = channels.value[0].id; }
      window.scrollTo(0, 0);
    }
    const onHash = () => { route.value = parseHash(); };
    const onKey = (e) => { if (e.key === 'Escape') { editing.value = null; dlg.open = false; ndlg.open = false; } };
    // vigia lento: avisa a tela quando um agendamento começa a rodar sozinho (o polling rápido só roda com job ativo)
    let idleTimer = null;
    async function idleTick() {
      if (route.value.name === 'agenda') { calApi.atualizar(cal.mes); return loadAgenda(); }
      if (route.value.name !== 'project' || !project.value || timer) return;
      try {
        const st = await api(`/api/projects/${project.value.id}/status`);
        if (st.busy) { await refresh(); job.value = st.job; schedule.value = await api(`/api/projects/${project.value.id}/schedule`).catch(() => null); startPolling(); }
      } catch {}
    }
    onMounted(() => { window.addEventListener('hashchange', onHash); window.addEventListener('keydown', onKey); idleTimer = setInterval(idleTick, 20000); onRoute(); });
    onUnmounted(() => { clearInterval(idleTimer); clearInterval(listTimer); });
    watch(route, onRoute);
    onUnmounted(() => { window.removeEventListener('hashchange', onHash); window.removeEventListener('keydown', onKey); });

    return { ruleChecks, reviewScript, ytState, yt, sendYoutube, ytPriv, ytStatus, clipLyrics, saveLyrics, isClip, clipInfo, clipSections, shortsState, shortsLayout, shortsCount, genShorts, api, say, channels, chanFilter, newCtx, chanName, projectsShown, onNewVideo, outdatedImg, scriptParas, jobTitle, stageItems, stagePct, showLive, liveMap, liveCurrent, liveVoice, liveImage, liveClip, liveAnimated, liveDone, liveOpen, liveFollow, toggleLive, canRunAll, runAll, miniPct, JOB_TITLE, dayPage, daySize, dayPages, dayShown, dayFrom, dayTo, dayGo, outdatedAud, styleOutdated, styleChange, voiceChange, revertSel, styleName, keepStale, revertStyle, revertVoice, pub, ytEdit, thumbText, th, tagsChars, genMeta, genThumbs, saveMeta, pickThumb, applyThumbText, copy, voiceLabel, MOTION_OPTS, TRANSITION_OPTS, transLabel, FILTERS, nextHint, showTip, dismissTip, guide, calApi, cal, calHoje, calTitle, calWeeks, eventsOfDay, dayEvents, daySummary, dayAria, calMove, calToday, selectDay, tlTicks, tlToday, tlLanes, evTime, evTitle, cancelCalEvent, ndlg, eligible, ndlgProject, ndlgTs, ndlgEnds, openNew, loadNdlgEstimate, saveNew, hhmm, dayTitle, monthOfIso, WEEKDAYS, CAL_STATUS, CAL_KIND, schedule, agenda, dlg, presets, dlgTs, dlgEnds, minLocal, activeSchedule, stoppedSchedule, SCHED_STATUS, fmtWhen, eta2, openSchedule, pickPreset, saveSchedule, cancelSchedule, cancelFromAgenda, loadAgenda, route, cfg, profiles, projects, project, job, estimate, music, error, toast, loading, tokenInput, testImages, editing, form, edit, opts, sample, view,
      profileMap, step, wordCount, estMinutes, elapsed, eta, stopped, canAskNotifications, counts, filtered, visible, primary, authNeeded,
      STATUS, STEPS, fmt, dur, go, media, issues, toggleScene,
      planNow, replan, prepare, render, removeProject, cancelJob, retryJob, askNotifications, saveScript, playSample,
      tokenMsg, tokenBusy, mailToken, scenePg, projPg, capPg, agPg, shortPg, cap, capLoad, capTouch, capDel, capApply, capReset, setPause, patchScene, regen, animateScene, mergeNext, removeScene, addScene, splitScene, savePrefs, saveOpts, uploadMusic, deleteMusic, createProject, rulesInfo, scriptCheck, scriptErrors, formTouched,
      editProfile, saveProfile, dupProfile, delProfile, testProfile, login };
  },
  template: `
  <header class="top">
    <a class="brand" href="#/">MisterClip</a>
    <nav class="desk-nav" aria-label="Principal">
      <a href="#/" :aria-current="route.name==='projects'||route.name==='project' ? 'page' : null">Meus vídeos</a>
      <a href="#/novo" :aria-current="route.name==='new' ? 'page' : null">Novo vídeo</a>
      <a href="#/clipe" :aria-current="route.name==='clip' ? 'page' : null">Novo clipe</a>
 <a href="#/agenda" :aria-current="route.name==='agenda' ? 'page' : null">Agenda</a>
      <a href="#/canais" :aria-current="route.name==='channels'||route.name==='channel' ? 'page' : null">Canais</a>
      <a href="#/perfis" :aria-current="route.name==='profiles' ? 'page' : null">Estilos visuais</a>
      <a href="#/prompts" :aria-current="route.name==='prompts' ? 'page' : null">Prompts</a>
    </nav>
    <span class="mode" :class="cfg.mode">{{ cfg.mode === 'fake' ? 'modo teste' : cfg.mode }}</span>
    <a class="helpbtn" href="#/ajuda" aria-label="Ajuda: como o MisterClip funciona" title="Ajuda">?</a>
  </header>

  <div v-if="error" class="error" role="alert" @click="error=''">{{ error }}</div>
  <div v-if="toast" class="toast" role="status" aria-live="polite">{{ toast }}</div>

  <div v-if="authNeeded" class="modal" role="dialog" aria-modal="true" aria-labelledby="login-t">
    <form class="card editor" @submit.prevent="login">
      <h2 id="login-t">Acesso ao MisterClip</h2>
      <p class="muted">Digite a senha de acesso (o token). Ela fica guardada neste aparelho, então você só digita uma vez.</p>
      <label>Senha de acesso<input type="password" v-model="tokenInput" autocomplete="current-password" autofocus required></label>
      <button class="primary" type="submit">Entrar</button>
      <button type="button" class="linkbtn" :disabled="tokenBusy" @click="mailToken">{{ tokenBusy ? 'Enviando…' : 'Não tenho o token: enviar para o meu e-mail' }}</button>
      <p v-if="tokenMsg" class="muted" role="status">{{ tokenMsg }}</p>
    </form>
  </div>

  <main id="main" tabindex="-1">
  <!-- ===================== PROJETOS ===================== -->
  <section v-if="route.name==='projects'">
    <div class="row"><h1>Meus vídeos</h1><span class="row-tight"><a class="btn" href="#/clipe">+ Novo clipe</a><a class="btn primary" href="#/novo">+ Novo vídeo</a></span></div>
    <p v-if="loading" class="muted">Carregando…</p>
    <div v-else-if="!projects.length" class="card welcome">
      <h2>Bem-vindo ao MisterClip</h2>
      <p>Aqui você transforma um roteiro em vídeo, sem editar nada à mão. São 3 passos:</p>
      <ol class="how">
        <li><strong>Cole o roteiro</strong> e escolha o estilo das imagens.</li>
        <li><strong>O MisterClip cria a voz e uma imagem</strong> para cada cena. Você revisa e ajusta o que quiser.</li>
        <li><strong>Aprove</strong> e ele monta o vídeo. É só baixar.</li>
      </ol>
      <div class="actions"><a class="btn primary big" href="#/novo">Criar meu primeiro vídeo</a><a class="btn" href="#/ajuda">Ver como funciona</a></div>
    </div>
    <div v-if="channels.length > 1 && projects.length" class="chips" role="group" aria-label="Filtrar por canal">
      <button type="button" :class="{ on: !chanFilter }" @click="chanFilter = ''">Todos os canais</button>
      <button v-for="c in channels" :key="c.id" type="button" :class="{ on: chanFilter === c.id }" @click="chanFilter = c.id">{{ c.name }}</button>
    </div>
    <div class="list">
      <a v-for="p in projectsShown" :key="p.id" class="card item" :href="'#/p/'+p.id">
        <div class="itext"><strong>{{ p.title }}</strong><span v-if="p.meta && p.meta.kind === 'clip'" class="badge clipbadge">🎵 clipe musical</span>
          <span class="next">{{ nextHint(p) }}</span>
          <span v-if="p.active_job" class="mini" role="status"><span class="minibar"><i :style="{ width: miniPct(p.active_job) + '%' }"></i></span>{{ p.active_job.status === 'queued' ? 'Na fila' : JOB_TITLE[p.active_job.kind] }} · {{ miniPct(p.active_job) }}%</span>
          <span class="muted">{{ profileMap[p.profile_id]?.name || p.profile_id }} · {{ p.scene_count }} cenas<template v-if="channels.length > 1 && chanName(p.channel_id)"> · {{ chanName(p.channel_id) }}</template></span></div>
        <span class="stack"><span class="badge" :class="p.status">{{ STATUS[p.status] || p.status }}</span>
          <span v-if="p.schedule" class="badge sched">⏰ {{ fmtWhen(p.schedule.run_at) }}</span></span>
      </a>
    </div>
    <pager :pg="projPg" label="Páginas dos vídeos"></pager>
  </section>

  <!-- ===================== NOVO ===================== -->
  <clipe-novo v-if="route.name==='clip' && profiles.length" :api="api" :say="say" :profiles="profiles" :channels="channels" :default-channel="newCtx.channel_id || (channels[0] && channels[0].id) || ''"></clipe-novo>

  <section v-if="route.name==='new'" class="newform">
    <p class="muted">Vai fazer um clipe para uma música? <a href="#/clipe">Use o Novo clipe musical</a>.</p>
    <h1>Novo vídeo</h1>
    <p class="lead">Cole o roteiro, escolha o estilo das imagens e toque em <strong>Criar</strong>. O resto o MisterClip faz.</p>
    <div v-if="showTip('novo')" class="tip"><span>💡 Cole o texto exatamente como ele será narrado. Para escolher você mesmo onde as cenas se dividem, coloque uma linha só com <code>[CENA]</code> entre os trechos.</span><button @click="dismissTip('novo')">Entendi</button></div>
    <label v-if="channels.length > 1">Canal<select v-model="newCtx.channel_id"><option v-for="c in channels" :key="c.id" :value="c.id">{{ c.name }}</option></select><small class="hint">O vídeo entra neste canal.</small></label>
    <p v-if="newCtx.plan_item" class="hint">Este vídeo será ligado ao item do calendário do canal.</p>
    <label>1. Título do vídeo<input v-model="form.title" placeholder="Ex.: O Grande Arcano" autocomplete="off"><small class="hint">Serve só para você se organizar.</small></label>
    <label>2. Roteiro (o texto que será narrado)
      <textarea v-model="form.text" rows="10" placeholder="Cole aqui o texto da narração…"></textarea>
      <small class="hint">{{ wordCount }} palavras ≈ {{ estMinutes }} min de vídeo.</small></label>
    <div v-if="scriptCheck" class="card rulecheck" aria-live="polite">
      <strong>Verificação do roteiro pelas regras do canal</strong>
      <p class="hint">O MisterClip não muda o seu texto: só avisa o que foge das regras.</p>
      <ul class="checks"><li v-for="a in scriptCheck.achados" :key="a.regra" :class="'lv-' + a.nivel"><span>{{ a.nivel === 'ok' ? '✅' : a.nivel === 'erro' ? '⛔' : '⚠️' }}</span> {{ a.mensagem }} <small v-if="a.como_corrigir" class="muted">{{ a.como_corrigir }}</small></li></ul>
    </div>
    <div v-if="rulesInfo" class="card premises">
      <strong>O que o canal já decidiu para este vídeo</strong>
      <p class="hint">Voz, estilo, ritmo das cenas, animação, música, legendas, título, descrição, miniatura e Shorts seguem o plano do canal. Para mudar, edite “Regras do canal” na aba Plano do canal.</p>
      <ul class="premise-list">
        <li>Voz: {{ voiceLabel(rulesInfo.regras.narracao.voz) }}, velocidade {{ rulesInfo.regras.narracao.velocidade }}</li>
        <li>Uma cena a cada ~{{ rulesInfo.regras.video.segundos_por_cena }} s, {{ Math.round(rulesInfo.regras.video.proporcao_animada * 100) }}% delas animadas</li>
        <li>Legendas: {{ rulesInfo.regras.video.legendas ? 'sim' : 'não' }} · Música: {{ rulesInfo.regras.video.musica.arquivo ? 'a do canal' : 'nenhuma' }}</li>
        <li>Depois do vídeo: {{ (rulesInfo.regras.video.apos_renderizar || []).length ? 'título, miniatura e Shorts, conforme o plano' : 'nada automático' }}</li>
      </ul>
    </div>
    <fieldset class="gallery-set"><legend>3. Estilo das imagens</legend>
      <p class="hint">O estilo define a aparência de todas as imagens. Você poderá trocar depois, cena por cena.</p>
      <div class="gallery">
        <label v-for="p in profiles" :key="p.id" class="card pick" :class="{sel: form.profile_id===p.id}">
          <input type="radio" name="perfil" v-model="form.profile_id" :value="p.id" @change="formTouched.profile = true">
          <img v-if="p.preview" :src="'/'+p.preview" :alt="'Exemplo do estilo '+p.name" loading="lazy">
          <strong>{{ p.name }}</strong><span class="muted">{{ p.description }}</span>
        </label>
      </div>
    </fieldset>
    <div class="grid2">
      <label>4. Voz da narração<select v-model="form.voice" @change="formTouched.voice = true"><option v-for="v in cfg.voices" :key="v" :value="v">{{ voiceLabel(v) }}</option></select></label>
      <label>Velocidade da fala<input type="number" step="0.05" min="0.6" max="1.3" v-model.number="form.speed" inputmode="decimal" @input="formTouched.speed = true"><small class="hint">0,85 é um ritmo calmo de narração; 1,0 é fala normal.</small></label>
    </div>
    <div class="row-tight"><button :disabled="sample.busy" @click="playSample(form.voice, form.speed)">{{ sample.busy ? 'Gerando amostra…' : '▶ Ouvir esta voz' }}</button>
      <audio v-if="sample.url" id="sample-audio" :src="sample.url" controls></audio></div>
  </section>

  <!-- ===================== PROJETO ===================== -->
  <section v-if="route.name==='project'">
    <p v-if="!project" class="muted">Carregando…</p>
    <template v-else>
      <div class="phead">
        <a class="back" href="#/">← Meus vídeos</a>
        <div class="ptitle"><h1>{{ project.title }}</h1>
          <span class="badge" :class="project.status">{{ STATUS[project.status] || project.status }}</span></div>
        <details class="menu"><summary aria-label="Mais opções">⋯</summary>
          <div class="menubox"><button :disabled="project.busy" @click="replan">{{ isClip ? 'Planejar o clipe de novo' : 'Dividir o roteiro em cenas de novo' }}</button>
            <button class="danger" :disabled="project.busy" @click="removeProject">Apagar este vídeo</button></div></details>
      </div>
      <p class="muted pmeta">{{ profileMap[project.profile_id]?.name }} · <template v-if="isClip">clipe musical<template v-if="clipInfo.analise"> · {{ Math.round(clipInfo.analise.bpm) }} batidas por minuto</template></template><template v-else>voz {{ voiceLabel(project.voice) }}</template> · {{ project.scenes.length }} cenas<template v-if="project.meta.total_est_seconds"> · duração de cerca de {{ dur(project.meta.total_est_seconds) }}</template></p>

      <div v-if="guide" class="guide" :class="guide.tone" role="status"><span class="gicon" aria-hidden="true">{{ guide.icon }}</span><div><strong>{{ guide.title }}</strong><p>{{ guide.text }}</p></div></div>

      <section v-if="project.busy && job" class="card prog" role="status" aria-live="polite">
        <div class="prog-head"><strong>{{ jobTitle }}</strong>
          <span class="muted">{{ job.status === 'queued' ? 'aguardando a vez na andes' : Math.round(job.progress * 100) + '% · ' + dur(elapsed) + (eta !== null ? ' · faltam ~' + dur(eta) : '') }}</span></div>
        <div class="bar"><div :style="{ width: Math.round(job.progress * 100) + '%' }"></div></div>
        <ul v-if="stageItems.length" class="stages">
          <li v-for="it in stageItems" :key="it.key" :class="it.state">
            <div class="stline"><span class="stico" aria-hidden="true">{{ it.state === 'done' ? '✓' : it.state === 'running' ? '●' : '○' }}</span>
              <span class="stname">{{ it.label }}</span><span class="stcount">{{ it.total ? it.done + ' de ' + it.total : 'não precisa' }}</span></div>
            <div class="bar sm"><div :style="{ width: stagePct(it) + '%' }"></div></div>
          </li>
        </ul>
        <p class="hint">{{ job.message }}</p>
      </section>

      <section v-if="showLive" class="card live">
        <div class="live-head"><strong>{{ job.kind === 'plan' ? 'O roteiro' : 'Roteiro em produção' }}</strong>
          <span class="live-tools"><label v-if="job.kind !== 'plan'" class="check small"><input type="checkbox" v-model="liveFollow"> Acompanhar</label>
            <button type="button" class="linkbtn" @click="toggleLive">{{ liveOpen ? 'Recolher' : 'Mostrar' }}</button></span></div>
        <template v-if="liveOpen">
          <div v-if="job.kind === 'plan'" class="live-script plain"><p v-for="(par, i) in scriptParas" :key="i">{{ par }}</p></div>
          <div v-else class="live-script" role="list">
            <p v-for="s in project.scenes" :key="s.id || s.n" :id="'ls-' + s.n" role="listitem" class="lsc" :class="{ cur: liveCurrent === s.n, ok: liveDone(s.n) }">
              <span class="ln">{{ s.n }}</span>
              <span class="ltxt">{{ s.text }}</span>
              <span class="lchips" aria-hidden="true"><span v-if="!isClip" :class="{ on: liveVoice(s.n) }" title="Voz">🎙</span><span :class="{ on: liveImage(s.n) }" title="Imagem">🖼</span><span v-if="liveAnimated(s.n)" :class="{ on: liveClip(s.n) }" title="Animação">🎞</span></span>
            </p>
          </div>
          <p v-if="job.kind !== 'plan'" class="hint">{{ isClip ? '' : '🎙 voz e tempos · ' }}🖼 imagem · 🎞 animação. A cena em produção fica destacada.</p>
        </template>
      </section>

      <div v-if="canRunAll" class="card autorun">
        <div><strong>Prefere não esperar?</strong><p class="muted">O MisterClip prepara o que falta e já cria o vídeo, sem parar para você revisar. Pode fechar a página ou desligar o seu computador: a andes termina tudo.</p></div>
        <button type="button" :disabled="project.busy" @click="runAll">Fazer tudo agora<small v-if="estimate"> · {{ estimate.human.total }}</small></button>
      </div>

      <div v-if="outdatedImg.length" class="card stale" role="alert">
        <strong>⚠ {{ outdatedImg.length }} {{ outdatedImg.length === 1 ? 'imagem está desatualizada' : 'imagens estão desatualizadas' }}</strong>
        <p v-if="styleChange">Você mudou o estilo de “{{ styleName(styleChange.from) }}” para “{{ styleName(styleChange.to) }}”. As imagens atuais continuam no estilo antigo e <strong>nada foi apagado</strong>.</p>
        <p v-else>Você mudou algo que afeta {{ outdatedImg.length === 1 ? 'esta imagem' : 'estas imagens' }}. <strong>Nada foi apagado.</strong></p>
        <p class="hint">Escolha o que fazer:</p>
        <div v-if="styleOutdated" class="choice">
          <label class="inline">Voltar ao estilo <select v-model="revertSel"><option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
          <button :disabled="project.busy" @click="revertStyle">Voltar a este estilo</button>
          <small class="hint">Desfaz a troca e aceita as imagens que você já tem.</small></div>
        <div class="choice"><button :disabled="project.busy" @click="keepStale('image')">Manter as imagens atuais</button>
          <small class="hint">Continua com o estilo novo daqui para frente, sem refazer nada agora.</small></div>
        <div class="choice"><button class="primary" :disabled="project.busy" @click="prepare">Gerar as imagens de novo<small v-if="estimate && estimate.seconds.prepare"> · {{ estimate.human.prepare }}</small></button></div>
      </div>
      <div v-if="outdatedAud.length" class="card stale" role="alert">
        <strong>⚠ {{ outdatedAud.length }} {{ outdatedAud.length === 1 ? 'narração está desatualizada' : 'narrações estão desatualizadas' }}</strong>
        <p>Você mudou a voz ou a velocidade da fala. As narrações atuais continuam com a voz antiga e <strong>nada foi apagado</strong>.</p>
        <p class="hint">Escolha o que fazer:</p>
        <div v-if="voiceChange" class="choice"><button :disabled="project.busy" @click="revertVoice">Voltar à voz anterior ({{ voiceLabel(voiceChange.from_voice) }}, velocidade {{ voiceChange.from_speed }})</button>
          <small class="hint">Desfaz a troca e aceita as narrações que você já tem.</small></div>
        <div class="choice"><button :disabled="project.busy" @click="keepStale('audio')">Manter as narrações atuais</button>
          <small class="hint">Continua com a voz nova daqui para frente, sem refazer nada agora.</small></div>
        <div class="choice"><button class="primary" :disabled="project.busy" @click="prepare">Gerar as narrações de novo<small v-if="estimate && estimate.seconds.prepare"> · {{ estimate.human.prepare }}</small></button></div>
      </div>

      <div v-if="activeSchedule" class="card sched" role="status">
        <strong>⏰ {{ activeSchedule.status==='running' ? 'Agendamento em andamento (' + (activeSchedule.step==='render' ? 'criando o vídeo' : 'preparando') + ')' : 'Agendado para ' + fmtWhen(activeSchedule.run_at) }}</strong>
        <span class="muted">Prepara o que faltar e cria o vídeo<template v-if="eta2(activeSchedule)"> · termina por volta de {{ eta2(activeSchedule) }}</template></span>
        <div class="actions"><button :disabled="activeSchedule.status==='running'" @click="openSchedule">Mudar horário</button>
          <button class="danger" @click="cancelSchedule">Cancelar agendamento</button></div>
      </div>
      <div v-else-if="stoppedSchedule" class="card sched bad" role="status">
        <strong>⏰ O último agendamento ({{ fmtWhen(stoppedSchedule.run_at) }}) {{ stoppedSchedule.status==='missed' ? 'não rodou a tempo' : 'falhou' }}</strong>
        <span class="muted">{{ stoppedSchedule.message }}</span>
        <div class="actions"><button @click="openSchedule">Agendar de novo</button></div>
      </div>

      <div class="steps" role="tablist" aria-label="Etapas do vídeo">
        <button v-for="(st, i) in STEPS" :key="st.id" role="tab" :aria-selected="step===st.id" :class="{on: step===st.id}" @click="go('#/p/'+project.id+'/'+st.id)">
          <span class="stn">{{ i+1 }}</span> {{ st.label }}
          <span v-if="st.id==='cenas' && counts.problemas" class="dot" :title="counts.problemas+' cenas pendentes'">{{ counts.problemas }}</span>
          <span v-if="st.id==='video' && project.status==='done'" class="okmark">✓</span>
        </button>
      </div>

      <!-- 1. ROTEIRO -->
      <div v-if="step==='roteiro' && isClip" class="panel clipinfo">
        <div class="card"><strong>A música</strong>
          <audio controls preload="none" :src="media(clipInfo.audio, 0)"></audio>
          <p class="muted">{{ clipInfo.arquivo }} · {{ fmt(clipInfo.seconds) }}<template v-if="clipInfo.analise"> · {{ Math.round(clipInfo.analise.bpm) }} batidas por minuto · {{ clipSections.length }} partes</template></p>
          <ul v-if="clipSections.length" class="tasks"><li v-for="(x, i) in clipSections" :key="i"><span class="tag">{{ fmt(x.start) }}</span> parte {{ x.nome }} · {{ x.len }} s</li></ul></div>
        <div v-if="clipInfo.historia" class="card"><strong>A história do clipe</strong>
          <p>{{ clipInfo.historia.resumo }}</p>
          <details><summary>Como o clipe vai parecer (usado para manter as imagens parecidas)</summary>
            <p class="hint"><b>Quem vive a história:</b> {{ clipInfo.historia.protagonista }}</p>
            <p class="hint"><b>Onde:</b> {{ clipInfo.historia.cenario }}</p>
            <p class="hint"><b>Cores e luz:</b> {{ clipInfo.historia.paleta }}</p>
            <ol class="how"><li v-for="(a, i) in clipInfo.historia.arco" :key="i"><b>{{ a.momento }}</b></li></ol></details></div>
        <div class="card"><strong>Letra</strong>
          <p class="hint">Revise a letra antes de gerar as imagens: ela decide a história e o que aparece em cada cena. Se mudar, o clipe é planejado de novo (as cenas e imagens atuais são refeitas).</p>
          <textarea v-model="clipLyrics" rows="12" :disabled="project.busy"></textarea>
          <div class="actions"><button class="primary" :disabled="project.busy || clipLyrics.trim() === (project.text || '').trim()" @click="saveLyrics">Salvar a letra e planejar o clipe de novo</button></div></div>
        <p class="hint">Para trocar a música, crie um novo clipe. Na aba Cenas você ajusta a imagem e o movimento de cada cena.</p>
      </div>
      <div v-if="step==='roteiro' && !isClip" class="panel">
        <label>Título<input v-model="edit.title" :disabled="project.busy"></label>
        <label>Roteiro (o texto que é narrado)<textarea v-model="edit.text" rows="12" :disabled="project.busy"></textarea></label>
        <div class="grid2">
          <label>Voz da narração<select v-model="edit.voice" :disabled="project.busy"><option v-for="v in cfg.voices" :key="v" :value="v">{{ voiceLabel(v) }}</option></select></label>
          <label>Velocidade da fala<input type="number" step="0.05" min="0.6" max="1.3" v-model.number="edit.speed" :disabled="project.busy" inputmode="decimal"><small class="hint">0,85 é calmo; 1,0 é fala normal.</small></label>
        </div>
        <div class="row-tight"><button :disabled="sample.busy" @click="playSample(edit.voice, edit.speed)">{{ sample.busy ? 'Gerando amostra…' : '▶ Ouvir esta voz' }}</button>
          <audio v-if="sample.url" id="sample-audio" :src="sample.url" controls></audio></div>
        <p class="muted">Mudar a voz ou a velocidade refaz só a narração. Mudar o texto pergunta se você quer dividir em cenas de novo.</p>
        <button class="primary" :disabled="project.busy" @click="saveScript">Salvar roteiro e voz</button>
      </div>

      <!-- 2. CENAS -->
      <div v-if="step==='cenas'" class="panel">
        <div v-if="showTip('cenas') && project.scenes.length" class="tip"><span>💡 Toque numa cena para abrir. Lá você edita o texto, troca o estilo, anima a imagem ou ouve a narração. Avisos em vermelho mostram o que ainda falta.</span><button @click="dismissTip('cenas')">Entendi</button></div>
        <div class="toolbar">
          <div class="chips" role="group" aria-label="Filtrar cenas">
            <button v-for="f in FILTERS" :key="f.id" :class="{on: view.filter===f.id}" :aria-pressed="view.filter===f.id" @click="view.filter=f.id">{{ f.label }} <b>{{ counts[f.id] }}</b></button>
          </div>
          <label class="inline">Estilo do vídeo
            <select :value="project.profile_id" :disabled="project.busy" @change="savePrefs({profile_id: $event.target.value})">
              <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
        </div>
        <p v-if="!project.scenes.length" class="muted">Ainda não há cenas. Toque em "Planejar cenas" na barra de baixo.</p>
        <p v-else-if="!filtered.length" class="muted">Nenhuma cena neste filtro.</p>

        <ol class="scenes">
          <li v-for="s in visible" :key="s.id || s.n" class="scene" :class="{open: view.open===s.n}">
            <button class="srow" :aria-expanded="view.open===s.n" @click="toggleScene(s.n)">
              <span class="thumb"><img v-if="s.thumb" :src="media(s.thumb, s.ver)" :alt="'Imagem da cena '+s.n" loading="lazy"><span v-else class="ph">–</span><span class="num">{{ s.n }}</span></span>
              <span class="stext"><span class="clamp">{{ s.text }}</span>
                <span class="tags"><span class="tag">{{ s.duration ? fmt(s.duration) : '~'+s.est_seconds+'s' }}</span>
                  <span v-if="s.motion!=='ken_burns'" class="tag anim">{{ s.clip ? 'animada ✓' : 'vai animar' }}</span>
                  <span v-for="i in issues(s)" :key="i" class="tag warn">{{ i }}</span></span></span>
            </button>

            <div v-if="view.open===s.n" class="editor-in">
              <label>{{ isClip ? 'Letra desta cena' : 'Texto da cena (é o que será narrado)' }}<textarea :id="'ta-'+s.n" rows="5" :value="s.text" :disabled="project.busy" @change="patchScene(s,{text:$event.target.value})"></textarea></label>
              <label>Descrição da imagem (em inglês)<textarea rows="3" :value="s.visual_prompt" :disabled="project.busy" @change="patchScene(s,{visual_prompt:$event.target.value})"></textarea>
                <small class="hint">É o que a IA vai desenhar. Em inglês os resultados são melhores. Depois de mudar, toque em "Gerar outra imagem".</small></label>
              <div class="grid2">
                <label>Estilo desta cena<select :value="s.profile_id||''" :disabled="project.busy" @change="patchScene(s,{profile_id:$event.target.value})">
                  <option value="">o mesmo do vídeo</option><option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
                <label>Efeito da imagem<select :value="s.motion" :disabled="project.busy" @change="patchScene(s,{motion:$event.target.value})">
                  <option v-for="m in MOTION_OPTS" :key="m[0]" :value="m[0]">{{ m[1] }}</option></select>
                  <small class="hint">Animar dá vida à imagem, mas demora mais.</small></label>
              </div>
              <label v-if="!isClip">Pausa depois da fala (segundos)<input type="number" step="0.1" min="0" max="3" inputmode="decimal" :value="s.pause ?? 0.45" :disabled="project.busy" @change="setPause(s, $event.target.value)">
                <small class="hint">Silêncio antes da próxima cena. Aumente para respirar depois de uma frase forte; reduza para acelerar. Vale ao criar o vídeo de novo.</small></label>
              <p v-if="s.image_warning" class="muted">⚠️ A imagem desta cena pode estar ruim: {{ s.image_warning }}. Toque em "Gerar outra imagem".</p>
              <div v-if="s.audio && !isClip" class="media-row"><span class="muted">Ouvir a narração</span><audio controls preload="none" :src="media(s.audio, s.ver)"></audio></div>
              <div v-if="s.clip" class="media-row"><span class="muted">Ver a animação</span><video controls preload="none" muted playsinline :src="media(s.clip, s.ver)"></video></div>
              <p v-if="s.clip_error" class="muted">A animação desta cena não deu certo, então ela usa um zoom suave. Dá para tentar de novo ao criar o vídeo.</p>
              <div class="actions">
                <button v-if="s.image && s.dirty_image" :disabled="project.busy" @click="keepStale('image', [s.n])">Manter esta imagem</button>
                <button :disabled="project.busy" @click="regen(s)">Gerar outra imagem</button>
                <button v-if="s.motion!=='ken_burns' && !s.clip && s.image && !s.dirty_image" class="primary" :disabled="project.busy" @click="animateScene(s)">Gerar a animação desta cena</button>
                <button v-if="s.motion!=='ken_burns' && s.clip" :disabled="project.busy" @click="patchScene(s,{redo_clip:true}).then(() => say('Pronto: esta animação será refeita quando você criar o vídeo de novo'))">Refazer a animação</button>
                <small v-if="s.motion!=='ken_burns' && s.clip" class="hint">Se o movimento ficou estranho, refaça a animação ou troque o efeito para "Zoom suave".</small>
                <button v-if="!isClip" :disabled="project.busy" @click="splitScene(s)">Dividir no cursor</button>
                <button v-if="!isClip" :disabled="project.busy || s.n===project.scenes.length" @click="mergeNext(s)">Juntar com a próxima</button>
                <button v-if="!isClip" class="danger" :disabled="project.busy || project.scenes.length<2" @click="removeScene(s)">Apagar cena</button>
              </div>
              <details v-if="!isClip" class="addbox"><summary>Adicionar uma cena depois desta</summary>
                <textarea rows="3" v-model="view.newText" placeholder="Texto da nova cena…" :disabled="project.busy"></textarea>
                <button :disabled="project.busy || !view.newText.trim()" @click="addScene(s)">Adicionar cena</button></details>
            </div>
          </li>
        </ol>
        <pager :pg="scenePg" label="Páginas das cenas"></pager>
      </div>

      <!-- 3. AJUSTES -->
      <div v-if="step==='opcoes'" class="panel">
        <p class="muted">Estes ajustes valem na próxima vez que você criar o vídeo.</p>
        <div class="grid2">
          <label>Como uma cena troca para a próxima
            <select v-model="opts.transition"><option v-for="t in TRANSITION_OPTS" :key="t[0]" :value="t[0]">{{ t[1] }}</option></select></label>
          <label>Duração da transição (segundos)<input type="number" step="0.1" min="0.2" max="2" v-model.number="opts.transition_seconds" :disabled="opts.transition==='cut'" inputmode="decimal"></label>
        </div>
        <p v-if="isClip" class="hint">O áudio do clipe é a música que você enviou. Não há música de fundo para escolher.</p>
        <div v-if="!isClip" class="grid2">
          <label>Música de fundo (opcional)
            <select v-model="opts.music.file"><option value="">sem música</option>
              <option v-for="m in music" :key="m.name" :value="m.name">{{ m.name }} ({{ fmt(m.seconds) }})</option></select></label>
          <label>Enviar uma música<input type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" @change="uploadMusic"><small class="hint">mp3, wav, m4a, ogg ou flac. Use só músicas que você tem direito de usar.</small></label>
        </div>
        <div v-if="opts.music.file && !isClip" class="musicbox">
          <audio :src="'/media/music/'+encodeURIComponent(opts.music.file)" controls preload="none"></audio>
          <label>Volume da música: {{ Math.round(opts.music.volume*100) }}%<input type="range" min="0" max="1" step="0.05" v-model.number="opts.music.volume"></label>
          <label class="check"><input type="checkbox" v-model="opts.music.duck"> Baixar o volume da música automaticamente quando alguém fala</label>
          <button class="danger" @click="deleteMusic(opts.music.file)">Apagar esta música</button>
        </div>
        <div class="actions"><button class="primary" :disabled="project.busy" @click="saveOpts">Salvar ajustes</button></div>
      </div>

      <!-- 4. VÍDEO -->
      <div v-if="step==='video'" class="panel">
        <div v-if="project.status==='done'" class="video">
          <video :src="'/media/'+project.id+'/final.mp4?v='+project.updated" controls playsinline></video>
          <a class="btn primary" :href="'/api/projects/'+project.id+'/download'">Baixar o vídeo (MP4, {{ fmt(project.meta.total_seconds) }} min)</a>
          <p v-if="project.meta.rendered_with" class="muted">Transição usada: {{ transLabel(project.meta.rendered_with.transition==='cut' ? 'cut' : project.meta.rendered_with.transition) }} · música: {{ project.meta.rendered_with.music ? 'sim' : 'não' }}</p>
        </div>
        <p v-else class="muted">Ainda não há vídeo. Revise as cenas e toque em "Aprovar e criar o vídeo" na barra de baixo.</p>
        <div v-if="project.status==='done' && project.meta.render_stale" class="card rulecheck" role="status">
          <strong>⚠️ O vídeo mostrado não tem as pausas novas</strong>
          <p class="hint">Você mudou a pausa de uma cena. Toque em "Aprovar e criar o vídeo" na barra de baixo: as animações já feitas são reaproveitadas, então leva poucos minutos. Só depois disso dá para editar as legendas.</p>
        </div>
        <details v-if="project.status==='done'" class="card capedit" @toggle="$event.target.open && !cap.loaded && capLoad()">
          <summary><strong>Editar as legendas</strong> <span class="muted">corrigir uma palavra, juntar ou separar linhas, ajustar o tempo</span></summary>
          <p class="hint">Mexe só nas legendas do vídeo pronto: a narração e as animações não são refeitas e leva alguns segundos. O seu roteiro original não muda.</p>
          <p v-if="cap.stale" class="muted">⚠️ As suas edições antigas não valem mais, porque a duração do vídeo mudou. Abaixo estão as legendas automáticas atuais.</p>
          <p v-if="cap.edited" class="muted">Estas são legendas editadas por você.</p>
          <div v-if="cap.loaded" class="caplist">
            <div v-for="(c, i) in capPg.items" :key="capPg.from + i" class="caprow">
              <input type="number" step="0.1" min="0" inputmode="decimal" v-model.number="c.start" :aria-label="'Início da linha ' + (i + 1) + ' (s)'" @input="capTouch" :disabled="project.busy">
              <input type="number" step="0.1" min="0" inputmode="decimal" v-model.number="c.end" :aria-label="'Fim da linha ' + (i + 1) + ' (s)'" @input="capTouch" :disabled="project.busy">
              <input type="text" maxlength="160" v-model="c.text" :aria-label="'Texto da linha ' + (i + 1)" @input="capTouch" :disabled="project.busy">
              <button type="button" class="danger" :aria-label="'Apagar a linha ' + (i + 1)" :disabled="project.busy" @click="capDel(capPg.from - 1 + i)">✕</button>
            </div>
            <pager :pg="capPg" label="Páginas das legendas"></pager>
            <div class="actions">
              <button class="primary" :disabled="project.busy || !cap.dirty || project.meta.render_stale" @click="capApply">Gravar as legendas no vídeo</button>
              <button :disabled="project.busy || !(cap.edited || cap.stale)" @click="capReset">Voltar às automáticas</button>
              <small class="hint">Início e fim em segundos, a partir do começo do vídeo ({{ cap.items.length }} linhas, {{ fmt(cap.total) }} min).</small>
            </div>
          </div>
          <p v-else class="muted">Carregando as legendas…</p>
        </details>
      </div>
      <!-- 5. PUBLICAR -->
      <div v-if="step==='publicar'" class="panel">
        <div class="guide"><span class="gicon" aria-hidden="true">📤</span><div><strong>Prepare a publicação no YouTube</strong><p>O MisterClip sugere o título, a descrição (com capítulos) e as tags, e cria a miniatura. Você revisa e, no fim desta página, envia direto ao YouTube (com o canal conectado) ou copia e cola no YouTube Studio.</p></div></div>

        <h2 class="sec">Título, descrição e tags</h2>
        <div class="card rulecheck" v-if="ruleChecks">
          <strong>Regras do canal</strong>
          <p class="hint">{{ ruleChecks.pode_enviar ? 'Nada aqui impede o envio.' : 'Há erros que barram o envio automático ao YouTube. Corrija-os, ou envie mesmo assim por sua conta.' }}</p>
          <ul class="checks"><li v-for="a in ruleChecks.achados" :key="a.regra + a.mensagem" :class="'lv-' + a.nivel"><span>{{ a.nivel === 'ok' ? '✅' : a.nivel === 'erro' ? '⛔' : '⚠️' }}</span> {{ a.mensagem }} <small v-if="a.como_corrigir" class="muted">{{ a.como_corrigir }}</small></li></ul>
          <div class="actions"><button :disabled="project.busy" @click="reviewScript">Revisar o roteiro com a IA</button></div>
          <details v-if="project.meta && project.meta.review" class="adv" open><summary>Revisão do roteiro</summary>
            <p>{{ project.meta.review.veredito }}</p>
            <p v-if="project.meta.review.tese"><strong>Tese:</strong> {{ project.meta.review.tese }}</p>
            <ul v-if="project.meta.review.riscos && project.meta.review.riscos.length"><li v-for="(r, i) in project.meta.review.riscos" :key="i"><strong>{{ r.trecho }}</strong>: {{ r.problema }} <em>{{ r.sugestao }}</em></li></ul>
            <ul v-if="project.meta.review.pontos_de_saida && project.meta.review.pontos_de_saida.length"><li v-for="(r, i) in project.meta.review.pontos_de_saida" :key="'s' + i">Perto de {{ r.aprox }}: {{ r.risco }} <em>{{ r.solucao }}</em></li></ul>
            <p v-if="project.meta.review.abertura_sugerida"><strong>Abertura sugerida:</strong> {{ project.meta.review.abertura_sugerida }}</p>
            <p v-if="project.meta.review.originalidade" class="hint">Originalidade {{ project.meta.review.originalidade.nota }}/5: {{ project.meta.review.originalidade.motivo }}</p>
            <p class="hint">É só uma sugestão: o seu roteiro não foi alterado.</p></details>
        </div>
        <div class="actions"><button class="primary" :disabled="project.busy" @click="genMeta">{{ pub && pub.youtube ? 'Gerar sugestões de novo' : 'Gerar sugestões' }}<small v-if="pub"> · {{ pub.estimate.metadata }}</small></button></div>
        <template v-if="pub && pub.youtube">
          <fieldset><legend>Título</legend>
            <p class="hint">Escolha uma sugestão ou escreva o seu.</p>
            <label v-for="t in pub.youtube.titles" :key="t" class="opt"><input type="radio" name="titulo" :value="t" v-model="ytEdit.title"> <span>{{ t }}</span></label>
            <label>Título escolhido ({{ ytEdit.title.length }}/100)<input v-model="ytEdit.title" maxlength="100"></label>
          </fieldset>
          <label>Introdução da descrição<textarea v-model="ytEdit.intro" rows="6"></textarea></label>
          <fieldset v-if="ytEdit.chapters.length"><legend>Capítulos</legend>
            <p class="hint">Os horários são calculados sozinhos a partir do vídeo. Edite só os nomes.</p>
            <div v-for="(c, i) in ytEdit.chapters" :key="c.scene" class="chrow"><span class="ts">{{ pub.chapters_resolved[i] ? pub.chapters_resolved[i].t : '—' }}</span><input v-model="c.title" maxlength="60" :aria-label="'Nome do capítulo ' + (i + 1)"></div>
          </fieldset>
          <p v-else class="muted">Capítulos: só são criados em vídeos a partir de uns 5 minutos (o YouTube pede pelo menos 3 capítulos de 10 segundos ou mais).</p>
          <label>Hashtags<input v-model="ytEdit.hashtags_text" placeholder="#filosofia #ocultismo #tecnologia"><small class="hint">As 3 primeiras aparecem acima do título no YouTube.</small></label>
          <label>Tags ({{ tagsChars }}/500 caracteres)<textarea v-model="ytEdit.tags_text" rows="3"></textarea><small class="hint">Separe por vírgula. Ajudam o YouTube a entender o assunto.</small></label>
          <div class="actions"><button class="primary" :disabled="project.busy" @click="saveMeta">Salvar alterações</button></div>
          <details class="adv" open><summary>Descrição final (é isto que vai para o YouTube)</summary>
            <pre class="final">{{ pub.description_final }}</pre><p class="hint">Salve as alterações para atualizar esta prévia.</p></details>
          <div class="actions"><button @click="copy(ytEdit.title, 'Título copiado')">Copiar título</button><button @click="copy(pub.description_final, 'Descrição copiada')">Copiar descrição</button><button @click="copy(pub.youtube.tags.join(', '), 'Tags copiadas')">Copiar tags</button></div>
        </template>

        <h2 class="sec">Miniatura</h2>
        <p class="muted">É a imagem que aparece antes de o vídeo abrir. Criamos 3 opções com o texto por cima, no tamanho que o YouTube pede (1280×720, até 2 MB).</p>
        <div class="actions"><button class="primary" :disabled="project.busy" @click="genThumbs">{{ th ? 'Gerar novas miniaturas' : 'Gerar miniaturas' }}<small v-if="pub"> · {{ pub.estimate.thumbnail }}</small></button></div>
        <template v-if="th">
          <div class="thumbs" role="radiogroup" aria-label="Opções de miniatura">
            <button v-for="v in th.variants" :key="v.i" class="thumbopt" :class="{sel: th.selected===v.i}" role="radio" :aria-checked="th.selected===v.i" @click="pickThumb(v.i)">
              <img :src="media(v.file, th.ver)" :alt="'Opção de miniatura ' + v.i"><span>{{ th.selected===v.i ? '✓ Escolhida' : 'Escolher' }}</span></button>
          </div>
          <label>Texto na miniatura<input v-model="thumbText" maxlength="40"><small class="hint">Poucas palavras funcionam melhor. Toque em "Aplicar texto" para atualizar a miniatura escolhida.</small></label>
          <div class="actions"><button :disabled="project.busy" @click="applyThumbText">Aplicar texto</button><a class="btn primary" :href="'/api/projects/'+project.id+'/thumbnail/download'">Baixar miniatura (JPG)</a></div>
        </template>

        <h2 class="sec">YouTube</h2>
        <template v-if="ytState">
          <p v-if="!ytState.conectado" class="muted">Para enviar o vídeo direto ao YouTube, conecte o canal na aba <a :href="'#/canal/' + project.channel_id + '/youtube'">YouTube do canal</a>.</p>
          <template v-else>
            <p class="muted">Envia o vídeo, o título, a descrição, as tags e a miniatura escolhida. Vídeos de projetos de API ainda não auditados pelo Google ficam privados: publique com um toque no YouTube Studio.</p>
            <div v-if="!ytState.envios.some((u) => u.status !== 'erro')" class="grid2">
              <label>Como enviar<select v-model="yt.privacidade"><option v-for="(t, k) in ytPriv" :key="k" :value="k">{{ t }}</option></select></label>
              <label v-if="yt.privacidade === 'agendado'">Data e hora (horário do Brasil)<input type="datetime-local" v-model="yt.publish_at"><small class="hint">Pelo menos 20 minutos à frente.</small></label>
            </div>
            <label v-if="!ytState.envios.some((u) => u.status !== 'erro')" class="check"><input type="checkbox" v-model="yt.sintetico"> Marcar como conteúdo alterado ou sintético</label>
            <div v-if="!ytState.envios.some((u) => u.status !== 'erro')" class="actions"><button class="primary" :disabled="project.busy || (yt.privacidade === 'agendado' && !yt.publish_at)" @click="sendYoutube">Enviar ao YouTube</button></div>
            <ul v-if="ytState.envios.length" class="vlist"><li v-for="u in ytState.envios" :key="u.id" class="vrow"><p class="vtitle">{{ ytStatus[u.status] || u.status }}<template v-if="u.video_id"> · <a :href="'https://youtu.be/' + u.video_id" target="_blank" rel="noopener noreferrer">abrir no YouTube</a></template></p>
              <p v-if="u.warning" class="hint">{{ u.warning }}</p><p v-if="u.error" class="error-line">{{ u.error }}</p></li></ul>
          </template>
        </template>

        <h2 class="sec">Shorts</h2>
        <p class="muted">Cortes verticais de 30 a 45 segundos tirados deste vídeo, para atrair gente nova ao vídeo completo. O MisterClip escolhe os trechos mais fortes e monta cada Short com legenda grande e uma frase de gancho no topo.</p>
        <div class="grid2">
          <label>Quantos Shorts<select v-model.number="shortsCount"><option :value="1">1</option><option :value="2">2</option><option :value="3">3</option><option :value="4">4</option><option :value="5">5</option></select></label>
          <label>Formato da imagem<select v-model="shortsLayout"><option v-for="(t, k) in (shortsState ? shortsState.layouts : { blur: 'Imagem inteira com fundo desfocado (recomendado)' })" :key="k" :value="k">{{ t }}</option></select></label>
        </div>
        <div class="actions"><button class="primary" :disabled="project.busy" @click="genShorts">{{ shortsState && shortsState.items.length ? 'Gerar os Shorts de novo' : 'Gerar Shorts' }}</button></div>
        <div v-if="shortsState && shortsState.items.length" class="shorts">
          <div v-for="s in shortPg.items" :key="s.i" class="card short">
            <video :src="media(s.file, shortsState.ver)" :poster="media(s.poster, shortsState.ver)" controls preload="none" playsinline></video>
            <div class="stext"><strong>Short {{ s.i }} · {{ Math.round(s.duration) }} s</strong>
              <p class="hint">Gancho no topo: “{{ s.hook }}”</p>
              <label>Título<input :value="s.title" readonly></label>
              <div class="actions"><a class="btn primary" :href="'/api/projects/' + project.id + '/shorts/' + s.i + '/download'">Baixar</a>
                <button @click="copy(s.title, 'Título copiado')">Copiar título</button><button @click="copy(s.description, 'Descrição copiada')">Copiar descrição</button></div></div>
          </div>
          <pager :pg="shortPg" label="Páginas dos Shorts"></pager>
          <p class="hint">Ao publicar cada Short no YouTube, use “Vídeo relacionado” e escolha este vídeo, e fixe um comentário com o título do vídeo completo. Mais ideias no plano de Shorts do canal.</p>
        </div>
      </div>
    </template>
  </section>

  <!-- ===================== PERFIS ===================== -->
  <section v-if="route.name==='profiles'">
    <div class="row"><h1>Estilos visuais</h1><button class="primary" @click="editProfile()">+ Novo estilo</button></div>
    <p class="lead">Um estilo define a aparência das imagens (cores, luz, técnica) e o acabamento do vídeo. Você escolhe um ao criar o vídeo e pode trocar depois, cena por cena.</p>
    <div class="gallery big">
      <div v-for="p in profiles" :key="p.id" class="card">
        <img v-if="testImages[p.id] && testImages[p.id]!=='loading'" :src="testImages[p.id]" :alt="'Exemplo do estilo '+p.name">
        <div v-else-if="testImages[p.id]==='loading'" class="ph" role="status">gerando exemplo…</div>
        <img v-else-if="p.preview" :src="'/'+p.preview" :alt="'Exemplo do estilo '+p.name" loading="lazy">
        <strong>{{ p.name }} <span v-if="p.builtin" class="badge">padrão</span></strong>
        <span class="muted">{{ p.description }}</span>
        <div class="actions">
          <button @click="testProfile(p)">Ver exemplo novo</button><button @click="dupProfile(p)">Copiar para editar</button>
          <button v-if="!p.builtin" @click="editProfile(p)">Editar</button><button v-if="!p.builtin" class="danger" @click="delProfile(p)">Apagar</button>
        </div>
      </div>
    </div>
    <div v-if="editing" class="modal" role="dialog" aria-modal="true" aria-labelledby="pe-t" @click.self="editing=null"><div class="card editor">
      <button type="button" class="modal-x" aria-label="Fechar" title="Fechar" @click="editing=null">✕</button>
      <h2 id="pe-t">{{ editing.id ? 'Editar estilo' : 'Novo estilo' }}</h2>
      <p v-if="editing.builtin" class="muted">Os estilos padrão não podem ser editados. Use "Copiar para editar".</p>
      <label>Nome do estilo<input v-model="editing.name"></label>
      <label>Descrição curta<input v-model="editing.description"></label>
      <label>Como devem ser as imagens (em inglês)<textarea rows="4" v-model="editing.style_prompt"></textarea>
        <small class="hint">Ex.: "oil painting, dramatic candlelight, muted earthy colors". Use "Ver exemplo novo" para testar antes de salvar.</small></label>
      <div class="grid2">
        <label>Quantas cenas animar (0 a 1)<input type="number" step="0.05" min="0" max="1" v-model.number="editing.motion.animated_ratio" inputmode="decimal"><small class="hint">0,35 anima cerca de 1 em cada 3 cenas. 0 não anima nenhuma.</small></label>
        <label>Tipo de animação<select v-model="editing.motion.clip_engine"><option value="ltx">Rápida</option><option value="wan">Mais fiel à imagem</option></select></label>
        <label>Cor do vídeo<select v-model="editing.finishing.grade"><option value="none">natural</option><option value="sepia_warm">sépia quente</option><option value="teal_amber">azul e âmbar</option><option value="high_contrast">alto contraste</option><option value="muted_earth">tons terrosos</option></select></label>
        <label>Grão de filme (0 a 1)<input type="number" step="0.05" min="0" max="1" v-model.number="editing.finishing.grain" inputmode="decimal"></label>
        <label>Escurecer as bordas (0 a 1)<input type="number" step="0.05" min="0" max="1" v-model.number="editing.finishing.vignette" inputmode="decimal"></label>
        <label>Fonte da legenda<select v-model="editing.captions.font"><option value="sans">sem serifa</option><option value="serif">com serifa</option><option value="mono">monoespaçada</option></select></label>
        <label>Cor da legenda<input type="color" v-model="editing.captions.color"></label>
      </div>
      <details class="adv"><summary>Avançado</summary>
        <div class="grid3">
          <label>Qualidade da imagem (passos)<input type="number" v-model.number="editing.params.steps"></label>
          <label>Largura da imagem<input type="number" step="16" v-model.number="editing.params.width"></label>
          <label>Altura da imagem<input type="number" step="16" v-model.number="editing.params.height"></label>
        </div>
        <p class="hint">Só mexa aqui se souber o que faz. Os valores padrão funcionam bem.</p>
      </details>
      <div class="actions"><button @click="editing=null">Cancelar</button><button class="primary" :disabled="editing.builtin" @click="saveProfile">Salvar</button></div>
    </div></div>
  </section>

  <!-- ===================== AGENDA ===================== -->
  <section v-if="route.name==='agenda'" class="agenda">
    <div class="row"><h1>Agenda de criação de vídeos</h1><button class="primary" @click="openNew(cal.sel)">+ Agendar um vídeo</button></div>
    <p class="lead">Veja o que está agendado, o que já foi feito e escolha o dia para criar um vídeo. Cada vídeo é criado no horário marcado, um de cada vez; a andes precisa estar ligada e sem o AudioGlifo rodando.</p>

    <section class="card tl" aria-label="Linha do tempo do mês">
      <h2 class="small">Linha do tempo de {{ calTitle }}</h2>
      <div class="tl-body">
        <div class="tl-axis" aria-hidden="true"><span v-for="t in tlTicks" :key="t.n" :style="{ left: t.left + '%' }">{{ t.n }}</span></div>
        <div v-for="lane in tlLanes" :key="lane.name" class="tl-lane">
          <span class="tl-name">{{ lane.name }}</span>
          <button v-for="e in lane.items" :key="e.id" type="button" class="tl-block" :class="'st-' + e.status" :style="{ left: e.left + '%', width: e.width + '%' }" :title="evTitle(e)" :aria-label="evTitle(e)" @click="selectDay(new Date(e.inicio * 1000).toLocaleDateString('sv-SE'))"></button>
        </div>
        <div v-if="tlToday !== null" class="tl-today" :style="{ left: tlToday + '%' }"><span>hoje</span></div>
      </div>
    </section>

    <div class="cal-layout">
      <section class="card cal" aria-label="Calendário do mês">
        <div class="cal-head">
          <div class="cal-nav">
            <button type="button" aria-label="Mês anterior" @click="calMove(-1)">‹</button>
            <h2>{{ calTitle }}</h2>
            <button type="button" aria-label="Próximo mês" @click="calMove(1)">›</button>
          </div>
          <button type="button" @click="calToday">Hoje</button>
        </div>
        <p v-if="calApi.erro.value" class="error-line" role="alert">{{ calApi.erro.value }} <button type="button" @click="calApi.tentarNovamente()">Tentar de novo</button></p>
        <div class="cal-wd" aria-hidden="true"><span v-for="w in WEEKDAYS" :key="w">{{ w }}</span></div>
        <div class="cal-weeks" :aria-busy="calApi.carregando.value">
          <div v-for="(sem, i) in calWeeks" :key="i" class="cal-week">
            <button v-for="iso in sem" :key="iso" type="button" class="cal-day" :class="{ sel: iso === cal.sel, out: monthOfIso(iso) !== cal.mes, today: iso === calHoje }" :aria-pressed="iso === cal.sel" :aria-label="dayAria(iso)" @click="selectDay(iso)">
              <span class="dn">{{ Number(iso.slice(8)) }}</span>
              <span class="dots" aria-hidden="true"><span v-for="e in eventsOfDay(iso).slice(0, 3)" :key="e.id" class="dotc" :class="'st-' + e.status"></span></span>
              <span v-for="e in eventsOfDay(iso).slice(0, 2)" :key="'c' + e.id" class="chip" :class="'st-' + e.status">{{ hhmm(e.inicio) }} {{ e.project_title }}</span>
              <span v-if="eventsOfDay(iso).length > 2" class="more">+{{ eventsOfDay(iso).length - 2 }}</span>
            </button>
          </div>
        </div>
        <div class="cal-legend"><span v-for="(label, key) in CAL_STATUS" :key="key"><i class="sw" :class="'st-' + key"></i>{{ label }}</span></div>
      </section>

      <aside class="card day" aria-live="polite">
        <p class="eyebrow">Dia selecionado</p>
        <h2>{{ dayTitle(cal.sel) }}</h2>
        <p class="muted">{{ daySummary }}</p>
        <ul class="evlist">
          <li v-for="e in dayShown" :key="e.id" class="evcard">
            <div class="evtop"><span class="evchip" :class="'st-' + e.status">{{ CAL_STATUS[e.status] || e.status }}</span><span class="muted">{{ e.origem === 'agendamento' ? 'agendado por você' : 'feito na hora' }}</span></div>
            <a class="evtitle" :href="'#/p/' + e.project_id">{{ e.project_title || 'vídeo apagado' }}</a>
            <p class="muted">{{ CAL_KIND[e.tipo] }} · ⏰ {{ evTime(e) }}</p>
            <p v-if="e.mensagem && !['pending', 'running'].includes(e.status)" class="muted">{{ e.mensagem }}</p>
            <div class="actions"><a class="btn" :href="'#/p/' + e.project_id">Abrir o vídeo</a><button v-if="e.cancelavel" type="button" class="danger" @click="cancelCalEvent(e)">Cancelar agendamento</button></div>
          </li>
          <li v-if="!dayEvents.length" class="muted">Nenhum vídeo neste dia.</li>
        </ul>
        <div v-if="dayEvents.length > 5" class="pager" role="navigation" aria-label="Páginas dos itens do dia">
          <span class="pcount">{{ dayFrom }}–{{ dayTo }} de {{ dayEvents.length }}</span>
          <span class="pbtns"><button type="button" :disabled="dayPage <= 1" aria-label="Página anterior" @click="dayGo(-1)">‹</button>
            <span class="pnum">{{ dayPage }}/{{ dayPages }}</span>
            <button type="button" :disabled="dayPage >= dayPages" aria-label="Próxima página" @click="dayGo(1)">›</button></span>
          <label class="psize">Por página <select v-model.number="daySize"><option :value="5">5</option><option :value="10">10</option><option :value="20">20</option></select></label>
        </div>
        <button type="button" class="primary wide" @click="openNew(cal.sel)">Agendar um vídeo neste dia</button>
      </aside>
    </div>

    <h2 class="sec">Todos os agendamentos</h2>
    <p v-if="!agenda.length" class="muted">Nada agendado ainda. Escolha um dia no calendário ou abra um vídeo e toque em "⏰ Agendar".</p>
    <div class="list">
      <div v-for="sc in agPg.items" :key="sc.id" class="card sitem" :class="sc.status">
        <div class="shead"><a :href="'#/p/'+sc.project_id" class="stitle">{{ sc.project_title || 'vídeo apagado' }}</a>
          <span class="badge" :class="'sch-'+sc.status">{{ SCHED_STATUS[sc.status] }}</span></div>
        <div class="muted">⏰ {{ fmtWhen(sc.run_at) }}<template v-if="eta2(sc)"> · termina por volta de {{ eta2(sc) }}</template></div>
        <div v-if="sc.message && !['pending'].includes(sc.status)" class="muted">{{ sc.message }}</div>
        <div v-if="['pending','running'].includes(sc.status)" class="actions"><button class="danger" @click="cancelFromAgenda(sc)">Cancelar</button></div>
      </div>
    </div>
    <pager :pg="agPg" label="Páginas dos agendamentos"></pager>
  </section>

  <!-- ===================== AJUDA ===================== -->
  <canais-view v-if="route.name==='channels'" :api="api" :say="say"></canais-view>
  <prompts-view v-if="route.name==='prompts'" :api="api" :say="say"></prompts-view>
  <canal-view v-if="route.name==='channel'" :key="route.id" :id="route.id" :tab="route.tab" :api="api" :say="say" @novo-video="onNewVideo"></canal-view>

  <section v-if="route.name==='ajuda'" class="help">
    <h1>Como o MisterClip funciona</h1>
    <p class="lead">Você entrega o roteiro. O MisterClip cuida da voz, das imagens, das legendas e da montagem do vídeo.</p>
    <h2>Passo a passo</h2>
    <ol class="how">
      <li><strong>Novo vídeo:</strong> cole o roteiro e escolha o estilo das imagens e a voz.</li>
      <li><strong>Dividir em cenas:</strong> o texto vira cenas de cerca de 10 segundos, cada uma com a sua imagem.</li>
      <li><strong>Voz e imagens:</strong> o MisterClip narra cada cena e desenha uma imagem para ela.</li>
      <li><strong>Revisar:</strong> veja as cenas, edite o que quiser e escolha quais imagens animar.</li>
      <li><strong>Criar o vídeo:</strong> aprove e ele junta tudo, com legendas, transições e música. Depois é só baixar.</li>
    </ol>
    <h2>Quanto tempo leva?</h2>
    <p>Depende do tamanho do vídeo e de quantas cenas são animadas. Como referência: um vídeo de 30 segundos fica pronto em cerca de 5 a 8 minutos; um de 15 minutos leva uns 25 minutos para preparar a voz e as imagens e mais 2 a 3 horas para criar o vídeo. Os botões mostram a estimativa de cada etapa.</p>
    <p>Para vídeos longos, use <strong>⏰ Agendar</strong> e deixe rodar de madrugada.</p>
    <h2>Palavras que aparecem aqui</h2>
    <dl class="gloss">
      <dt>Cena</dt><dd>Um trecho do roteiro (cerca de 10 segundos) com a sua própria imagem e narração.</dd>
      <dt>Estilo visual</dt><dd>A aparência das imagens e do acabamento do vídeo (cores, luz, técnica).</dd>
      <dt>Animar a imagem</dt><dd>Transforma a imagem parada num pequeno clipe com movimento. "Rápido" é mais ágil; "mais fiel" demora mais e respeita melhor a imagem. Sem animar, a imagem recebe um zoom suave.</dd>
      <dt>Transição</dt><dd>Como uma cena troca para a próxima: dissolver, escurecer ou corte direto.</dd>
      <dt>Agendar</dt><dd>Escolher o dia e a hora em que o vídeo será criado, para rodar enquanto você não está usando o computador.</dd>
      <dt>A andes</dt><dd>O computador com a placa de vídeo que faz o trabalho pesado. Precisa estar ligado.</dd>
    </dl>
    <h2>Dúvidas comuns</h2>
    <details><summary>Posso fechar a página enquanto o vídeo é criado?</summary><p>Pode. O trabalho continua na andes e o resultado fica salvo. Quando voltar, abra o vídeo na lista.</p></details>
    <details><summary>O que são os canais?</summary><p>Um canal é o seu canal do YouTube dentro do MisterClip. Cada canal tem o seu plano de 90 dias, calendário de vídeos, metas e números, e os vídeos que você cria ficam ligados a ele. Os vídeos antigos foram para o primeiro canal, que você pode renomear. Quando tiver outro canal, crie-o em Canais e escolha em qual deles cada vídeo entra.</p></details>
    <details><summary>Posso desligar o meu computador?</summary><p>Pode. Todo o trabalho acontece na andes, não no seu aparelho. Enquanto a andes estiver ligada, ela continua e termina o que começou, mesmo que você feche a página, atualize a tela ou desligue o seu computador. Se a própria andes reiniciar, o trabalho é retomado sozinho de onde parou. Use "Fazer tudo agora" ou "⏰ Agendar" para o MisterClip ir até o vídeo pronto sem esperar você.</p></details>
    <details><summary>A tarefa parou ou deu erro. E agora?</summary><p>Toque em "Tentar de novo". Ele continua de onde parou, sem refazer o que já ficou pronto.</p></details>
    <details><summary>Cancelei sem querer. Perdi tudo?</summary><p>Não. Tudo o que já foi gerado fica salvo.</p></details>
    <details><summary>Posso mudar o texto depois?</summary><p>Pode. Na aba Roteiro, altere e salve; o app pergunta se você quer dividir em cenas de novo. Mudar só a voz ou a velocidade refaz apenas a narração.</p></details>
    <details><summary>Por que a primeira imagem demora mais?</summary><p>A placa de vídeo precisa carregar o modelo de imagens. As seguintes saem mais rápido.</p></details>
    <details><summary>Posso usar qualquer música de fundo?</summary><p>Use apenas músicas que você tem direito de usar: suas, livres de direitos ou licenciadas.</p></details>
    <details><summary>Qual é o endereço do MisterClip?</summary><p>http://misterclip.nord, com a rede mesh ligada no aparelho (computador ou celular).</p></details>
    <p class="actions"><a class="btn primary" href="#/novo">Criar um vídeo</a><a class="btn" href="#/">Meus vídeos</a></p>
  </section>
  </main>

  <div v-if="ndlg.open" class="modal" role="dialog" aria-modal="true" aria-labelledby="nd-t" @click.self="ndlg.open=false">
    <form class="card editor" @submit.prevent="saveNew">
      <button type="button" class="modal-x" aria-label="Fechar" title="Fechar" @click="ndlg.open=false">✕</button>
      <h2 id="nd-t">Agendar um vídeo para {{ ndlg.date ? dayTitle(ndlg.date) : '' }}</h2>
      <p v-if="!eligible.length" class="muted">Ainda não há vídeos com cenas. Crie um vídeo e divida o roteiro em cenas para poder agendar.</p>
      <template v-else>
        <label>Vídeo<select v-model="ndlg.project_id" @change="loadNdlgEstimate"><option v-for="p in eligible" :key="p.id" :value="p.id">{{ p.title }}</option></select></label>
        <p v-if="ndlgProject && ndlgProject.schedule" class="hint">Este vídeo já está agendado para {{ fmtWhen(ndlgProject.schedule.run_at) }}. Agendar de novo substitui o horário anterior.</p>
        <div class="grid2"><label>Dia<input type="date" v-model="ndlg.date" required></label><label>Hora<input type="time" v-model="ndlg.time" required></label></div>
        <p v-if="ndlg.est && ndlgTs" class="muted">Leva {{ ndlg.est.seconds.prepare ? ndlg.est.human.prepare + ' (preparar) + ' : '' }}{{ ndlg.est.human.render }} (criar o vídeo)<template v-if="ndlgEnds">, e termina por volta de <strong>{{ fmtWhen(ndlgEnds) }}</strong></template>.</p>
        <p class="muted">A andes precisa estar ligada nesse horário e o AudioGlifo parado. Se houver outro vídeo na vez, este espera; se a andes estiver fora do ar, ele ainda roda até 12 h depois.</p>
      </template>
      <p v-if="ndlg.error" class="error-line" role="alert">{{ ndlg.error }}</p>
      <div class="actions"><button type="button" @click="ndlg.open=false">Voltar</button><button class="primary" type="submit" :disabled="!eligible.length">Agendar</button></div>
    </form>
  </div>

  <div v-if="dlg.open" class="modal" role="dialog" aria-modal="true" aria-labelledby="sch-t" @click.self="dlg.open=false">
    <form class="card editor" @submit.prevent="saveSchedule">
      <button type="button" class="modal-x" aria-label="Fechar" title="Fechar" @click="dlg.open=false">✕</button>
      <h2 id="sch-t">Agendar a criação do vídeo</h2>
      <p class="muted">No horário escolhido, o MisterClip prepara o que faltar (voz e imagens) e cria o vídeo, sozinho.</p>
      <div class="chips" role="group" aria-label="Horários sugeridos">
        <button type="button" v-for="p in presets" :key="p.h" @click="pickPreset(p)">{{ p.text }}</button>
      </div>
      <label>Data e hora<input type="datetime-local" v-model="dlg.value" :min="minLocal" required></label>
      <p v-if="estimate && dlgTs" class="muted">Leva {{ estimate.human.prepare && estimate.seconds.prepare ? estimate.human.prepare + ' (preparar) + ' : '' }}{{ estimate.human.render }} (criar o vídeo)<template v-if="dlgEnds">, e termina por volta de <strong>{{ fmtWhen(dlgEnds) }}</strong></template>.</p>
      <p class="muted">A andes precisa estar ligada nesse horário e o AudioGlifo parado. Se houver outro job rodando, este espera a vez; se a andes estiver fora do ar, ele ainda roda até 12 h depois.</p>
      <p v-if="dlg.error" class="error-line" role="alert">{{ dlg.error }}</p>
      <div class="actions"><button type="button" @click="dlg.open=false">Voltar</button><button class="primary" type="submit">Agendar</button></div>
    </form>
  </div>

  <!-- ===================== BARRA DE AÇÃO FIXA ===================== -->
  <div v-if="route.name==='new'" class="actionbar">
    <button :disabled="!form.text.trim() || !form.profile_id" @click="createProject(false)">Criar e revisar as cenas</button>
    <button class="primary big" :disabled="!form.text.trim() || !form.profile_id" @click="createProject(true)">Montar o vídeo sozinho</button>
  </div>
  <div v-if="route.name==='project' && project" class="actionbar" role="region" aria-label="Ação principal">
    <template v-if="project.busy && job">
      <div class="runbox" role="status" aria-live="polite">
        <div class="progress" role="progressbar" :aria-valuenow="Math.round(job.progress*100)" aria-valuemin="0" aria-valuemax="100"><div :style="{width:(job.progress*100)+'%'}"></div><span>{{ job.message }}</span></div>
        <div class="runmeta"><span class="muted">{{ Math.round(job.progress*100) }}% · {{ dur(elapsed) }}<template v-if="eta !== null"> · faltam ~{{ dur(eta) }}</template></span>
          <span class="rbtns"><button v-if="canAskNotifications" @click="askNotifications">Avisar</button>
            <button class="danger" :disabled="job.status==='cancelling'" @click="cancelJob">{{ job.status==='cancelling' ? 'Cancelando…' : 'Cancelar' }}</button></span></div>
      </div>
    </template>
    <template v-else-if="stopped">
      <div class="stopmsg" role="alert"><strong>{{ job.status==='cancelled' ? 'Você cancelou a tarefa.' : 'A tarefa parou por um problema.' }}</strong> <span class="muted">O que já foi gerado está salvo.</span>
        <details v-if="job.status==='failed'" class="tech"><summary>Ver detalhe técnico</summary><code>{{ job.message }}</code></details></div>
      <button class="primary big" @click="retryJob">Tentar de novo (continua de onde parou)</button>
    </template>
    <template v-else-if="primary">
      <button class="primary big" @click="primary.run">{{ primary.label }}<small v-if="primary.sub"> · {{ primary.sub }}</small></button>
      <button v-if="project.scenes.length" class="big sec" @click="openSchedule" aria-label="Agendar a criação do vídeo">⏰ Agendar</button>
      <a v-if="project.status==='done'" class="btn big" :href="'/api/projects/'+project.id+'/download'" aria-label="Baixar o vídeo em MP4">Baixar</a>
    </template>
  </div>

  <nav class="tabbar" v-if="['projects','profiles','agenda','ajuda','channels','channel'].includes(route.name)" aria-label="Principal">
    <a href="#/" :aria-current="route.name==='projects' ? 'page' : null">Vídeos</a>
    <a href="#/novo">Novo</a>
    <a href="#/agenda" :aria-current="route.name==='agenda' ? 'page' : null">Agenda</a>
    <a href="#/canais" :aria-current="route.name==='channels'||route.name==='channel' ? 'page' : null">Canais</a>
    <a href="#/perfis" :aria-current="route.name==='profiles' ? 'page' : null">Estilos</a>
  </nav>
  `,
}).mount('#app');
