import { useQuery } from "@tanstack/react-query";

import { api, buildQuery } from "@/lib/api";
import { filtrosParaQuery, type Filtros } from "@/features/filters/types";
import type { AnalyticsResumo } from "./types";

export const analyticsKeys = {
  todas: ["analytics"] as const,
  resumo: (filtros: Filtros, categoriaPaiId: number | null) =>
    ["analytics", "resumo", filtros, categoriaPaiId] as const,
};

/**
 * Os cinco painéis numa chamada.
 *
 * Um endpoint em vez de cinco porque eles compartilham o mesmo recorte: cinco
 * requisições paralelas com o mesmo WHERE fariam o Postgres varrer o mesmo
 * índice cinco vezes por render.
 */
export function useAnalyticsResumo(filtros: Filtros, categoriaPaiId: number | null) {
  return useQuery({
    queryKey: analyticsKeys.resumo(filtros, categoriaPaiId),
    queryFn: () => {
      const query = buildQuery({
        ...filtrosParaQuery(filtros),
        categoria_pai_id: categoriaPaiId,
      });
      return api.get<AnalyticsResumo>(`/analytics/resumo${query}`);
    },
    // Sem isto os gráficos somem a cada tecla digitada no filtro de texto.
    placeholderData: (anterior) => anterior,
  });
}
