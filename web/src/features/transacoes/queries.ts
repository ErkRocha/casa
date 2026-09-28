import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, buildQuery } from "@/lib/api";
import { filtrosParaQuery, type Filtros } from "@/features/filters/types";
import type {
  LoteAtribuir,
  LoteResponse,
  Transacao,
  TransacaoCreate,
  TransacaoListagem,
  TransacaoUpdate,
} from "./types";

export const transacaoKeys = {
  todas: ["transacoes"] as const,
  lista: (filtros: Filtros, offset: number, limit: number) =>
    ["transacoes", "lista", filtros, offset, limit] as const,
};

export function useTransacoes(filtros: Filtros, offset: number, limit: number) {
  return useQuery({
    queryKey: transacaoKeys.lista(filtros, offset, limit),
    queryFn: () => {
      const query = buildQuery({ ...filtrosParaQuery(filtros), offset, limit });
      return api.get<TransacaoListagem>(`/transacoes${query}`);
    },
    // Mantém a página anterior visível enquanto a nova carrega — sem isso, a
    // tabela pisca em branco a cada tecla digitada no filtro.
    placeholderData: (anterior) => anterior,
  });
}

/**
 * Invalida tudo que depende de transação.
 *
 * Analytics inclusive: os agregados mudam quando uma transação muda, e é o
 * banco que recalcula (D-14).
 */
function useInvalidarTransacoes() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: transacaoKeys.todas });
    void client.invalidateQueries({ queryKey: ["analytics"] });
  };
}

export function useCriarTransacao() {
  const invalidar = useInvalidarTransacoes();
  return useMutation({
    mutationFn: (payload: TransacaoCreate & { local_nome?: string }) => {
      const { local_nome, ...corpo } = payload;
      const query = buildQuery({ local_nome: local_nome || null });
      return api.post<Transacao>(`/transacoes${query}`, corpo);
    },
    onSuccess: invalidar,
  });
}

export function useAtualizarTransacao() {
  const invalidar = useInvalidarTransacoes();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TransacaoUpdate }) =>
      api.patch<Transacao>(`/transacoes/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useRemoverTransacao() {
  const invalidar = useInvalidarTransacoes();
  return useMutation({
    mutationFn: (id: number) => api.delete<{ ok: boolean }>(`/transacoes/${id}`),
    onSuccess: invalidar,
  });
}

export function useAtribuirEmLote() {
  const invalidar = useInvalidarTransacoes();
  return useMutation({
    mutationFn: (payload: LoteAtribuir) =>
      api.post<LoteResponse>("/transacoes/lote/atribuir", payload),
    onSuccess: invalidar,
  });
}

export function useExcluirEmLote() {
  const invalidar = useInvalidarTransacoes();
  return useMutation({
    mutationFn: (ids: number[]) => api.post<LoteResponse>("/transacoes/lote/excluir", { ids }),
    onSuccess: invalidar,
  });
}
