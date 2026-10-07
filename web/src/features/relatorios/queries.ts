import { useQuery } from "@tanstack/react-query";

import { api, buildQuery, type Page } from "@/lib/api";
import type { RelatorioDetalhe, RelatorioResumo } from "./types";

export const relatorioKeys = {
  todas: ["relatorios"] as const,
  lista: ["relatorios", "lista"] as const,
  detalhe: (id: number) => ["relatorios", "detalhe", id] as const,
};

/**
 * Todos os relatórios vigentes, mais recente primeiro. São um por mês: 200
 * cobrem mais de uma década, e a tela precisa da lista inteira para montar
 * a coluna de meses.
 */
export function useRelatorios() {
  return useQuery({
    queryKey: relatorioKeys.lista,
    queryFn: () =>
      api.get<Page<RelatorioResumo>>(`/relatorios${buildQuery({ limit: 200 })}`),
  });
}

export function useRelatorio(id: number | null) {
  return useQuery({
    queryKey: relatorioKeys.detalhe(id ?? 0),
    queryFn: () => api.get<RelatorioDetalhe>(`/relatorios/${id}`),
    enabled: id !== null,
  });
}
