import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiCompras, buildQuery } from "@/lib/api";
import { novoIdCliente } from "@/features/compras/id-cliente";
import { comprasKeys } from "@/features/compras/queries";
import {
  CHAVE_ROTEIRO,
  chaveDoPasso,
  comPassoFeito,
  feitoDaLinha,
  passoEmVoo,
} from "./passos-feitos";
import type {
  ListaCardapio,
  MedidaBase,
  Pessoa,
  PassoFeitoLinha,
  ReceitaCorpo,
  ReceitaDetalhe,
  ReceitasPagina,
  Refeicao,
  Roteiro,
  Semana,
  SemanaCopiada,
  Sessao,
  TipoRefeicao,
} from "./types";

export const cardapioKeys = {
  todas: ["cardapio"] as const,
  semana: (inicio: string) => ["cardapio", "semana", inicio] as const,
  roteiro: (semanaId: number) => ["cardapio", "roteiro", semanaId] as const,
  previa: (semanaId: number) => ["cardapio", "previa", semanaId] as const,
  pessoas: ["cardapio", "pessoas"] as const,
  receitas: (busca: string, tipo: TipoRefeicao | null) =>
    ["cardapio", "receitas", busca, tipo ?? "todos"] as const,
  receita: (id: number) => ["cardapio", "receita", id] as const,
};

/**
 * O cardápio é planejado com calma, não com os dois no mercado (api-cardapio):
 * lê de novo ao abrir e depois de cada escrita. A exceção, os passos feitos,
 * chega pelo polling da lista.
 */

