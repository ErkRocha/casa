/** Espelho de `app/schemas/analises.py` (D-24). */

import type { TipoPagamento } from "@/features/cadastros/types";
import type { FaixaOrcamento } from "@/features/inicio/types";
import type { Dinheiro } from "@/features/transacoes/types";

export type Periodo = "mes" | "3m" | "12m";

/** D-27: o que sai da conta (competência) ou a data da compra. */
export type BaseAnalise = "caixa" | "compra";

export interface MesAnalise {
  competencia: string;
  despesas: Dinheiro;
  receitas: Dinheiro;
  /** O mês corrente: valores até hoje. */
  em_curso: boolean;
}

export interface SubcategoriaAnalise {
  categoria_id: number;
  nome: string;
  valor: Dinheiro;
}

export interface CategoriaAnalise {
  /** Nulo = sem categoria. */
  categoria_id: number | null;
  nome: string;
  valor: Dinheiro;
  subcategorias: SubcategoriaAnalise[];
}

export interface MudancaCategoria {
  categoria_id: number;
  nome: string;
  valor: Dinheiro;
  media: Dinheiro;
  /** Inteiro, com sinal: 42, −13. */
  variacao: number;
}

export interface Mudancas {
  referencia: string;
  meses_base: number;
  linhas: MudancaCategoria[];
}

export interface LinhaOrcamentoAnalise {
  categoria_id: number;
  nome: string;
  gasto: Dinheiro;
  meta: Dinheiro;
  percentual: number;
  faixa: FaixaOrcamento;
  /** Largura da barra, até 100. */
  largura: number;
  excesso: Dinheiro | null;
}

export interface Analises {
  periodo: Periodo;
  base: BaseAnalise;
  inicio: string;
  fim: string;
  dia_referencia: number;
  dias_no_mes: number;
  meses: MesAnalise[];
  meses_fechados: number;
  base_categorias: "media_mensal" | "mes";
  media_mensal: Dinheiro | null;
  mes_mais_caro: MesAnalise | null;
  categorias: CategoriaAnalise[];
  mudancas: Mudancas | null;
  orcamento: LinhaOrcamentoAnalise[];
}

export interface FormaNoBanco {
  forma_pagamento_id: number;
  apelido: string;
  tipo: TipoPagamento;
  /** Cartão de crédito; o resto sai direto da conta. */
  cartao: boolean;
  valor: Dinheiro;
  quantidade: number;
  /** Ainda na revisão das importações: fora de `valor` até aprovar. */
  revisao_valor: Dinheiro;
  revisao_quantidade: number;
}

export interface LinhaBanco {
  /** Nulo = lançamento sem forma de pagamento. */
  conta_id: number | null;
  nome: string;
  total: Dinheiro;
  cartao: Dinheiro;
  conta: Dinheiro;
  percentual: Dinheiro;
  formas: FormaNoBanco[];
  revisao_valor: Dinheiro;
  revisao_quantidade: number;
}

/** Despesa do período por banco e forma. Ignora o filtro de forma. */
export interface GastoPorBanco {
  total: Dinheiro;
  cartao: Dinheiro;
  conta: Dinheiro;
  linhas: LinhaBanco[];
  revisao_valor: Dinheiro;
  revisao_quantidade: number;
}
