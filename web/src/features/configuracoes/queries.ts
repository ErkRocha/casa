import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Categoria, Conta, FormaPagamento, TipoConta } from "@/features/cadastros/types";
import type { TipoTransacao } from "@/features/filters/types";
import { api, buildQuery } from "@/lib/api";
import type { CategoriaPluggyUso, ContasECartoes, LinhaHistorico, UsoCategorias } from "./types";

export const configuracoesKeys = {
  contas: ["configuracoes", "contas"] as const,
  usoCategorias: (competencia: string) => ["configuracoes", "categorias", competencia] as const,
  categoriasPluggy: ["configuracoes", "categorias-pluggy"] as const,
  historico: (dias: number) => ["sincronizacao", "historico", dias] as const,
};

export function useContasECartoes() {
  return useQuery({
    queryKey: configuracoesKeys.contas,
    queryFn: () => api.get<ContasECartoes>("/configuracoes/contas"),
  });
}

export function useUsoCategorias(competencia: string) {
  return useQuery({
    queryKey: configuracoesKeys.usoCategorias(competencia),
    queryFn: () =>
      api.get<UsoCategorias>(`/configuracoes/categorias${buildQuery({ competencia })}`),
  });
}

export function useCategoriasPluggy() {
  return useQuery({
    queryKey: configuracoesKeys.categoriasPluggy,
    queryFn: () => api.get<CategoriaPluggyUso[]>("/configuracoes/categorias-pluggy"),
  });
}

export function useHistorico(dias = 30) {
  return useQuery({
    queryKey: configuracoesKeys.historico(dias),
    queryFn: () => api.get<LinhaHistorico[]>(`/sincronizacao/historico${buildQuery({ dias })}`),
  });
}

/** Cadastro mexeu: as telas de configuração e os selects das outras telas. */
function useInvalidarCadastros() {
  const client = useQueryClient();
  return () => {
    for (const chave of [["configuracoes"], ["contas"], ["formas-pagamento"], ["categorias"], ["transacoes"]]) {
      void client.invalidateQueries({ queryKey: chave });
    }
  };
}

export function useCriarConta() {
  const invalidar = useInvalidarCadastros();
  return useMutation({
    mutationFn: (payload: { nome: string; tipo: TipoConta; titular_id: number | null }) =>
      api.post<Conta>("/contas", payload),
    onSuccess: invalidar,
  });
}

/** Renomear: a conta pelo `nome`, o cartão (forma de pagamento) pelo `apelido`. */
export function useRenomear() {
  const invalidar = useInvalidarCadastros();
  return useMutation({
    mutationFn: ({
      tipo,
      id,
      nome,
    }: {
      tipo: "conta" | "cartao";
      id: number;
      nome: string;
    }): Promise<Conta | FormaPagamento> =>
      tipo === "conta"
        ? api.patch<Conta>(`/contas/${id}`, { nome })
        : api.patch<FormaPagamento>(`/formas-pagamento/${id}`, { apelido: nome }),
    onSuccess: invalidar,
  });
}

export function useCriarCategoria() {
  const invalidar = useInvalidarCadastros();
  return useMutation({
    mutationFn: (payload: { nome: string; tipo: TipoTransacao; categoria_pai_id: number | null }) =>
      api.post<Categoria>("/categorias", payload),
    onSuccess: invalidar,
  });
}

/**
 * A tradução de uma categoria da Pluggy (D-21): cria, troca ou tira o
 * mapeamento. Tirar é soft delete, como todo o resto (regra 2).
 */
export function useTraduzirCategoriaPluggy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ linha, categoriaId }: { linha: CategoriaPluggyUso; categoriaId: number | null }) => {
      if (linha.mapeamento_id !== null) {
        return categoriaId === null
          ? api.delete(`/categorias-pluggy/${linha.mapeamento_id}`)
          : api.patch(`/categorias-pluggy/${linha.mapeamento_id}`, {
              categoria_id: categoriaId,
              ativo: true,
            });
      }
      if (categoriaId === null) return Promise.resolve(null);
      return api.post("/categorias-pluggy", {
        pluggy_categoria_id: linha.pluggy_categoria_id,
        pluggy_categoria_nome: linha.pluggy_categoria_nome,
        categoria_id: categoriaId,
      });
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: configuracoesKeys.categoriasPluggy }),
  });
}
