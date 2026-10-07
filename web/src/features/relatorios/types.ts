/** Espelho dos schemas de relatórios da API (fase 6). Só leitura. */

import type { Dinheiro } from "@/features/transacoes/types";

export interface RelatorioResumo {
  id: number;
  /** Mês de referência, dia 1º (`2026-07-01`). */
  competencia: string;
  /** `mensal` | `anual` | `avulso`. */
  tipo: string;
  /** Escrito por modelo (com IA) ou só dos números (seco). */
  com_ia: boolean;
  /** Arquivo de prompt usado, ex. `relatorio_mensal_v1` (regra 9). */
  prompt_versao: string;
  criado_em: string;
}

export interface RelatorioDetalhe extends RelatorioResumo {
  /**
   * Markdown escrito por modelo: conteúdo NÃO confiável. Renderizado só pelo
   * `MarkdownSeguro`, sem HTML bruto.
   */
  conteudo: string;
  /** Os números que o modelo recebeu. Nulo se não foram salvos. */
  dossie: Dossie | null;
  periodo_inicio: string | null;
  /** Fim exclusivo: `[inicio, fim)`. */
  periodo_fim: string | null;
  execucao: Record<string, unknown>;
}

/**
 * O dossiê como a API de insights o grava (`app/schemas/insights.py`).
 * Tudo opcional: um relatório antigo pode ter sido gravado com um formato
 * anterior, e a tela mostra o que houver em vez de quebrar. Percentuais vêm
 * de 0 a 100.
 */
export interface Dossie {
  competencia?: string;
  gerado_em?: string;
  resumo?: {
    receitas?: Dinheiro;
    despesas?: Dinheiro;
    saldo?: Dinheiro;
    transacoes?: number;
    em_curso?: boolean;
  };
  cobertura?: {
    total?: Dinheiro;
    categorizado?: Dinheiro;
    sem_categoria?: Dinheiro;
    percentual?: string;
    transacoes_sem_categoria?: number;
  };
  gasto_por_categoria?: {
    total?: Dinheiro;
    linhas?: Array<{ categoria: string; total: Dinheiro; participacao: string; transacoes: number }>;
  };
  divisao_pessoas?: {
    total?: Dinheiro;
    linhas?: Array<{ pessoa: string; total: Dinheiro; participacao: string }>;
  };
  comparacao?: {
    competencia_anterior?: string;
    total_atual?: Dinheiro;
    total_anterior?: Dinheiro;
    diferenca?: Dinheiro;
    variacao_pct?: string | null;
    media_janela?: Dinheiro;
    meses_na_media?: number;
  };
  orcamento?: {
    tem_orcamento?: boolean;
    estourados?: number;
    linhas?: Array<{
      categoria: string;
      meta: Dinheiro;
      realizado: Dinheiro;
      percentual: string;
      situacao: string;
    }>;
  };
  atipicas?: {
    linhas?: Array<{
      data: string;
      descricao: string;
      categoria: string;
      valor: Dinheiro;
      mediana_categoria: Dinheiro;
    }>;
  };
  reajustes?: {
    linhas?: Array<{
      descricao: string;
      valor_anterior: Dinheiro;
      valor_atual: Dinheiro;
      variacao_pct: string;
    }>;
  };
}
