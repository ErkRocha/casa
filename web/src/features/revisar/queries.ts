import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ConfirmarTransferencia,
  GrupoDuplicata,
  ItemRevisar,
  ResultadoRevisao,
  RevisarResumo,
  TransferenciaRevisar,
} from "./types";

export const revisarKeys = {
  todas: ["revisar"] as const,
  resumo: ["revisar", "resumo"] as const,
  itens: ["revisar", "itens"] as const,
  duplicatas: ["revisar", "duplicatas"] as const,
  transferencias: ["revisar", "transferencias"] as const,
};

/**
 * Quantos itens esperam decisão, por motivo. Alimenta o contador de
 * "Revisar" na navegação e o cartão do Início.
 */
export function useRevisarResumo() {
  return useQuery({
    queryKey: revisarKeys.resumo,
    queryFn: () => api.get<RevisarResumo>("/revisar/resumo"),
  });
}

/** Todos os pendentes, com o motivo de cada um. */
export function useItensRevisar() {
  return useQuery({
    queryKey: revisarKeys.itens,
    queryFn: () => api.get<ItemRevisar[]>("/revisar/itens"),
  });
}

export function useDuplicatas() {
  return useQuery({
    queryKey: revisarKeys.duplicatas,
    queryFn: () => api.get<GrupoDuplicata[]>("/revisar/duplicatas"),
  });
}

export function useTransferencias() {
  return useQuery({
    queryKey: revisarKeys.transferencias,
    queryFn: () => api.get<TransferenciaRevisar[]>("/revisar/transferencias"),
  });
}

/**
 * Toda decisão da revisão mexe no staging e, quando aprova, em transações:
 * listagem, Início e análises recalculam no banco (D-14).
 */
function useInvalidar() {
  const client = useQueryClient();
  return () => {
    for (const chave of [["revisar"], ["importacoes"], ["transacoes"], ["analytics"], ["sincronizacao"]]) {
      void client.invalidateQueries({ queryKey: chave });
    }
  };
}

export function useResolverDuplicata() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (payload: { manter_ids: number[]; descartar_ids: number[] }) =>
      api.post<ResultadoRevisao>("/revisar/duplicatas/resolver", payload),
    onSuccess: invalidar,
  });
}

export function useConfirmarTransferencias() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (itens: ConfirmarTransferencia[]) =>
      api.post<ResultadoRevisao>("/revisar/transferencias/confirmar", { itens }),
    onSuccess: invalidar,
  });
}

export function useNaoETransferencia() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, tipo }: { id: number; tipo?: "despesa" | "receita" }) =>
      api.post<ItemRevisar>(`/revisar/transferencias/${id}/nao-e`, tipo ? { tipo } : {}),
    onSuccess: invalidar,
  });
}
