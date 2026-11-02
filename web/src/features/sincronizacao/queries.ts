import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EstadoSincronizacao } from "./types";

export const sincronizacaoKeys = {
  todas: ["sincronizacao"] as const,
  estado: ["sincronizacao", "estado"] as const,
};

/** Enquanto a sync do painel roda, o estado é relido neste intervalo. */
const ACOMPANHAR_MS = 2_000;

export function useEstadoSincronizacao() {
  const queryClient = useQueryClient();
  const consulta = useQuery({
    queryKey: sincronizacaoKeys.estado,
    queryFn: () => api.get<EstadoSincronizacao>("/sincronizacao/estado"),
    staleTime: 5 * 60_000,
    refetchInterval: (q) => (q.state.data?.execucao?.situacao === "rodando" ? ACOMPANHAR_MS : false),
  });

  // Quando a execução do painel termina, tudo o que ela pode ter trazido
  // (lançamentos, revisão, histórico, contas) é lido de novo.
  const situacao = consulta.data?.execucao?.situacao;
  const anterior = useRef(situacao);
  useEffect(() => {
    if (anterior.current === "rodando" && situacao !== "rodando") {
      void queryClient.invalidateQueries();
    }
    anterior.current = situacao;
  }, [situacao, queryClient]);

  return consulta;
}

/** "Atualizar agora": dispara a sync em segundo plano; a API volta na hora. */
export function useAtualizarAgora() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<EstadoSincronizacao>("/sincronizacao/atualizar"),
    onSuccess: (estado) => queryClient.setQueryData(sincronizacaoKeys.estado, estado),
  });
}
