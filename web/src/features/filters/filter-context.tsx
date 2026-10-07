import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { FILTROS_VAZIOS, type Filtros } from "./types";

/**
 * Estado de filtro compartilhado pelas telas.
 *
 * Vive acima do roteamento: trocar de Transações para Analytics mantém o
 * recorte, que é justamente o ponto de "filtros compartilhados" da fase 4.
 */

interface FilterContextValue {
  filtros: Filtros;
  setFiltros: (patch: Partial<Filtros>) => void;
  alternarCategoria: (id: number) => void;
  alternarFormaPagamento: (id: number) => void;
  limparTudo: () => void;
}

const FilterContext = createContext<FilterContextValue | null>(null);

export function FilterProvider({ children }: { children: React.ReactNode }) {
  const [filtros, setEstado] = useState<Filtros>(FILTROS_VAZIOS);

  const setFiltros = useCallback((patch: Partial<Filtros>) => {
    setEstado((atual) => ({ ...atual, ...patch }));
  }, []);

  const alternarCategoria = useCallback((id: number) => {
    setEstado((atual) => ({
      ...atual,
      categoriaIds: atual.categoriaIds.includes(id)
        ? atual.categoriaIds.filter((x) => x !== id)
        : [...atual.categoriaIds, id],
    }));
  }, []);

  const alternarFormaPagamento = useCallback((id: number) => {
    setEstado((atual) => ({
      ...atual,
      formaPagamentoIds: atual.formaPagamentoIds.includes(id)
        ? atual.formaPagamentoIds.filter((x) => x !== id)
        : [...atual.formaPagamentoIds, id],
    }));
  }, []);

  const limparTudo = useCallback(() => setEstado(FILTROS_VAZIOS), []);

  const value = useMemo(
    () => ({ filtros, setFiltros, alternarCategoria, alternarFormaPagamento, limparTudo }),
    [filtros, setFiltros, alternarCategoria, alternarFormaPagamento, limparTudo],
  );

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- o hook é inseparável do provider; o custo é só perder o estado deste arquivo no hot reload.
export function useFiltros(): FilterContextValue {
  const context = useContext(FilterContext);
  if (!context) throw new Error("useFiltros precisa estar dentro de <FilterProvider>");
  return context;
}
