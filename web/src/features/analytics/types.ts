/**
 * Espelho dos schemas de Analytics da API (snake_case, como vem no JSON).
 *
 * Tudo aqui já chega somado, ordenado e com percentual pronto: o front recebe
 * e desenha (D-14). Nenhum componente recalcula nada disto.
 *
 * Dinheiro é string pelo mesmo motivo de `transacoes/types.ts`: `numeric(12,2)`
 * virando number em JS perde centavo. Converter para número só na hora de
 * medir uma barra é seguro — somar não é.
 */

import type { Dinheiro } from "@/features/transacoes/types";

export type { Dinheiro };

/** Competência ISO — sempre o dia 1º do mês de referência (D-02). */
export type Competencia = string;

export interface PontoMensal {
  competencia: Competencia;
  pessoa_a: Dinheiro;
  pessoa_b: Dinheiro;
  conjunto: Dinheiro;
  total: Dinheiro;
  /** Mês corrente: total parcial, recebe realce na tela. */
  em_curso: boolean;
}

export interface EvolucaoMensal {
  pontos: PontoMensal[];
  media_total: Dinheiro;
  /** Nome cadastrado das duas pessoas, na ordem das séries. */
  rotulo_a: string;
  rotulo_b: string;
}

export interface LinhaComposicao {
  categoria_id: number;
  nome: string;
  /** Token de cor da categoria (`cat-3`). */
  cor: string | null;
  valor: Dinheiro;
  percentual: Dinheiro;
  /** `false` numa folha: não há para onde descer. */
  tem_filhos: boolean;
}

export interface ComposicaoCategoria {
  categoria_pai: { categoria_id: number; nome: string } | null;
  linhas: LinhaComposicao[];
  total_nivel: Dinheiro;
}

export interface LinhaPessoa {
  /** Id da pessoa em texto, ou `conjunto`. */
  balde: string;
  nome: string;
  valor: Dinheiro;
  /** Os três somam 100, sem sobreposição (D-03). */
  percentual: Dinheiro;
  valor_anterior: Dinheiro;
}

export interface DivisaoPessoas {
  competencia: Competencia;
  linhas: LinhaPessoa[];
  total: Dinheiro;
}

export type StatusOrcamento = "ok" | "atencao" | "estourado";

export interface LinhaOrcamento {
  categoria_id: number;
  nome: string;
  realizado: Dinheiro;
  meta: Dinheiro;
  percentual: Dinheiro;
  status: StatusOrcamento;
}

export interface ProgressoOrcamento {
  competencia: Competencia;
  linhas: LinhaOrcamento[];
  /** Fração do mês decorrida (0–1), para o marcador de ritmo. */
  fracao_decorrida: Dinheiro;
}

export interface LinhaComparativo {
  chave: string;
  label: string;
  valor: Dinheiro;
  valor_base: Dinheiro | null;
  base_label: string | null;
}

export interface Comparativo {
  linhas: LinhaComparativo[];
}

/** Retorno de `GET /analytics/resumo`. */
export interface AnalyticsResumo {
  evolucao_mensal: EvolucaoMensal;
  composicao_categoria: ComposicaoCategoria;
  divisao_pessoas: DivisaoPessoas;
  orcamento: ProgressoOrcamento;
  comparativo: Comparativo;
}
