/** Espelho de `app/schemas/configuracoes.py` e do histórico da sincronização. */

import type { TipoConta, TipoPagamento } from "@/features/cadastros/types";

export type SituacaoConta = "sincronizando" | "pausado" | "sem_movimento" | "manual";

export interface ItemContaCartao {
  tipo: "conta" | "cartao";
  conta_id: number;
  /** O cartão é forma de pagamento da conta que paga a fatura. */
  forma_pagamento_id: number | null;
  nome: string;
  tipo_conta: TipoConta | null;
  titular: string | null;
  situacao: SituacaoConta;
  formas: TipoPagamento[];
  cartoes: string[];
  paga_por: string | null;
  cartoes_virtuais: string[];
  ultimo_movimento: string | null;
}

export interface GrupoContas {
  titulo: string;
  pluggy_item_id: string | null;
  desde: string | null;
  situacao: "funcionando" | "parcial" | "pausada" | "manual";
  itens: ItemContaCartao[];
}

export interface ContasECartoes {
  grupos: GrupoContas[];
}

export interface UsoCategorias {
  competencia: string;
  sem_categoria: number;
  categorias: Array<{ categoria_id: number; lancamentos: number }>;
}

export interface CategoriaPluggyUso {
  pluggy_categoria_id: string;
  pluggy_categoria_nome: string;
  transacoes: number;
  mapeamento_id: number | null;
  categoria_id: number | null;
  categoria_nome: string | null;
  ativo: boolean | null;
  /** Família de transferência da Pluggy: nunca vira despesa (D-21). */
  transferencia: boolean;
}

export interface LinhaHistorico {
  importacao_id: number;
  criado_em: string;
  origem: string | null;
  parser_usado: string | null;
  arquivo_nome: string;
  total_itens: number;
  entraram: number;
  revisar: number;
  situacao: "concluida" | "com_pendencias" | "nada_novo" | "desfeita";
  pode_desfazer: boolean;
}
