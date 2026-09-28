import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, buildQuery, type Page } from "@/lib/api";

/** Espelho de `RegraRead` da API. */
export interface Regra {
  id: number;
  padrao: string;
  tipo_match: TipoMatch;
  categoria_id: number | null;
  local_id: number | null;
  pessoa_id: number | null;
  /** Menor roda primeiro. */
  prioridade: number;
  /** `usuario` | `correcao_automatica`. */
  criada_por: string;
  /** Quantas vezes já foi reforçada por uma correção. */
  acertos: number;
  ativo: boolean;
  criado_em: string;
}

export type TipoMatch = "contem" | "regex" | "exato";

export const TIPO_MATCH_LABEL: Record<TipoMatch, string> = {
  contem: "contém",
  exato: "exato",
  regex: "regex",
};

export interface RegraCreate {
  padrao: string;
  tipo_match: TipoMatch;
  categoria_id: number | null;
  pessoa_id: number | null;
  prioridade?: number;
}

export const regraKeys = {
  todas: ["regras"] as const,
  lista: ["regras", "lista"] as const,
};

export function useRegras() {
  return useQuery({
    queryKey: regraKeys.lista,
    queryFn: () => api.get<Page<Regra>>("/regras?limit=200"),
    select: (page) => page.items,
  });
}

function useInvalidar() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: regraKeys.todas });
    // Reaplicar muda as sugestões do staging.
    void client.invalidateQueries({ queryKey: ["importacoes"] });
  };
}

export function useCriarRegra() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (payload: RegraCreate) => api.post<Regra>("/regras", payload),
    onSuccess: invalidar,
  });
}

export function useAtualizarRegra() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<RegraCreate> & { ativo?: boolean } }) =>
      api.patch<Regra>(`/regras/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useRemoverRegra() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (id: number) => api.delete<{ ok: boolean }>(`/regras/${id}`),
    onSuccess: invalidar,
  });
}

/**
 * Reaplica as regras aos itens ainda pendentes.
 *
 * É o que fecha o ciclo: corrigir uma linha e resolver as outras iguais sem
 * tocar em cada uma (D-09).
 */
export function useReaplicarRegras() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (importacaoId?: number) =>
      api.post<{ avaliados: number; alterados: number }>(
        `/regras/reaplicar${buildQuery({ importacao_id: importacaoId ?? null })}`,
      ),
    onSuccess: invalidar,
  });
}

/** Prévia do casamento, para cadastrar regra sem tentativa e erro. */
export function useTestarRegra() {
  return useMutation({
    mutationFn: (payload: { padrao: string; tipo_match: TipoMatch; texto: string }) =>
      api.post<{ casa: boolean }>("/regras/testar", payload),
  });
}
