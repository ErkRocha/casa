import { useQuery } from "@tanstack/react-query";

import { api, type Page } from "@/lib/api";
import type { TipoTransacao } from "@/features/filters/types";
import type { CategoriaArvore, Conta, FormaPagamento, Pessoa } from "./types";

/**
 * Cadastros mudam raramente, mas alimentam quase toda tela (filtro, select de
 * edição inline, formulário). `staleTime` alto evita refetch a cada foco.
 */
const CINCO_MINUTOS = 5 * 60 * 1000;

export const cadastroKeys = {
  pessoas: ["pessoas"] as const,
  contas: ["contas"] as const,
  categoriaArvore: ["categorias", "arvore"] as const,
  formasPagamento: ["formas-pagamento"] as const,
};

export function useContas() {
  return useQuery({
    queryKey: cadastroKeys.contas,
    queryFn: () => api.get<Page<Conta>>("/contas?limit=200&apenas_ativos=true"),
    staleTime: CINCO_MINUTOS,
    select: (page) => page.items,
  });
}

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

export interface GrupoDeCategoria {
  raizId: number;
  raizNome: string;
  tipo: TipoTransacao;
  /** As folhas do grupo; a própria raiz quando ela não tem filhas. */
  opcoes: Array<{ id: number; nome: string }>;
}

/**
 * As categorias por grupo, para os `<select>` com `<optgroup>`: o select
 * fechado mostra só o nome da folha ("Mercado"), como nas pranchetas.
 */
export function useGruposDeCategoria() {
  const { data: arvore, ...resto } = useCategoriaArvore();
  const grupos: GrupoDeCategoria[] = (arvore ?? []).map((raiz) => ({
    raizId: raiz.id,
    raizNome: raiz.nome,
    tipo: raiz.tipo,
    opcoes:
      raiz.subcategorias.length > 0
        ? raiz.subcategorias.map((sub) => ({ id: sub.id, nome: sub.nome }))
        : [{ id: raiz.id, nome: raiz.nome }],
  }));
  return { ...resto, data: grupos };
}

