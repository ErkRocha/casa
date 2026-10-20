/** Espelho de `app/schemas/revisar.py`. */

import type { TipoPagamento } from "@/features/cadastros/types";
import type { TipoTransacao } from "@/features/filters/types";
import type { Dinheiro } from "@/features/transacoes/types";

export type Motivo =
  | "possivel_duplicata"
  | "encargos"
  | "pagamento_fatura_cartao"
  | "transferencia"
  | "observacao"
  | "sem_categoria"
  | "outros";

export interface MotivoRevisao {
  motivo: Motivo;
  rotulo: string;
  quantidade: number;
}

export interface RevisarResumo {
  total: number;
  motivos: MotivoRevisao[];
}

export interface ItemRevisar {
  id: number;
  importacao_id: number;
  motivo: Motivo;
  status: "pendente" | "aprovado" | "rejeitado" | "duplicado";
  data: string | null;
  valor: Dinheiro | null;
  tipo_sugerido: TipoTransacao | null;
  competencia_sugerida: string | null;
  /** A descrição que a promoção vai gravar. */
  descricao: string;
  descricao_original: string | null;
  observacao: string | null;
  categoria_sugerida_id: number | null;
  categoria_nome: string | null;
  pessoa_sugerida_id: number | null;
  pessoa_nome: string | null;
  forma_pagamento_sugerida_id: number | null;
  forma_pagamento_tipo: TipoPagamento | null;
  forma_pagamento_apelido: string | null;
  /** A conta da forma de pagamento: de onde o item veio. */
  conta_id: number | null;
  conta_nome: string | null;
  transacao_id: number | null;
}

export interface ContaResumo {
  id: number;
  nome: string;
}

export type TipoTransferencia =
  | "pagamento_fatura_conta"
  | "pagamento_fatura_cartao"
  | "mesma_pessoa"
  | "outra";

export interface TransferenciaRevisar {
  item: ItemRevisar;
  tipo: TipoTransferencia;
  direcao: "entrada" | "saida" | null;
  origem: ContaResumo | null;
  destino: ContaResumo | null;
  /** O cartão cuja fatura foi paga ("Nubank Gold •••• 7704"). */
  fatura_de: string | null;
  par_item_id: number | null;
  /** `descartar`: fatura de cartão da própria conta, nada a gravar (D-05). */
  ao_confirmar: "transferencia" | "descartar";
}

export interface GrupoDuplicata {
  data: string;
  valor: Dinheiro;
  descricao: string;
  itens: ItemRevisar[];
  ja_lancado: boolean;
  /** O banco aceita os itens como transações separadas (D-07)? */
  podem_ser_dois: boolean;
}

export interface ConfirmarTransferencia {
  item_id: number;
  conta_origem_id?: number | null;
  conta_destino_id?: number | null;
}

export interface ResultadoRevisao {
  aprovados: number;
  descartados: number;
  pendentes: number;
  erros: Array<{ item_id: number; erro: string }>;
}
