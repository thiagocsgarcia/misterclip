/** Biblioteca de prompts: o playbook de 10 prompts para planejar um canal, editável, com variáveis para preencher e copiar. */
import { ref, reactive, computed, onMounted } from './vendor/vue.esm-browser.prod.js';
import { usePager, Pager } from './pager.js';

const VAR_HINT = '{{variavel}}';   // as chaves duplas ficam numa constante: dentro do template elas fechariam a interpolação
const VAR_LABEL = { nome_do_canal: 'Nome do canal', nicho: 'Nicho', publico: 'Público', recursos: 'Recursos (tempo por semana, orçamento, equipamento)', meta: 'Meta', data_de_inicio: 'Primeiro dia do plano',
  interesses: 'Seus interesses', habilidades: 'Suas habilidades', ideia_do_video: 'Ideia do vídeo', minutos: 'Duração (minutos)', quebra_a_cada_segundos: 'Quebra de padrão a cada (segundos)', porte_do_canal: 'Porte do canal',
  temas_dos_videos_longos: 'Temas dos vídeos longos', videos_por_semana: 'Vídeos por semana', horas_por_semana: 'Horas por semana', ferramentas_que_ja_tem: 'Ferramentas que você já tem', pais: 'País',
  tipo_de_audiencia: 'Tipo de audiência', dados_colados: 'Seus números da semana' };

