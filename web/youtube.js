/** Aba YouTube de um canal: configuração, conexão, dashboard de números e envio automático pelo calendário. */
import { ref, reactive, computed, onMounted, watch } from './vendor/vue.esm-browser.prod.js';
import { usePager, Pager } from './pager.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nf = (n) => Math.round(n || 0).toLocaleString('pt-BR');
const nf1 = (n) => Number(n || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
const pct = (a, b) => Math.max(0, Math.min(100, b ? Math.round((a / b) * 100) : 0));
const fday = (iso) => (iso ? new Date(String(iso).slice(0, 10) + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : '');
const fwhen = (ts) => (ts ? new Date(ts * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
const PRIV = { agendado: 'Agendar na data do calendário (recomendado)', privado: 'Enviar como privado', nao_listado: 'Enviar como não listado', publico: 'Publicar na hora' };
const ST = { enviando: 'Enviando…', enviado: 'Enviado', publicado: 'Publicado', erro: 'Deu erro' };

export const YoutubeView = {
  components: { Pager },
  props: { id: String, api: Function, say: Function },
  setup(props) {
    const st = ref(null); const err = ref(''); const loading = ref(true); const busy = ref(false);
    const cli = reactive({ client_id: '', client_secret: '' });
    const auth = reactive({ url: '', pasted: '' });
    const cfg = reactive({ envio_automatico: false, hora: '18:00', privacidade: 'agendado', categoria: '27', conteudo_sintetico: false });
    const range = ref(28);
    const guard = async (fn) => { err.value = ''; busy.value = true; try { return await fn(); } catch (e) { err.value = e.message; } finally { busy.value = false; } };
    const load = async () => {
      try { st.value = await props.api(`/api/channels/${props.id}/youtube`); Object.assign(cfg, st.value.config); } catch (e) { err.value = e.message; }
      loading.value = false;
    };
    onMounted(load); watch(() => props.id, load);

    const saveClient = () => guard(async () => { await props.api('/api/youtube/config', { method: 'PUT', body: { ...cli } }); cli.client_secret = ''; props.say('Chaves guardadas'); await load(); });
    const getUrl = () => guard(async () => { auth.url = (await props.api(`/api/channels/${props.id}/youtube/auth-url`, { method: 'POST' })).url; });
    const finish = () => guard(async () => { const r = await props.api(`/api/channels/${props.id}/youtube/auth-finish`, { method: 'POST', body: { pasted: auth.pasted } }); auth.url = ''; auth.pasted = ''; props.say('Conectado: ' + r.canal.title); await load(); await sync(); });
    const disconnect = () => confirm('Desconectar este canal do YouTube? Os vídeos já enviados continuam lá.') && guard(async () => { await props.api(`/api/channels/${props.id}/youtube`, { method: 'DELETE' }); await load(); });
    const sync = () => guard(async () => {
      props.say('Lendo os números do YouTube…');
      let j = await props.api(`/api/channels/${props.id}/youtube/sync`, { method: 'POST' });
      for (let i = 0; i < 120 && j.status !== 'done' && j.status !== 'failed'; i++) { await sleep(2000); j = await props.api('/api/jobs/' + j.id); }
      if (j.status === 'failed') throw new Error(j.message || 'não foi possível ler os números');
      props.say('Números atualizados'); await load();
    });
    const saveCfg = () => guard(async () => { await props.api(`/api/channels/${props.id}/plan/youtube_config`, { method: 'PUT', body: { value: { ...cfg } } }); props.say('Salvo'); await load(); });

    const snap = computed(() => st.value?.snapshot || null);
    const serie = computed(() => (snap.value?.serie_90d || []).slice(-range.value));
    const spark = (key, w = 300, h = 70) => {
      const v = serie.value.map((r) => r[key]); if (!v.length) return '';
      const mx = Math.max(1, ...v); const step = v.length > 1 ? w / (v.length - 1) : w;
      return v.map((x, i) => `${(i * step).toFixed(1)},${(h - 4 - (x / mx) * (h - 8)).toFixed(1)}`).join(' ');
    };
    const totals = computed(() => ({ views: serie.value.reduce((a, r) => a + r.views, 0), horas: serie.value.reduce((a, r) => a + r.minutos, 0) / 60,
      inscritos: serie.value.reduce((a, r) => a + r.inscritos_ganhos - r.inscritos_perdidos, 0) }));
    const videos = computed(() => snap.value?.videos || []);
    const pgY = usePager(videos, 10);
    const ypp = computed(() => st.value?.ypp || null);
    return { pgY, st, err, loading, busy, cli, auth, cfg, range, saveClient, getUrl, finish, disconnect, sync, saveCfg, snap, serie, spark, totals, videos, ypp, PRIV, ST, nf, nf1, pct, fday, fwhen };
  },
  template: `
  <div class="plano yt">
    <p v-if="err" class="error-line" role="alert">{{ err }}</p>
    <p v-if="loading" class="muted">Carregando…</p>
    <template v-else-if="st">

      <section v-if="!st.cliente_configurado" class="card">
        <h2>1. Ligar o MisterClip ao seu YouTube</h2>
        <p class="lead">Uma vez só. Você cria uma “chave” gratuita no Google e cola aqui. O MisterClip nunca vê a sua senha.</p>
        <ol class="how">
          <li>Abra <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer">console.cloud.google.com</a>, entre com a conta Google do canal e crie um projeto (nome: MisterClip).</li>
          <li>Em <b>APIs e serviços &gt; Biblioteca</b>, ative as duas: <b>YouTube Data API v3</b> e <b>YouTube Analytics API</b>.</li>
          <li>Em <b>Tela de permissão OAuth</b>: tipo <b>Externo</b>, nome MisterClip, o seu e-mail; em <b>Usuários de teste</b> acrescente a sua conta Google. Depois toque em <b>Publicar app</b> (“Em produção”). No modo de teste a permissão vence em 7 dias.</li>
          <li>Em <b>Credenciais &gt; Criar credenciais &gt; ID do cliente OAuth</b>, escolha o tipo <b>App para computador</b>.</li>
          <li>Copie o <b>ID do cliente</b> e a <b>chave secreta</b> e cole abaixo.</li>
        </ol>
        <form @submit.prevent="saveClient"><label>ID do cliente<input v-model="cli.client_id" autocomplete="off" placeholder="números.apps.googleusercontent.com" required></label>
          <label>Chave secreta<input v-model="cli.client_secret" type="password" autocomplete="off" required><small class="hint">Fica guardada só na andes. Nunca volta para esta tela.</small></label>
          <button class="primary" type="submit" :disabled="busy">Guardar</button></form>
        <p class="hint">Aviso importante do Google: vídeos enviados por projetos de API que ainda não passaram pela auditoria do Google ficam <b>privados</b>. O MisterClip envia assim e você publica com um toque no YouTube Studio. Para publicar sozinho, peça a auditoria do projeto (formulário “YouTube API Services: Audit and Quota Extension”).</p>
      </section>

      <section v-else-if="!st.conectado" class="card">
        <h2>2. Conectar este canal</h2>
        <p>As chaves já estão guardadas. Agora autorize o acesso ao seu canal do YouTube.</p>
        <button v-if="!auth.url" class="primary" type="button" :disabled="busy" @click="getUrl">Conectar ao YouTube</button>
        <template v-else>
          <ol class="how"><li><a :href="auth.url" target="_blank" rel="noopener noreferrer">Abrir a página do Google</a> e tocar em <b>Permitir</b> (aceite todas as caixas).</li>
            <li>Vai aparecer uma página de erro (“não foi possível conectar”). É normal. Copie o <b>endereço inteiro</b> dessa página, na barra do navegador.</li>
            <li>Cole aqui e toque em Concluir.</li></ol>
          <label>Endereço copiado<input v-model="auth.pasted" placeholder="http://127.0.0.1:8765/?state=...&code=..." autocomplete="off"></label>
          <button class="primary" type="button" :disabled="busy || !auth.pasted" @click="finish">Concluir a conexão</button>
        </template>
      </section>

      <template v-else>
        <section class="card">
          <div class="row"><h2>{{ st.conta.titulo || 'Canal conectado' }}</h2><span class="badge">conectado</span></div>
          <p class="muted">Última leitura: {{ snap ? fwhen(snap.taken) : 'ainda não leu' }}. O MisterClip atualiza sozinho uma vez por dia.</p>
          <div class="row-tight"><button class="primary" type="button" :disabled="busy" @click="sync">{{ busy ? 'Lendo…' : 'Atualizar os números agora' }}</button><button type="button" class="danger" @click="disconnect">Desconectar</button></div>
        </section>

        <template v-if="snap">
          <section class="card">
            <h2>Rumo ao Programa de Parcerias</h2>
            <div class="goalrow"><span>Horas de vídeos longos (12 meses)</span><b>{{ nf1(ypp.horas) }} de {{ nf(ypp.horas_meta) }}</b></div><div class="bar"><div :style="{ width: pct(ypp.horas, ypp.horas_meta) + '%' }"></div></div>
            <div class="goalrow"><span>Inscritos</span><b>{{ nf(ypp.inscritos) }} de {{ nf(ypp.inscritos_meta) }}</b></div><div class="bar"><div :style="{ width: pct(ypp.inscritos, ypp.inscritos_meta) + '%' }"></div></div>
            <p v-if="ypp.inclui_shorts" class="hint">O YouTube não separou os Shorts nesta leitura: as horas podem incluir Shorts e estar acima do que vale para o programa.</p>
            <p v-if="ypp.shorts_views_90d !== null" class="hint">Visualizações de Shorts nos últimos 90 dias: {{ nf(ypp.shorts_views_90d) }} (o caminho dos Shorts pede {{ nf(ypp.shorts_meta) }}).</p>
            <p v-if="ypp.regras_novas_valem" class="hint">As regras novas (8.000 horas) já valem para quem ainda não entrou no programa.</p>
          </section>

          <section class="card">
            <div class="row"><h2>Últimos dias</h2><span class="row-tight"><button type="button" :class="{ on: range === 28 }" @click="range = 28">28 dias</button><button type="button" :class="{ on: range === 90 }" @click="range = 90">90 dias</button></span></div>
            <div class="kpis"><div><b>{{ nf(totals.views) }}</b><span>visualizações</span></div><div><b>{{ nf1(totals.horas) }}</b><span>horas assistidas</span></div><div><b>{{ totals.inscritos > 0 ? '+' : '' }}{{ nf(totals.inscritos) }}</b><span>inscritos no período</span></div></div>
            <div class="sparks">
              <figure><figcaption>Visualizações por dia</figcaption><svg viewBox="0 0 300 70" role="img" aria-label="Visualizações por dia"><polyline :points="spark('views')" class="goal"/></svg></figure>
              <figure><figcaption>Minutos assistidos por dia</figcaption><svg viewBox="0 0 300 70" role="img" aria-label="Minutos assistidos por dia"><polyline :points="spark('minutos')" class="goal"/></svg></figure>
              <figure><figcaption>Inscritos ganhos por dia</figcaption><svg viewBox="0 0 300 70" role="img" aria-label="Inscritos ganhos por dia"><polyline :points="spark('inscritos_ganhos')" class="goal"/></svg></figure>
            </div>
          </section>

          <section class="card" v-if="videos.length">
            <h2>Vídeos (últimos 90 dias)</h2>
            <table class="mtable"><thead><tr><th>Vídeo</th><th>Views</th><th>Assistido</th><th>CTR</th><th>Inscritos</th></tr></thead>
              <tbody><tr v-for="v in pgY.items" :key="v.id"><td><a :href="'https://studio.youtube.com/video/' + v.id + '/edit'" target="_blank" rel="noopener noreferrer">{{ v.titulo }}</a><small v-if="v.privacidade && v.privacidade !== 'public'"> · {{ v.privacidade === 'private' ? 'privado' : v.privacidade }}</small></td>
                <td>{{ nf(v.views) }}</td><td>{{ nf1(v.assistido_pct) }}%</td><td>{{ v.ctr === null ? '–' : nf1(v.ctr) + '%' }}</td><td>{{ nf(v.inscritos) }}</td></tr></tbody></table>
            <pager :pg="pgY" label="Páginas dos vídeos do canal"></pager>
          </section>

          <section class="card" v-if="st.piores.length">
            <h2>Os 3 que mais precisam de atenção</h2>
            <ul class="vlist"><li v-for="v in st.piores" :key="v.id" class="vrow"><p class="vtitle">{{ v.titulo }}</p>
              <p class="muted">{{ nf(v.views) }} views · assistido {{ nf1(v.assistido_pct) }}%<template v-if="v.ctr !== null"> · CTR {{ nf1(v.ctr) }}%</template></p><p>{{ v.diagnostico }}</p></li></ul>
            <p class="hint">Mude uma coisa por vez e espere 7 dias (veja a revisão semanal na aba Operação).</p>
          </section>
          <section class="card" v-if="snap.avisos && snap.avisos.length"><h2>Avisos da leitura</h2><ul><li v-for="(a, i) in snap.avisos" :key="i">{{ a }}</li></ul></section>
        </template>

        <section class="card">
          <h2>Publicação pelo calendário</h2>
          <p class="hint">Quando um vídeo do calendário fica pronto, o MisterClip pode enviá-lo sozinho ao YouTube na data marcada, um de cada vez (limite de {{ st.max_envios_dia }} por dia, pela cota do YouTube). Hoje: {{ st.envios_hoje }}.</p>
          <label class="check"><input type="checkbox" v-model="cfg.envio_automatico"> Enviar sozinho quando o vídeo ficar pronto</label>
          <div class="grid2"><label>Hora da publicação<input type="time" v-model="cfg.hora"></label>
            <label>Como enviar<select v-model="cfg.privacidade"><option v-for="(t, k) in PRIV" :key="k" :value="k">{{ t }}</option></select></label></div>
          <label class="check"><input type="checkbox" v-model="cfg.conteudo_sintetico"> Marcar como conteúdo alterado ou sintético (use se houver imagens realistas feitas por IA)</label>
          <button class="primary" type="button" :disabled="busy" @click="saveCfg">Salvar</button>
        </section>

        <section class="card" v-if="st.envios.length">
          <h2>Envios feitos</h2>
          <ul class="vlist"><li v-for="u in st.envios" :key="u.id" class="vrow" :class="u.status">
            <p class="vtitle">{{ u.title }}</p><p class="muted">{{ ST[u.status] || u.status }} · {{ fwhen(u.created) }}<template v-if="u.publish_at"> · marcado para {{ fwhen(Date.parse(u.publish_at) / 1000) }}</template>
              <template v-if="u.video_id"> · <a :href="'https://youtu.be/' + u.video_id" target="_blank" rel="noopener noreferrer">abrir</a></template></p>
            <p v-if="u.warning" class="hint">{{ u.warning }}</p><p v-if="u.error" class="error-line">{{ u.error }}</p></li></ul>
        </section>
      </template>
    </template>
  </div>`,
};
