import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EstadoSincronizacao } from "./types";

export const sincronizacaoKeys = {
  todas: ["sincronizacao"] as const,
  estado: ["sincronizacao", "estado"] as const,
};

export function useEstadoSincronizacao() {
  return useQuery({
    queryKey: sincronizacaoKeys.estado,
    queryFn: () => api.get<EstadoSincronizacao>("/sincronizacao/estado"),
    staleTime: 5 * 60_000,
  });
}
