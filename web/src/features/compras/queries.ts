import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiCompras, buildQuery } from "@/lib/api";
import { novoIdCliente } from "./id-cliente";
import type {
  EstadoDespensa,
  Item,
  ItemResposta,
  Lista,
  LinhaDespensa,
  Mudancas,
  Produto,
  RespostaDespensa,
  Secao,
} from "./types";

export const comprasKeys = {
  todas: ["compras"] as const,
  lista: ["compras", "lista"] as const,
  despensa: (estado: EstadoDespensa | null) => ["compras", "despensa", estado ?? "todos"] as const,
  produtos: (busca: string) => ["compras", "produtos", busca] as const,
  secoes: ["compras", "secoes"] as const,
};

/** De quanto em quanto tempo a tela pergunta o que mudou (api.md). */
const POLLING_MS = 3_000;

/**
 * Itens com escrita otimista em curso. O polling não os sobrescreve: a
 * resposta do servidor ainda não chegou, e a cópia dele viria velha.
 */
const emVoo = new Set<number>();

/** A mesma ordem do `GET /lista`: pendentes primeiro, pelo percurso das seções. */
function ordenar(itens: Item[]): Item[] {
  return [...itens].sort(
    (a, b) =>
      (a.situacao === b.situacao ? 0 : a.situacao === "pendente" ? -1 : 1) ||
      a.secao_ordem - b.secao_ordem ||
      a.produto_nome.localeCompare(b.produto_nome, "pt-BR"),
  );
}

/** Troca, acrescenta ou tira (apagados) itens na cópia local da lista. */
function aplicar(lista: Lista, novos: Item[], cursor?: string): Lista {
  const porId = new Map(lista.itens.map((i) => [i.id, i]));
  for (const novo of novos) {
    if (emVoo.has(novo.id)) continue;
    if (novo.deleted_em) porId.delete(novo.id);
    else porId.set(novo.id, novo);
  }
  return { ...lista, cursor: cursor ?? lista.cursor, itens: ordenar([...porId.values()]) };
}

export function useLista() {
  return useQuery({
    queryKey: comprasKeys.lista,
    queryFn: () => apiCompras.get<Lista>("/lista"),
    // Quem mantém a lista em dia é o polling de /mudancas.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export type EstadoConexao = "ok" | "falha";

/**
 * Polling de `GET /mudancas?desde=` a cada 3 s, só com a tela visível
 * (api.md, "Polling com desde"). Aba oculta: para. Volta: pergunta na hora
 * o que mudou desde o último cursor. Itens mudados entram direto na lista;
 * mudança na despensa, nos produtos ou nas seções relê as telas de compras.
 */
export function useSincronizacaoCompras(): EstadoConexao {
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<EstadoConexao>("ok");

  useEffect(() => {
    let parado = false;
    let rodando = false;
    let relogio: number | undefined;

    async function perguntar() {
      if (rodando || parado || document.visibilityState !== "visible") return;
      const lista = queryClient.getQueryData<Lista>(comprasKeys.lista);
      if (!lista) return;
      rodando = true;
      try {
        const m = await apiCompras.get<Mudancas>(`/mudancas${buildQuery({ desde: lista.cursor })}`);
        if (parado) return;
        if (m.recarregar) {
          await queryClient.invalidateQueries({ queryKey: comprasKeys.todas });
        } else {
          queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
            atual ? aplicar(atual, m.itens, m.cursor) : atual,
          );
          if (m.despensa.length > 0 || m.produtos.length > 0 || m.secoes.length > 0) {
            void queryClient.invalidateQueries({ queryKey: comprasKeys.todas });
          }
        }
        setEstado("ok");
      } catch {
        if (!parado) setEstado("falha");
      } finally {
        rodando = false;
      }
    }

    function aoMudarVisibilidade() {
      window.clearInterval(relogio);
      if (document.visibilityState === "visible") {
        void perguntar();
        relogio = window.setInterval(() => void perguntar(), POLLING_MS);
      }
    }

    aoMudarVisibilidade();
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      parado = true;
      window.clearInterval(relogio);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
  }, [queryClient]);

  return estado;
}

// --- escritas na lista ---------------------------------------------------------

export interface NovoItem {
  produto_id?: number;
  produto_nome?: string;
  quantidade?: string | null;
  unidade?: string | null;
  observacao?: string | null;
}

export function useAdicionarItem(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (novo: NovoItem & { id_cliente?: string }) =>
      apiCompras.post<ItemResposta>(
        "/lista/itens",
        { ...novo, id_cliente: novo.id_cliente ?? novoIdCliente() },
        quem,
      ),
    onSuccess: (item) => {
      queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
        atual
          ? {
              ...aplicar(atual, [item]),
              sugestoes: atual.sugestoes.filter((s) => s.produto_id !== item.produto_id),
            }
          : atual,
      );
    },
  });
}

