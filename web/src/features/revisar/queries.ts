import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { RevisarResumo } from "./types";

export const revisarKeys = {
  todas: ["revisar"] as const,
  resumo: ["revisar", "resumo"] as const,
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