/** A semana pela segunda-feira. Semana que não existe vira `null` (a API dá 404). */
export function useSemana(inicio: string, ligado = true) {
  return useQuery({
    queryKey: cardapioKeys.semana(inicio),
    enabled: ligado,
    queryFn: async (): Promise<Semana | null> => {
      try {
        return await apiCompras.get<Semana>(`/semanas/${inicio}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  });
}

export function usePessoasDoCardapio() {
  return useQuery({
    queryKey: cardapioKeys.pessoas,
    queryFn: () => apiCompras.get<Pessoa[]>("/pessoas"),
    staleTime: 5 * 60_000,
  });
}

export function useRoteiro(semanaId: number | undefined) {
  return useQuery({
    queryKey: cardapioKeys.roteiro(semanaId ?? 0),
    enabled: semanaId !== undefined,
    queryFn: () => apiCompras.get<Roteiro>(`/semanas/${semanaId}/preparo`),
    // Quem traz o "feito" do outro celular é o polling de /mudancas.
    refetchOnWindowFocus: false,
  });
}

/** A prévia da lista (GET): o que a geração faria, sem gravar nada. */
export function useListaPrevia(semanaId: number | undefined, ligado: boolean) {
  return useQuery({
    queryKey: cardapioKeys.previa(semanaId ?? 0),
    enabled: semanaId !== undefined && ligado,
    queryFn: () => apiCompras.get<ListaCardapio>(`/semanas/${semanaId}/lista`),
    staleTime: 10_000,
  });
}

export function useReceitas(busca: string, tipo: TipoRefeicao | null = null) {
  return useQuery({
    queryKey: cardapioKeys.receitas(busca.trim(), tipo),
    queryFn: () =>
      apiCompras.get<ReceitasPagina>(
        `/receitas${buildQuery({ busca: busca.trim(), tipo, limite: 30 })}`,
      ),
    placeholderData: (anterior) => anterior,
  });
}

export function useReceita(id: number | null) {
  return useQuery({
    queryKey: cardapioKeys.receita(id ?? 0),
    enabled: id !== null,
    queryFn: () => apiCompras.get<ReceitaDetalhe>(`/receitas/${id}`),
  });
}

// --- escritas ---------------------------------------------------------------------

/** Depois de escrever, relê o cardápio todo: semana, roteiro, prévia, receitas. */
function useRelerCardapio() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: cardapioKeys.todas });
}

export function useCriarSemana(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: (inicio: string) => apiCompras.post<Semana>("/semanas", { inicio }, quem),
    onSuccess: reler,
  });
}

export function useCopiarSemana(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({ semanaId, destino }: { semanaId: number; destino: string }) =>
      apiCompras.post<SemanaCopiada>(`/semanas/${semanaId}/copiar`, { destino }, quem),
    onSuccess: reler,
  });
}

export function useAdicionarRefeicao(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({
      semanaId,
      ...corpo
    }: {
      semanaId: number;
      dia: string;
      tipo: TipoRefeicao;
      receita_id: number;
    }) => apiCompras.post<Refeicao>(`/semanas/${semanaId}/refeicoes`, corpo, quem),
    onSuccess: reler,
  });
}

export function useTrocarReceita(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({ refeicaoId, receitaId }: { refeicaoId: number; receitaId: number }) =>
      apiCompras.patch<Refeicao>(`/refeicoes/${refeicaoId}`, { receita_id: receitaId }, quem),
    onSuccess: reler,
  });
}

export function useDefinirPessoas(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({
      refeicaoId,
      pessoas,
    }: {
      refeicaoId: number;
      /** `porcoes` nulo volta ao padrão do perfil. */
      pessoas: Array<{ pessoa_id: number; porcoes: string | null }>;
    }) => apiCompras.put<Refeicao>(`/refeicoes/${refeicaoId}/pessoas`, pessoas, quem),
    onSuccess: reler,
  });
}

export function useRemoverRefeicao(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: (refeicaoId: number) =>
      apiCompras.delete<Refeicao>(`/refeicoes/${refeicaoId}`, quem),
    onSuccess: reler,
  });
}

export function useCriarSessao(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({
      semanaId,
      data,
      rotulo,
    }: {
      semanaId: number;
      data: string;
      rotulo: string | null;
    }) => apiCompras.post<Sessao>(`/semanas/${semanaId}/sessoes`, { data, rotulo }, quem),
    onSuccess: reler,
  });
}

/** Cria (com `id_cliente`) ou substitui (PUT) uma receita. */
export function useSalvarReceita(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: ({
      id,
      idCliente,
      corpo,
    }: {
      /** Sem `id`: receita nova. */
      id: number | null;
      idCliente: string;
      corpo: ReceitaCorpo;
    }) =>
      id === null
        ? apiCompras.post<ReceitaDetalhe>("/receitas", { ...corpo, id_cliente: idCliente }, quem)
        : apiCompras.put<ReceitaDetalhe>(`/receitas/${id}`, corpo, quem),
    onSuccess: reler,
  });
}

export function useDuplicarReceita(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: (id: number) => apiCompras.post<ReceitaDetalhe>(`/receitas/${id}/duplicar`, {}, quem),
    onSuccess: reler,
  });
}

export function useConferirReceita(quem: string) {
  const reler = useRelerCardapio();
  return useMutation({
    mutationFn: (id: number) => apiCompras.post<ReceitaDetalhe>(`/receitas/${id}/conferir`, {}, quem),
    onSuccess: reler,
  });
}

/** "1 unidade de Cebola tem 150 g": `PATCH /produtos/{id}` com a medida. */
export function useCadastrarMedida(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      produtoId,
      medida_base,
      medida_por_unidade,
    }: {
      produtoId: number;
      medida_base: MedidaBase;
      medida_por_unidade: string | null;
    }) => apiCompras.patch<unknown>(`/produtos/${produtoId}`, { medida_base, medida_por_unidade }, quem),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cardapioKeys.todas });
      void queryClient.invalidateQueries({ queryKey: ["compras", "produtos"] });
    },
  });
}

/**
 * Mandar a prévia para a lista (POST). Depois, a Lista relê: os itens
 * aparecem lá com a origem "cardápio".
 */
export function useGravarLista(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (semanaId: number) =>
      apiCompras.post<ListaCardapio>(`/semanas/${semanaId}/lista`, {}, quem),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cardapioKeys.todas });
      void queryClient.invalidateQueries({ queryKey: comprasKeys.lista });
    },
  });
}

/**
 * Marcar e desfazer um passo do roteiro, otimista como o "comprado" da lista:
 * a caixa muda no toque; se a API recusar, volta ao que era e a tela diz por
 * quê. O outro celular vê pelo `/mudancas` (`passos_feitos`).
 */
export function useMarcarPasso(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      sessaoId,
      receitaId,
      feito,
    }: {
      sessaoId: number;
      receitaId: number;
      feito: boolean;
    }) => {
      const caminho = `/sessoes/${sessaoId}/passos/${receitaId}/feito`;
      return feito
        ? apiCompras.put<PassoFeitoLinha>(caminho, { id_cliente: novoIdCliente() }, quem)
        : apiCompras.delete<PassoFeitoLinha | null>(caminho, quem);
    },
    onMutate: ({ sessaoId, receitaId, feito }) => {
      passoEmVoo(chaveDoPasso(sessaoId, receitaId), true);
      const anteriores = queryClient.getQueriesData<Roteiro>({ queryKey: CHAVE_ROTEIRO });
      const otimista = feito ? { por: quem, em: new Date().toISOString() } : null;
      queryClient.setQueriesData<Roteiro>({ queryKey: CHAVE_ROTEIRO }, (atual) =>
        atual ? comPassoFeito(atual, sessaoId, receitaId, otimista) : atual,
      );
      return { anteriores };
    },
    onError: (_erro, { sessaoId, receitaId }, contexto) => {
      passoEmVoo(chaveDoPasso(sessaoId, receitaId), false);
      for (const [chave, dados] of contexto?.anteriores ?? []) {
        queryClient.setQueryData(chave, dados);
      }
      // O servidor pode saber de algo que esta cópia não sabe: relê.
      void queryClient.invalidateQueries({ queryKey: CHAVE_ROTEIRO });
    },
    onSuccess: (linha, { sessaoId, receitaId }) => {
      passoEmVoo(chaveDoPasso(sessaoId, receitaId), false);
      queryClient.setQueriesData<Roteiro>({ queryKey: CHAVE_ROTEIRO }, (atual) =>
        atual ? comPassoFeito(atual, sessaoId, receitaId, feitoDaLinha(linha)) : atual,
      );
    },
  });
}
