/** Espelho de `app/schemas/sincronizacao.py`. */

export interface EstadoSincronizacao {
  ultima_atualizacao: string | null;
  conexoes_ativas: number;
  /** A sync roda sozinha? Hoje não: o agendamento ainda não existe. */
  automatica: boolean;
}
