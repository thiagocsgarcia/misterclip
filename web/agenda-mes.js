/**
 * Carrega os itens da agenda por mês, sob demanda: um pedido por mês, cache em memória, pré-carga silenciosa dos meses
 * vizinhos (navegar fica instantâneo) e erro claro quando a conexão falha. Mesmo modelo do `useAgendaMes` do SIGEM.
 *
 *   const cal = useAgendaMes({ fetcher: (ym) => api(`/api/calendar?month=${ym}`) });   // fetcher devolve { itens: [...] }
 *   cal.carregar('2026-11');   cal.itens('2026-11');   cal.atualizar('2026-11');   cal.invalidar();
 */
import { ref, shallowRef } from './vendor/vue.esm-browser.prod.js';

export const deslocarMes = (ym, delta) => {
  const [a, m] = ym.split('-').map(Number);
  const d = new Date(a, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

export function useAgendaMes({ fetcher, prefetch = true, extrair = (json) => json.itens }) {
  const cache = shallowRef({});
  const pendentes = new Map();
  const carregando = ref(false);
  const erro = ref('');
  let atual = null;

  const guardar = (ym, itens) => { cache.value = { ...cache.value, [ym]: itens }; };

  function buscar(ym, forcar = false) {
    if (!forcar && cache.value[ym]) return Promise.resolve(cache.value[ym]);
    if (pendentes.has(ym)) return pendentes.get(ym);
    const p = fetcher(ym)
      .then((json) => { const itens = extrair(json) ?? []; guardar(ym, itens); return itens; })
      .finally(() => pendentes.delete(ym));
    pendentes.set(ym, p);
    return p;
  }

  function precarregar(ym) {
    if (!prefetch || navigator.connection?.saveData) return;
    const agendar = window.requestIdleCallback ?? ((fn) => setTimeout(fn, 400));
    agendar(() => { for (const v of [deslocarMes(ym, 1), deslocarMes(ym, -1)]) buscar(v).catch(() => {}); });
  }

  async function carregar(ym) {
    atual = ym;
    erro.value = '';
    if (cache.value[ym]) { precarregar(ym); return; }
    carregando.value = true;
    try {
      await buscar(ym);
      precarregar(ym);
    } catch (e) {
      if (atual === ym) erro.value = e?.message?.startsWith('Não consegui') ? e.message : 'Não foi possível carregar este mês. Verifique a conexão e tente de novo.';
    } finally {
      if (atual === ym) carregando.value = false;
    }
  }

  /** Busca de novo sem esvaziar o cache (a tela não pisca): usado depois de agendar/cancelar e no vigia lento. */
  async function atualizar(ym) {
    try { await buscar(ym, true); } catch { /* mantém o que já está na tela */ }
  }

  return {
    cache, carregando, erro, carregar, atualizar,
    itens: (ym) => cache.value[ym] ?? [],
    invalidar: () => { cache.value = {}; },
    tentarNovamente: () => atual && carregar(atual),
  };
}
