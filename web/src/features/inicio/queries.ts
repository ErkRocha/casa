import { useQuery } from "@tanstack/react-query";

import { api, buildQuery } from "@/lib/api";
import type { TransacaoListagem } from "@/features/transacoes/types";
import type { Inicio } from "./types";

/**
 * Debaixo de `analytics` e `transacoes` de propósito: as mutações que já
 * invalidam essas chaves (editar, aprovar, desfazer) atualizam o Início sem
 * precisar saber que ele existe.
 */
export const inicioKeys = {
  resumo: (competencia: string) => ["analytics", "inicio", competencia] as const,
  ultimos: (competencia: string) => ["transacoes", "ultimos", competencia] as const,
};

export function useInicio(competencia: string) {
  return useQuery({
    queryKey: inicioKeys.resumo(competencia),
    queryFn: () => api.get<Inicio>(`/analytics/inicio${buildQuery({ competencia })}`),
    placeholderData: (anterior) => anterior,
  });
}

/** Os lançamentos mais recentes do mês (por data, mais novo primeiro). */
export function useUltimosLancamentos(competencia: string, limite = 6) {
  return useQuery({
    queryKey: inicioKeys.ultimos(competencia),
    queryFn: () =>
      api.get<TransacaoListagem>(
        `/transacoes${buildQuery({
          competencia_inicio: competencia,
          competencia_fim: competencia,
          limit: limite,
          offset: 0,
        })}`,
      ),
  });
}
