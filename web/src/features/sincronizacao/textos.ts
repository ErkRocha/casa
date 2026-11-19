import { quandoComSemana } from "@/lib/format";

/** "Os bancos não atualizam desde seg, 10 nov às 6h" (sync atrasada). */
export function textoSyncAtrasada(ultimaAtualizacao: string | null): string {
  return ultimaAtualizacao
    ? `Os bancos não atualizam desde ${quandoComSemana(ultimaAtualizacao)}`
    : "Os bancos ainda não foram atualizados";
}
