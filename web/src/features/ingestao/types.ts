/** Espelho dos schemas de ingestão da API (snake_case, como vem no JSON). */

import type { TipoTransacao } from "@/features/filters/types";
import type { Dinheiro } from "@/features/transacoes/types";

export type StatusImportacao =
  | "processando"
  | "aguardando_revisao"
  | "concluida"
  | "erro"
  | "cancelada";

export type StatusItem = "pendente" | "aprovado" | "rejeitado" | "duplicado";

export interface Importacao {
  id: number;
  arquivo_nome: string;
  /** `nubank_fatura` | `nubank_extrato` | `pluggy`. */
  origem: string | null;
  parser_usado: string | null;
  /**
   * `application/pdf` ou `application/json` (sync da Pluggy). Decide se a
   * tela oferece reabrir o PDF.
   */
  arquivo_tipo: string | null;
  periodo_inicio: string | null;
  periodo_fim: string | null;
  status: StatusImportacao;
  total_itens: number;
  itens_aprovados: number;
  /** Total que o próprio documento declara — o gabarito da extração. */
  total_declarado: Dinheiro | null;
  /** Preenchido quando a soma não fechou ou sobrou linha não reconhecida. */
  erro_mensagem: string | null;
  criado_em: string;
}

export interface ItemImportacao {
  id: number;
  importacao_id: number;
  /** A linha exata do PDF. É contra ela que se confere. */
  linha_bruta: string;
  linha_num: number | null;
  data: string | null;
  valor: Dinheiro | null;
  tipo_sugerido: TipoTransacao | null;
  competencia_sugerida: string | null;
  categoria_sugerida_id: number | null;
  local_sugerido_id: number | null;
  pessoa_sugerida_id: number | null;
  forma_pagamento_sugerida_id: number | null;
  confianca: Dinheiro | null;
  /** `parser` | `regra` | `alias` | `llm`. */
  origem_sugestao: string | null;
  status: StatusItem;
  transacao_id: number | null;
  motivo_rejeicao: string | null;
  /**
   * Nota do parser ou da sync para a revisão: possível duplicata vinda da
   * Pluggy, encargos deduzidos da fatura, competência estimada.
   */
  observacao: string | null;
  /** Id da transação na Pluggy; nulo para PDF. */
  id_externo: string | null;
}

export interface ImportacaoDetalhe {
  importacao: Importacao;
  itens: ItemImportacao[];
  /** Quanto entra de despesa se aprovar tudo que está pendente. */
  total_pendente: Dinheiro;
}

export interface ItemAjuste {
  tipo_sugerido?: TipoTransacao | null;
  competencia_sugerida?: string | null;
  categoria_sugerida_id?: number | null;
  local_sugerido_id?: number | null;
  pessoa_sugerida_id?: number | null;
  forma_pagamento_sugerida_id?: number | null;
}

export interface ResultadoAprovacao {
  promovidos: number;
  /** Esbarraram na deduplicação — não é erro, é proteção (D-07). */
  duplicados: number;
  erros: Array<{ item_id: number; erro: string }>;
}

export const STATUS_ITEM_LABEL: Record<StatusItem, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
  duplicado: "Duplicado",
};

export const STATUS_IMPORTACAO_LABEL: Record<StatusImportacao, string> = {
  processando: "Processando",
  aguardando_revisao: "Aguardando revisão",
  concluida: "Concluída",
  erro: "Erro",
  cancelada: "Cancelada",
};

export const ORIGEM_LABEL: Record<string, string> = {
  nubank_fatura: "Fatura Nubank",
  nubank_extrato: "Extrato Nubank",
  pluggy: "Sincronização Pluggy",
};

/** A importação guardou um PDF que dá para reabrir? */
export function ehPdf(importacao: Pick<Importacao, "arquivo_tipo">): boolean {
  return importacao.arquivo_tipo === "application/pdf";
}
