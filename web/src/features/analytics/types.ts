/** Espelho de `app/schemas/analises.py` (D-22). */

import type { FaixaOrcamento } from "@/features/inicio/types";
import type { Dinheiro } from "@/features/transacoes/types";

export type Periodo = "mes" | "3m" | "12m";

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
