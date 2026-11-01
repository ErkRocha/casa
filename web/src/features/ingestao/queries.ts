import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  Importacao,
  FiltroRevisao,
  ImportacaoDetalhe,
  ItemAjuste,
  ItemImportacao,
  ResultadoAprovacao,
  ResultadoDesfazer,
} from "./types";

export const ingestaoKeys = {
  todas: ["importacoes"] as const,
  lista: ["importacoes", "lista"] as const,
  detalhe: (id: number, filtro?: FiltroRevisao) =>
    filtro ? (["importacoes", "detalhe", id, filtro] as const) : (["importacoes", "detalhe", id] as const),
};

export function useImportacoes() {
  return useQuery({
    queryKey: ingestaoKeys.lista,
    queryFn: () => api.get<Importacao[]>("/importacoes"),
  });
}

/** O detalhe já filtrado pela API: a tela não filtra a lista (regra 10). */
export function useImportacao(id: number | null, filtro: FiltroRevisao) {
  return useQuery({
    queryKey: ingestaoKeys.detalhe(id ?? 0, filtro),
    queryFn: () => {
      const params = new URLSearchParams();
      if (filtro.status) params.set("apenas", filtro.status);
      if (filtro.falta) params.set("falta", filtro.falta);
      if (filtro.busca.trim()) params.set("busca", filtro.busca.trim());
      const qs = params.toString();
      return api.get<ImportacaoDetalhe>(`/importacoes/${id}${qs ? `?${qs}` : ""}`);
    },
    enabled: id !== null,
    // Trocar de filtro mantém a tabela anterior na tela até a nova chegar.
    placeholderData: (anterior) => anterior,
  });
}

/**
 * Invalida a ingestão e tudo que promoção mexe.
 *
 * Aprovar cria transações, então listagem e analytics ficam velhos na mesma
 * hora — e os agregados são recalculados pelo banco (D-14).
 */
function useInvalidar() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ingestaoKeys.todas });
    void client.invalidateQueries({ queryKey: ["transacoes"] });
    void client.invalidateQueries({ queryKey: ["analytics"] });
  };
}

export function useImportarArquivo() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (arquivo: File) => {
      const form = new FormData();
      form.append("arquivo", arquivo);
      return api.postForm<Importacao>("/importacoes", form);
    },
    onSuccess: invalidar,
  });
}

export function useAjustarItem() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ItemAjuste }) =>
      api.patch<ItemImportacao>(`/importacoes/itens/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useAprovarItens() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (ids: number[]) =>
      api.post<ResultadoAprovacao>("/importacoes/itens/aprovar", { ids }),
    onSuccess: invalidar,
  });
}

/**
 * Desfaz a importação inteira: soft delete das transações e dos itens dela
 * (D-21). A importação fica cancelada, com o comprovante.
 */
export function useDesfazerImportacao() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: (id: number) => api.post<ResultadoDesfazer>(`/importacoes/${id}/desfazer`),
    onSuccess: invalidar,
  });
}

export function useRejeitarItens() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ ids, motivo }: { ids: number[]; motivo?: string }) =>
      api.post<{ afetadas: number }>("/importacoes/itens/rejeitar", { ids, motivo }),
    onSuccess: invalidar,
  });
}
