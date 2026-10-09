import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  Importacao,
  ImportacaoDetalhe,
  ItemAjuste,
  ItemImportacao,
  ResultadoAprovacao,
  ResultadoDesfazer,
} from "./types";

export const ingestaoKeys = {
  todas: ["importacoes"] as const,
  lista: ["importacoes", "lista"] as const,
  detalhe: (id: number) => ["importacoes", "detalhe", id] as const,
};

export function useImportacoes() {
  return useQuery({
    queryKey: ingestaoKeys.lista,
    queryFn: () => api.get<Importacao[]>("/importacoes"),
  });
}

export function useImportacao(id: number | null) {
  return useQuery({
    queryKey: ingestaoKeys.detalhe(id ?? 0),
    queryFn: () => api.get<ImportacaoDetalhe>(`/importacoes/${id}`),
    enabled: id !== null,
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
