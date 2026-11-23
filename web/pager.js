/** Paginação reutilizável: `usePager(lista, tamanho)` calcula a página; <pager :pg="pg"> mostra os botões. */
import { ref, reactive, computed, watch } from './vendor/vue.esm-browser.prod.js';

export const PAGE_SIZES = [10, 20, 50];

export function usePager(source, initial = 10) {
  const page = ref(1); const size = ref(initial);
  const total = computed(() => (source.value || []).length);
  const pages = computed(() => Math.max(1, Math.ceil(total.value / size.value)));
  const cur = computed(() => Math.min(page.value, pages.value));
  const items = computed(() => (source.value || []).slice((cur.value - 1) * size.value, cur.value * size.value));
  const from = computed(() => (total.value ? (cur.value - 1) * size.value + 1 : 0));
  const to = computed(() => Math.min(total.value, cur.value * size.value));
  watch(size, () => { page.value = 1; });
  return reactive({ page, size, total, pages, cur, items, from, to, initial,
    go: (p) => { page.value = Math.max(1, Math.min(pages.value, p)); },
    reset: () => { page.value = 1; } });
}

export const Pager = {
  name: 'Pager',
  props: { pg: Object, label: { type: String, default: 'Paginação' } },
  setup() { return { PAGE_SIZES }; },
  template: `
  <nav v-if="pg.total > Math.min(pg.initial, PAGE_SIZES[0])" class="pager" :aria-label="label">
    <span class="pcount" aria-live="polite">{{ pg.from }}–{{ pg.to }} de {{ pg.total }}</span>
    <span class="pbtns">
      <button type="button" :disabled="pg.cur <= 1" aria-label="Primeira página" @click="pg.go(1)">«</button>
      <button type="button" :disabled="pg.cur <= 1" aria-label="Página anterior" @click="pg.go(pg.cur - 1)">‹</button>
      <span class="pnum">{{ pg.cur }} / {{ pg.pages }}</span>
      <button type="button" :disabled="pg.cur >= pg.pages" aria-label="Próxima página" @click="pg.go(pg.cur + 1)">›</button>
      <button type="button" :disabled="pg.cur >= pg.pages" aria-label="Última página" @click="pg.go(pg.pages)">»</button>
    </span>
    <label class="inline psize">Por página<select :value="pg.size" @change="pg.size = Number($event.target.value)"><option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option></select></label>
  </nav>`,
};
