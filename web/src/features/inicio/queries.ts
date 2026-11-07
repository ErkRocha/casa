import { useQuery } from "@tanstack/react-query";

import { api, buildQuery } from "@/lib/api";
import type { TransacaoListagem } from "@/features/transacoes/types";
import type { GastosJanela, Inicio } from "./types";

/**
 * Debaixo de `analytics` e `transacoes` de propósito: as mutações que já
 * invalidam essas chaves (editar, aprovar, desfazer) atualizam o Início sem
 * precisar saber que ele existe.
 */
export const inicioKeys = {
  resumo: (competencia: string) => ["analytics", "inicio", competencia] as const,
  gastos30Dias: (params: ParamsGastos30Dias) =>
    ["analytics", "inicio", "gastos-30-dias", params] as const,
  ultimos: (competencia: string) => ["transacoes", "ultimos", competencia] as const,
};

/** O que o gráfico de linhas pede: pessoa, séries visíveis (nulo = todas) e a soma. */
export interface ParamsGastos30Dias {
  pessoaId: number | null;
  series: string[] | null;
  somar: boolean;
}

export function useInicio(competencia: string) {
  return useQuery({
    queryKey: inicioKeys.resumo(competencia),
    queryFn: () => api.get<Inicio>(`/analytics/inicio${buildQuery({ competencia })}`),
    placeholderData: (anterior) => anterior,
  });
}

/** Gasto acumulado dos últimos 30 dias; igual em qualquer mês escolhido (D-28). */
export function useGastos30Dias(params: ParamsGastos30Dias) {
  return useQuery({
    queryKey: inicioKeys.gastos30Dias(params),
    queryFn: () =>
      api.get<GastosJanela>(
        `/analytics/inicio/gastos-30-dias${buildQuery({
          pessoa_id: params.pessoaId,
          series: params.series ?? undefined,
          somar: params.somar ? "true" : undefined,
        })}`,
      ),
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
