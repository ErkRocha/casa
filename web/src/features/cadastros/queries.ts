import { useQuery } from "@tanstack/react-query";

import { api, type Page } from "@/lib/api";
import type { CategoriaArvore, FormaPagamento, Pessoa } from "./types";

/**
 * Cadastros mudam raramente, mas alimentam quase toda tela (filtro, select de
 * edição inline, formulário). `staleTime` alto evita refetch a cada foco.
 */
const CINCO_MINUTOS = 5 * 60 * 1000;

export const cadastroKeys = {
  pessoas: ["pessoas"] as const,
  categoriaArvore: ["categorias", "arvore"] as const,
  formasPagamento: ["formas-pagamento"] as const,
};

export function usePessoas() {
  return useQuery({
    queryKey: cadastroKeys.pessoas,
    queryFn: () => api.get<Page<Pessoa>>("/pessoas?limit=200&apenas_ativos=true"),
    staleTime: CINCO_MINUTOS,
    select: (page) => page.items,
  });
}

export function useCategoriaArvore() {
  return useQuery({
    queryKey: cadastroKeys.categoriaArvore,
    queryFn: () => api.get<CategoriaArvore[]>("/categorias/arvore/completa"),
    staleTime: CINCO_MINUTOS,
  });
}

export function useFormasPagamento() {
  return useQuery({
    queryKey: cadastroKeys.formasPagamento,
    queryFn: () =>
      api.get<Page<FormaPagamento>>("/formas-pagamento?limit=200&apenas_ativos=true"),
    staleTime: CINCO_MINUTOS,
    select: (page) => page.items,
  });
}

/** Opções achatadas "Alimentação › Mercado" para os selects de categoria. */
export function useCategoriaOpcoes() {
  const { data: arvore, ...resto } = useCategoriaArvore();

  const opcoes = (arvore ?? []).flatMap((raiz) =>
    raiz.subcategorias.length > 0
      ? raiz.subcategorias.map((sub) => ({
          id: sub.id,
          label: `${raiz.nome} › ${sub.nome}`,
          raizId: raiz.id,
          raizNome: raiz.nome,
        }))
      : [{ id: raiz.id, label: raiz.nome, raizId: raiz.id, raizNome: raiz.nome }],
  );

  return { ...resto, data: opcoes };
}