export function useAtualizarItem(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...campos }: { id: number } & Omit<NovoItem, "produto_id" | "produto_nome">) =>
      apiCompras.patch<Item>(`/lista/itens/${id}`, campos, quem),
    onSuccess: (item) => {
      queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
        atual ? aplicar(atual, [item]) : atual,
      );
    },
  });
}

/**
 * Marcar e desmarcar comprado, otimista (D-25): a caixa muda no toque. Se a
 * API recusar, o item volta sozinho ao que era e a tela diz por quê.
 */
export function useMarcarComprado(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ item, comprado }: { item: Item; comprado: boolean }) =>
      apiCompras.post<Item>(`/lista/itens/${item.id}/${comprado ? "comprar" : "desfazer"}`, {}, quem),
    onMutate: ({ item, comprado }) => {
      emVoo.add(item.id);
      const otimista: Item = comprado
        ? { ...item, situacao: "comprado", comprado_por: quem, comprado_em: new Date().toISOString() }
        : { ...item, situacao: "pendente", comprado_por: null, comprado_em: null };
      queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
        atual ? { ...atual, itens: ordenar(atual.itens.map((i) => (i.id === item.id ? otimista : i))) } : atual,
      );
      return { anterior: item };
    },
    onError: (_erro, _vars, contexto) => {
      if (!contexto) return;
      emVoo.delete(contexto.anterior.id);
      queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
        atual ? aplicar(atual, [contexto.anterior]) : atual,
      );
      // O servidor pode saber de algo que esta cópia não sabe (o outro
      // celular tirou o item da lista): relê.
      void queryClient.invalidateQueries({ queryKey: comprasKeys.lista });
    },
    onSuccess: (item) => {
      emVoo.delete(item.id);
      queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
        atual ? aplicar(atual, [item]) : atual,
      );
      // Comprar põe a despensa em "tem"; desfazer volta para "acabou".
      void queryClient.invalidateQueries({ queryKey: ["compras", "despensa"] });
    },
  });
}

// --- produtos, seções e despensa ------------------------------------------------

export function useBuscaProdutos(busca: string) {
  const termo = busca.trim();
  return useQuery({
    queryKey: comprasKeys.produtos(termo),
    queryFn: () => apiCompras.get<Produto[]>(`/produtos${buildQuery({ busca: termo, limite: 6 })}`),
    enabled: termo.length > 0,
    staleTime: 30_000,
    placeholderData: (anterior) => anterior,
  });
}

/** Todos os produtos, para a despensa mostrar os que ainda não são acompanhados. */
export function useProdutos() {
  return useQuery({
    queryKey: comprasKeys.produtos(""),
    queryFn: () => apiCompras.get<Produto[]>(`/produtos${buildQuery({ limite: 200 })}`),
    staleTime: 60_000,
  });
}

export function useSecoes() {
  return useQuery({
    queryKey: comprasKeys.secoes,
    queryFn: () => apiCompras.get<Secao[]>("/secoes"),
    staleTime: 5 * 60_000,
  });
}

export function useDespensa(estado: EstadoDespensa | null) {
  return useQuery({
    queryKey: comprasKeys.despensa(estado),
    queryFn: () => apiCompras.get<LinhaDespensa[]>(`/despensa${buildQuery({ estado })}`),
    staleTime: 30_000,
  });
}

export function useDefinirDespensa(quem: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ produtoId, estado }: { produtoId: number; estado: EstadoDespensa }) =>
      apiCompras.put<RespostaDespensa>(`/despensa/${produtoId}`, { estado }, quem),
    onSuccess: (resposta) => {
      if (resposta.item_criado) {
        const criado = resposta.item_criado;
        queryClient.setQueryData<Lista>(comprasKeys.lista, (atual) =>
          atual ? aplicar(atual, [criado]) : atual,
        );
      }
      // As sugestões da lista e as contagens das abas mudam.
      void queryClient.invalidateQueries({ queryKey: comprasKeys.todas });
    },
  });
}
