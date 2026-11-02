/** Espelho de `app/schemas/sincronizacao.py`. */

/** A sync disparada pelo "Atualizar agora", no processo da API. */
export interface ExecucaoSync {
  /** `ocupada`: outra sync (a agendada ou um make sync) estava rodando. */
  situacao: "nunca" | "rodando" | "ok" | "erro" | "ocupada";
  iniciada_em: string | null;
  terminada_em: string | null;
  itens_novos: number;
  promovidos: number;
  na_revisao: number;
  importacao_id: number | null;
  erro: string | null;
}

export interface EstadoSincronizacao {
  ultima_atualizacao: string | null;
  conexoes_ativas: number;
  /** A sync roda sozinha (há agenda)? */
  automatica: boolean;
  /** Quando roda a próxima, se `automatica`. */
  proxima_execucao: string | null;
  /** Dá para disparar pelo painel (há credenciais da Pluggy)? */
  pode_atualizar: boolean;
  /** A última disparada pelo painel; nula se nenhuma desde que a API subiu. */
  execucao: ExecucaoSync | null;
}
