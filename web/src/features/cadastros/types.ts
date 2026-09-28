/** Espelho dos schemas de cadastro da API (snake_case, como vem no JSON). */

import type { TipoTransacao } from "@/features/filters/types";

export type TipoPessoa = "individual" | "conjunta";
export type TipoConta = "corrente" | "poupanca" | "carteira" | "investimento" | "cartao";
export type TipoPagamento =
  | "credito"
  | "debito"
  | "pix"
  | "dinheiro"
  | "boleto"
  | "transferencia";

export interface Pessoa {
  id: number;
  nome: string;
  tipo: TipoPessoa;
  ativo: boolean;
}

export interface Conta {
  id: number;
  nome: string;
  tipo: TipoConta;
  titular_id: number | null;
  saldo_inicial: string;
  ativo: boolean;
}

export interface Categoria {
  id: number;
  nome: string;
  tipo: TipoTransacao;
  categoria_pai_id: number | null;
  /** Token de cor (`cat-1`..`cat-9`) — é o que amarra a cor no gráfico. */
  cor: string | null;
  ativo: boolean;
}

export interface CategoriaArvore extends Categoria {
  subcategorias: Categoria[];
}

export interface FormaPagamento {
  id: number;
  apelido: string;
  tipo: TipoPagamento;
  conta_id: number | null;
  titular_id: number | null;
  dia_fechamento: number | null;
  dia_vencimento: number | null;
  ativo: boolean;
}

export const TIPO_PAGAMENTO_LABEL: Record<TipoPagamento, string> = {
  credito: "Crédito",
  debito: "Débito",
  pix: "Pix",
  dinheiro: "Dinheiro",
  boleto: "Boleto",
  transferencia: "Transferência",
};
