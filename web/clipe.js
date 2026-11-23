/** Tela "Novo clipe musical": envia a música (sua), a letra e as escolhas; o clipe conta a história da letra, sem cantor na tela. */
import { ref, reactive, computed, onMounted, onUnmounted } from './vendor/vue.esm-browser.prod.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const AVG_SCENE = { calmo: 3.8, normal: 3.0, agitado: 2.0 };   // duração média de uma cena em cada ritmo, em segundos
const human = (s) => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${Math.max(1, m)} min`; };
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

export const ClipeNovo = {
  props: { api: Function, say: Function, profiles: Array, channels: Array, defaultChannel: String },
  setup(props) {
    const f = reactive({ title: '', lyrics: '', concept: '', profile_id: props.profiles[0]?.id || '', ritmo: 'normal', animacao: 'total', legendas: true, channel_id: props.defaultChannel || '' });
    const opts = ref({ ritmos: { normal: 'Normal' }, animacoes: { total: 'Animar todas as cenas (recomendado)' }, max_seconds: 600 });
    const file = ref(null); const url = ref(''); const secs = ref(0); const busy = ref(false); const err = ref('');
    // upload: a música sobe assim que é escolhida e a andes escreve a letra para você revisar
    const up = reactive({ id: '', state: 'idle', msg: '', suggested: '', filled: false, instrumental: false });
    let gen = 0;
    onMounted(async () => { try { opts.value = await props.api('/api/clips/options'); } catch {} if (!f.profile_id && props.profiles.length) f.profile_id = props.profiles[0].id; });
    onUnmounted(() => { gen++; if (url.value) URL.revokeObjectURL(url.value); });

    const poll = async (job, mine) => {
      let j = job;
      for (let i = 0; i < 600 && mine === gen && j.status !== 'done' && j.status !== 'failed' && j.status !== 'cancelled'; i++) {
        up.msg = j.status === 'queued' ? 'Na fila da andes… a transcrição começa quando ela estiver livre.' : 'Ouvindo a música para escrever a letra…';
        await sleep(2000); if (mine !== gen) return null; j = await props.api('/api/jobs/' + j.id);
      }
      return mine === gen ? j : null;
    };
    const applyTranscript = (res) => {
      up.instrumental = !!res.instrumental; up.suggested = res.lyrics || '';
      if (up.instrumental) { up.state = 'done'; up.msg = 'Não encontrei voz cantada nesta música. Descreva a história no campo 4.'; return; }
      if (!f.lyrics.trim()) { f.lyrics = res.lyrics; up.filled = true; up.suggested = ''; }
      up.state = 'done'; up.msg = 'Letra escrita pela andes. Revise com calma: música cantada pode ser entendida errado.';
    };
    const transcribe = async (job) => {
      const mine = ++gen; up.state = 'listening'; up.msg = 'Ouvindo a música para escrever a letra…';
      try {
        const j = await poll(job, mine); if (!j) return;
        if (j.status !== 'done') { up.state = 'failed'; up.msg = 'Não consegui transcrever a letra. Cole a letra à mão ou descreva a história no campo 4.'; return; }
        applyTranscript(j.result || {});
      } catch (e) { if (mine === gen) { up.state = 'failed'; up.msg = e.message; } }
    };
    const retranscribe = async () => {
      if (!up.id) return;
      try { up.filled = false; transcribe(await props.api(`/api/clips/upload/${up.id}/transcribe`, { method: 'POST' })); } catch (e) { err.value = e.message; }
    };
    const useSuggested = () => { f.lyrics = up.suggested; up.suggested = ''; up.filled = true; };
    const upload = async (x) => {
      const mine = ++gen; up.state = 'uploading'; up.msg = 'Enviando a música…'; up.suggested = ''; up.filled = false; up.instrumental = false;
      const old = up.id; up.id = '';
      if (old) props.api(`/api/clips/upload/${old}`, { method: 'DELETE' }).catch(() => {});
      try {
        const fd = new FormData(); fd.append('file', x);
        const r = await props.api('/api/clips/upload', { method: 'POST', body: fd });
        if (mine !== gen) return;
        up.id = r.upload_id; if (r.seconds) secs.value = r.seconds;
        transcribe(r.job);
      } catch (e) { if (mine === gen) { up.state = 'failed'; up.msg = e.message; err.value = e.message; } }
    };
    const pick = (ev) => {
      const x = ev.target.files[0]; if (!x) return;
      err.value = ''; file.value = x; secs.value = 0;
      if (url.value) URL.revokeObjectURL(url.value);
      url.value = URL.createObjectURL(x);
      const a = new Audio(); a.preload = 'metadata'; a.src = url.value; a.onloadedmetadata = () => { secs.value = a.duration || 0; };
      if (!f.title) f.title = x.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
      upload(x);
    };
    const estimate = computed(() => {
      if (!secs.value) return null;
      const n = Math.max(1, Math.round(secs.value / AVG_SCENE[f.ritmo]));
      const heroes = Math.min(6, Math.floor(n / 8)) || 1;
      const anim = f.animacao === 'total' ? (n - heroes) * 60 + heroes * 240 : f.animacao === 'destaques' ? Math.round(n * 0.4) * 60 : 0;
      const total = n * 5 + n * 14 + anim + 20 + n * 1.5 + secs.value * 0.65;
      return { n, total };
    });
    const tooLong = computed(() => secs.value > opts.value.max_seconds);
    const waiting = computed(() => up.state === 'uploading' || up.state === 'listening');
    const canSubmit = computed(() => !!file.value && !!up.id && !waiting.value && (f.lyrics.trim() || f.concept.trim()) && !!f.profile_id && !tooLong.value && secs.value >= 20);

    const submit = async () => {
      err.value = ''; busy.value = true;
      try {
        const fd = new FormData();
        fd.append('upload_id', up.id);
        for (const [k, v] of Object.entries(f)) fd.append(k, typeof v === 'boolean' ? String(v) : v ?? '');
        const p = await props.api('/api/clips', { method: 'POST', body: fd });
        await props.api(`/api/projects/${p.id}/plan`, { method: 'POST' });
        gen++; props.say('Clipe criado: a andes está ouvindo a música e criando a história');
        location.hash = `#/p/${p.id}/cenas`;
      } catch (e) { err.value = e.message; } finally { busy.value = false; }
    };
    return { f, opts, file, url, secs, busy, err, pick, up, waiting, retranscribe, useSuggested, estimate, tooLong, canSubmit, submit, human, mmss };
  },
  template: `
  <section class="newform clipnew">
    <h1>Novo clipe musical</h1>
    <p class="lead">Envie a sua música e cole a letra. O MisterClip conta a <strong>história da música</strong> em cenas animadas, cortadas no ritmo. Ninguém aparece cantando.</p>
    <div class="tip"><span>💡 A imagem de cada cena vem do momento da história que a letra conta. Quanto mais clara a letra (ou a sua descrição), melhor o clipe.</span></div>

    <label>1. Sua música
      <input type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" @change="pick">
      <small class="hint">mp3, wav, m4a, ogg ou flac, de 20 segundos a 10 minutos. Use só músicas suas ou que você tem direito de usar.</small></label>
    <div v-if="file" class="row-tight"><audio :src="url" controls preload="metadata"></audio><span class="muted">{{ file.name }}<template v-if="secs"> · {{ mmss(secs) }}</template></span></div>
    <p v-if="tooLong" class="error-line" role="alert">A música passa do limite de {{ opts.max_seconds / 60 }} minutos.</p>
    <div v-if="up.state !== 'idle'" class="card transc" :class="up.state" role="status" aria-live="polite">
      <span v-if="waiting" class="spin" aria-hidden="true">⏳</span><span v-else-if="up.state === 'failed'" aria-hidden="true">⚠️</span><span v-else aria-hidden="true">✅</span>
      <span>{{ up.msg }}</span>
      <button v-if="up.id && !waiting" type="button" @click="retranscribe">Transcrever de novo</button>
    </div>

    <label>2. Título do clipe<input v-model="f.title" maxlength="120" placeholder="Ex.: Volta pra casa" autocomplete="off"></label>
    <label>3. Letra da música
      <textarea v-model="f.lyrics" rows="10" placeholder="A letra aparece aqui depois que a andes ouvir a música. Você também pode colar ou escrever."></textarea>
      <small class="hint">É dela que sai a história. <b v-if="up.filled">Esta letra foi escrita automaticamente: leia, corrija e complete antes de criar o clipe.</b> Marcações como [Verso] e [Refrão] são ignoradas. Se a música não tem letra, descreva a história no campo abaixo.</small></label>
    <div v-if="up.suggested" class="card transc"><span>A andes também transcreveu uma letra, mas o campo já tem texto.</span><button type="button" @click="useSuggested">Usar a letra transcrita (troca a atual)</button></div>
    <label>4. Como você imagina o clipe (opcional)
      <textarea v-model="f.concept" rows="3" placeholder="Ex.: um marinheiro idoso volta à cidade onde nasceu; tudo em tons de azul e dourado"></textarea>
      <small class="hint">Quem vive a história, onde ela acontece, o clima. Em branco, o MisterClip deduz da letra.</small></label>

    <fieldset class="gallery-set"><legend>5. Estilo das imagens</legend>
      <div class="gallery">
        <label v-for="p in profiles" :key="p.id" class="card pick" :class="{sel: f.profile_id===p.id}">
          <input type="radio" name="perfil-clipe" v-model="f.profile_id" :value="p.id">
          <img v-if="p.preview" :src="'/'+p.preview" :alt="'Exemplo do estilo '+p.name" loading="lazy">
          <strong>{{ p.name }}</strong><span class="muted">{{ p.description }}</span>
        </label>
      </div>
    </fieldset>

    <div class="grid2">
      <label>6. Ritmo dos cortes<select v-model="f.ritmo"><option v-for="(t, k) in opts.ritmos" :key="k" :value="k">{{ t }}</option></select>
        <small class="hint">Os cortes caem sempre na batida. Partes mais fortes cortam mais rápido.</small></label>
      <label>7. Animação<select v-model="f.animacao"><option v-for="(t, k) in opts.animacoes" :key="k" :value="k">{{ t }}</option></select>
        <small class="hint">Animar dá vida às cenas, mas leva mais tempo na andes.</small></label>
    </div>
    <label class="check"><input type="checkbox" v-model="f.legendas"> Mostrar a letra na tela, no tempo da música</label>
    <label v-if="channels.length > 1">Canal<select v-model="f.channel_id"><option v-for="c in channels" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>

    <p v-if="estimate" class="card hint">Cerca de <b>{{ estimate.n }} cenas</b>. Na andes, o clipe leva em torno de <b>{{ human(estimate.total) }}</b> para ficar pronto. Pode deixar rodando e até desligar o seu computador; pare o AudioGlifo antes.</p>
    <p v-if="err" class="error-line" role="alert">{{ err }}</p>
    <div class="actions"><button class="primary big" type="button" :disabled="!canSubmit || busy" @click="submit">{{ busy ? 'Criando o clipe…' : waiting ? 'Aguarde a letra…' : 'Criar e planejar o clipe' }}</button></div>
  </section>`,
};
