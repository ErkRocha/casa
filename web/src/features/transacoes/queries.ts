import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, buildQuery } from "@/lib/api";
import { paraQuery, type FiltrosLancamentos } from "./filtros";
import type {
  LoteAtribuir,
  LoteResponse,
  TotalDia,
  Transacao,
  TransacaoCreate,
  TransacaoListagem,
  TransacaoUpdate,
} from "./types";

export const transacaoKeys = {
  todas: ["transacoes"] as const,
  lancamentos: (filtros: FiltrosLancamentos) => ["transacoes", "lancamentos", filtros] as const,
  dias: (filtros: FiltrosLancamentos) => ["transacoes", "dias", filtros] as const,
};

/** Página da listagem: o máximo que a API aceita (`limit` <= 200). */
const POR_PAGINA = 100;

/**
 * Os lançamentos do recorte, página a página ("Carregar mais"). Os totais
 * vêm na primeira página, somados no banco com o mesmo filtro (D-14).
 */
export function useLancamentos(filtros: FiltrosLancamentos) {
  return useInfiniteQuery({
    queryKey: transacaoKeys.lancamentos(filtros),
    queryFn: ({ pageParam }) => {
      const query = buildQuery({ ...paraQuery(filtros), offset: pageParam, limit: POR_PAGINA });
      return api.get<TransacaoListagem>(`/transacoes${query}`);
    },
    initialPageParam: 0,
    getNextPageParam: (ultima) => {
      const proxima = ultima.offset + ultima.items.length;
      return proxima < ultima.total ? proxima : undefined;
    },
    // A lista anterior fica na tela enquanto a nova carrega: sem isso ela
    // pisca em branco a cada filtro.
    placeholderData: keepPreviousData,
  });
}

/** O total de cada dia do recorte, para o cabeçalho de cada dia. */
export function useDiasLancamentos(filtros: FiltrosLancamentos) {
  return useQuery({
    queryKey: transacaoKeys.dias(filtros),
    queryFn: () => api.get<TotalDia[]>(`/transacoes/dias${buildQuery(paraQuery(filtros))}`),
    placeholderData: keepPreviousData,
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