export const PromptsView = {
  components: { Pager },
  props: { api: Function, say: Function },
  setup(props) {
    const list = ref([]); const err = ref(''); const open = ref(null); const vals = reactive({}); const draft = reactive({}); const busy = ref(false);
    const pgP = usePager(list, 10);
    const novo = reactive({ open: false, titulo: '', body: '', quando_usar: '' });
    const load = async () => { try { list.value = await props.api('/api/prompts'); } catch (e) { err.value = e.message; } };
    onMounted(load);
    const toggle = (p) => { open.value = open.value === p.id ? null : p.id; draft.body = p.body; draft.titulo = p.titulo; draft.quando_usar = p.quando_usar || ''; draft.por_que_funciona = p.por_que_funciona || ''; };
    const filled = (p) => (open.value === p.id ? draft.body : p.body).replace(/\{\{(\w+)\}\}/g, (m, k) => (vals[k] && String(vals[k]).trim() ? vals[k] : m));
    const copy = (text) => { try { navigator.clipboard.writeText(text); props.say('Copiado'); } catch { err.value = 'Não consegui copiar: selecione o texto e copie à mão.'; } };
    const save = async (p) => { busy.value = true; err.value = ''; try { await props.api(`/api/prompts/${p.id}`, { method: 'PUT', body: { titulo: draft.titulo, body: draft.body, quando_usar: draft.quando_usar, por_que_funciona: draft.por_que_funciona, variaveis: p.variaveis || [], secoes_geradas: p.secoes_geradas || [], ordem: p.ordem } }); props.say('Prompt salvo'); await load(); } catch (e) { err.value = e.message; } finally { busy.value = false; } };
    const restore = async (p) => { if (!confirm('Voltar este prompt ao texto de fábrica? As suas edições nele serão perdidas.')) return; try { await props.api(`/api/prompts/${p.id}/restore`, { method: 'POST' }); props.say('Restaurado'); await load(); open.value = null; } catch (e) { err.value = e.message; } };
    const remove = async (p) => { if (!confirm('Apagar este prompt?')) return; try { await props.api(`/api/prompts/${p.id}`, { method: 'DELETE' }); await load(); } catch (e) { err.value = e.message; } };
    const create = async () => { err.value = ''; try { await props.api('/api/prompts', { method: 'POST', body: { titulo: novo.titulo, body: novo.body, quando_usar: novo.quando_usar } }); Object.assign(novo, { open: false, titulo: '', body: '', quando_usar: '' }); props.say('Prompt criado'); await load(); } catch (e) { err.value = e.message; } };
    const varLabel = (k) => VAR_LABEL[k] || k.replace(/_/g, ' ');
    const exemplo = computed(() => 'Execute o prompt "Playbook completo: projetar um canal novo" da biblioteca de prompts do MisterClip para o canal [nome], nicho [nicho], público [público], recursos [tempo, orçamento, equipamento], meta [meta], começando em [data].');
    return { pgP, VAR_HINT, list, err, open, vals, draft, busy, novo, toggle, filled, copy, save, restore, remove, create, varLabel, exemplo };
  },
  template: `
  <section class="prompts">
    <a class="back" href="#/canais">← Canais</a>
    <div class="row"><h1>Modelos de prompt</h1><button class="btn" type="button" @click="novo.open = !novo.open">{{ novo.open ? 'Fechar' : '+ Novo prompt' }}</button></div>
    <p class="lead">O roteiro de 10 prompts para planejar um canal de YouTube, ajustado para o MisterClip. Cada um tem o seu texto original e uma versão com regras de qualidade e o formato que o módulo Canais entende.</p>
    <div class="card howto"><strong>Como usar num canal novo</strong>
      <p>Peça ao Claude, numa conversa, para executar um prompt (ou o “Playbook completo”, que faz os dez em ordem). Ele pesquisa, monta o planejamento e grava tudo no canal, onde você edita.</p>
      <p class="hint">Exemplo para copiar e preencher:</p><pre class="final">{{ exemplo }}</pre><button type="button" @click="copy(exemplo)">Copiar o exemplo</button></div>
    <p v-if="err" class="error-line" role="alert">{{ err }}</p>
    <form v-if="novo.open" class="card" @submit.prevent="create">
      <label>Título<input v-model="novo.titulo" required></label><label>Quando usar<input v-model="novo.quando_usar"></label>
      <label>Texto do prompt (use {{ VAR_HINT }} para o que muda)<textarea rows="8" v-model="novo.body" required></textarea></label><button class="primary" type="submit">Criar prompt</button></form>
    <article v-for="p in pgP.items" :key="p.id" class="card prompt">
      <header><button type="button" class="linkbtn big" @click="toggle(p)">{{ open === p.id ? '▾' : '▸' }} <b><template v-if="p.ordem > 0">{{ p.ordem }}. </template>{{ p.titulo }}</b></button>
        <span v-if="p.builtin" class="badge">de fábrica</span></header>
      <p class="muted">{{ p.quando_usar }}</p>
      <div v-if="open === p.id" class="pbody">
        <p><b>Por que funciona:</b> {{ p.por_que_funciona }}</p>
        <p v-if="(p.secoes_geradas || []).length" class="hint"><b>Preenche no canal:</b> {{ p.secoes_geradas.join(', ') }}</p>
        <fieldset v-if="(p.variaveis || []).length"><legend>Preencha para copiar o prompt pronto</legend>
          <label v-for="v in p.variaveis" :key="v">{{ varLabel(v) }}<input v-model="vals[v]"></label></fieldset>
        <label>Texto do prompt (ajustado)<textarea rows="14" v-model="draft.body"></textarea></label>
        <div class="row-tight"><button class="primary" type="button" @click="copy(filled(p))">Copiar o prompt{{ Object.values(vals).some((x) => x) ? ' preenchido' : '' }}</button>
          <button type="button" :disabled="busy" @click="save(p)">Salvar as minhas edições</button>
          <button v-if="p.builtin" type="button" @click="restore(p)">Voltar ao de fábrica</button>
          <button v-else type="button" class="danger" @click="remove(p)">Apagar</button></div>
        <details v-if="p.original" class="adv"><summary>Ver o texto original (o seu, antes do ajuste)</summary><pre class="final">{{ p.original }}</pre><button type="button" @click="copy(p.original)">Copiar o original</button></details>
      </div>
    </article>
    <pager :pg="pgP" label="Páginas dos prompts"></pager>
  </section>`,
};
