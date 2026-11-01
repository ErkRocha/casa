import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { BaldePessoa } from "@/features/filters/types";
import { api, buildQuery } from "@/lib/api";
import type { Analises, GastoPorBanco, Periodo } from "./types";

export const analyticsKeys = {
  todas: ["analytics"] as const,
  analises: (periodo: Periodo, pessoa: BaldePessoa | null) =>
    ["analytics", "analises", periodo, pessoa] as const,
  porBanco: (inicio: string, fim: string, pessoa: BaldePessoa | null) =>
    ["analytics", "por-banco", inicio, fim, pessoa] as const,
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

/** "Por banco" no mesmo período e pessoa da tela, somado no banco (D-14). */
export function usePorBanco(inicio: string, fim: string, pessoa: BaldePessoa | null) {
  return useQuery({
    queryKey: analyticsKeys.porBanco(inicio, fim, pessoa),
    queryFn: () =>
      api.get<GastoPorBanco>(
        `/analytics/por-banco${buildQuery({
          competencia_inicio: inicio,
          competencia_fim: fim,
          pessoa: pessoa === null ? null : String(pessoa),
        })}`,
      ),
    placeholderData: keepPreviousData,
  });
}
