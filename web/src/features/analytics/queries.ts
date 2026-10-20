import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { BaldePessoa } from "@/features/filters/types";
import { api, buildQuery } from "@/lib/api";
import type { Analises, Periodo } from "./types";

export const analyticsKeys = {
  todas: ["analytics"] as const,
  analises: (periodo: Periodo, pessoa: BaldePessoa | null) =>
    ["analytics", "analises", periodo, pessoa] as const,
};

/**
 * A tela Análises numa chamada: os quatro blocos dividem o mesmo período e a
 * mesma pessoa, e tudo vem somado do banco (D-14).
 */
export function useAnalises(periodo: Periodo, pessoa: BaldePessoa | null) {
  return useQuery({
    queryKey: analyticsKeys.analises(periodo, pessoa),
    queryFn: () =>
      api.get<Analises>(
        `/analytics/analises${buildQuery({ periodo, pessoa: pessoa === null ? null : String(pessoa) })}`,
      ),
    // Trocar de período não esvazia a tela enquanto o novo carrega.
    placeholderData: keepPreviousData,
  });
}
