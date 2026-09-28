import { useCategoriaArvore, useFormasPagamento, usePessoas } from "@/features/cadastros/queries";
import { rotuloDoBalde } from "./baldes";
import { useFiltros } from "./filter-context";
import { PERIODO_LABELS, temFiltroAtivo } from "./types";

/**
 * Chips do que está filtrado agora, cada um removível.
 *
 * Existe porque filtro combinável escondido atrás de um popover some da vista:
 * sem os chips, o usuário vê uma tabela curta e não sabe por quê.
 */
export function ActiveChips() {
  const { filtros, setFiltros, alternarCategoria, alternarFormaPagamento } = useFiltros();
  const { data: arvore = [] } = useCategoriaArvore();
  const { data: pessoas = [] } = usePessoas();
  const { data: formas = [] } = useFormasPagamento();

  if (!temFiltroAtivo(filtros)) return null;

  const chips: Array<{ chave: string; label: string; remover: () => void }> = [];

  if (filtros.periodo !== "todo_periodo") {
    chips.push({
      chave: "periodo",
      label: `Período: ${PERIODO_LABELS[filtros.periodo]}`,
      remover: () => setFiltros({ periodo: "todo_periodo" }),
    });
  }

  for (const id of filtros.categoriaIds) {
    const raiz = arvore.find((r) => r.id === id);
    const sub = arvore.flatMap((r) => r.subcategorias.map((s) => ({ s, r }))).find((x) => x.s.id === id);
    const label = raiz ? raiz.nome : sub ? `${sub.r.nome} › ${sub.s.nome}` : `Categoria ${id}`;
    chips.push({ chave: `cat-${id}`, label, remover: () => alternarCategoria(id) });
  }

  if (filtros.pessoa !== null) {
    chips.push({
      chave: "pessoa",
      label: `Pessoa: ${rotuloDoBalde(filtros.pessoa, pessoas)}`,
      remover: () => setFiltros({ pessoa: null }),
    });
  }

  for (const id of filtros.formaPagamentoIds) {
    const forma = formas.find((f) => f.id === id);
    chips.push({
      chave: `fp-${id}`,
      label: forma?.apelido ?? `Pagamento ${id}`,
      remover: () => alternarFormaPagamento(id),
    });
  }

  if (filtros.local) {
    chips.push({
      chave: "local",
      label: `Local: ${filtros.local}`,
      remover: () => setFiltros({ local: "" }),
    });
  }

  if (filtros.valorMin || filtros.valorMax) {
    chips.push({
      chave: "valor",
      label: `Valor: ${filtros.valorMin || "0"} – ${filtros.valorMax || "∞"}`,
      remover: () => setFiltros({ valorMin: "", valorMax: "" }),
    });
  }

  if (filtros.texto) {
    chips.push({
      chave: "texto",
      label: `"${filtros.texto}"`,
      remover: () => setFiltros({ texto: "" }),
    });
  }

  return (
    <div className="flex flex-wrap gap-3 px-14 pb-8">
      {chips.map((chip) => (
        <span
          key={chip.chave}
          className="bg-surface-sunken text-text-secondary text-caption-lg inline-flex items-center gap-3 rounded-md py-2 pr-3 pl-5 font-medium"
        >
          {chip.label}
          <button
            type="button"
            onClick={chip.remover}
            aria-label={`Remover filtro ${chip.label}`}
            className="hover:bg-surface flex size-8 cursor-pointer items-center justify-center rounded-full text-[10px]"
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}
