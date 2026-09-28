/**
 * Filtros compartilhados entre a tela de transações e a de Analytics.
 *
 * As duas telas mandam exatamente o mesmo conjunto de parâmetros para a API —
 * é o que faz "filtros compartilhados" ser verdade estrutural e não
 * coincidência de implementação.
 */

/** Balde de pessoa: id numérico, ou o gasto conjunto (D-03). */
export type BaldePessoa = number | "conjunto";

export type PeriodoPreset =
  | "mes_atual"
  | "mes_passado"
  | "ultimos_3_meses"
  | "ano_atual"
  | "todo_periodo";

export const PERIODO_LABELS: Record<PeriodoPreset, string> = {
  mes_atual: "Este mês",
  mes_passado: "Mês passado",
  ultimos_3_meses: "Últimos 3 meses",
  ano_atual: "Este ano",
  todo_periodo: "Todo o período",
};

export const PERIODO_ORDEM: PeriodoPreset[] = [
  "mes_atual",
  "mes_passado",
  "ultimos_3_meses",
  "ano_atual",
  "todo_periodo",
];

export type TipoTransacao = "despesa" | "receita" | "transferencia";

export interface Filtros {
  periodo: PeriodoPreset;
  categoriaIds: number[];
  pessoa: BaldePessoa | null;
  formaPagamentoIds: number[];
  tipos: TipoTransacao[];
  local: string;
  valorMin: string;
  valorMax: string;
  texto: string;
}

export const FILTROS_VAZIOS: Filtros = {
  periodo: "todo_periodo",
  categoriaIds: [],
  pessoa: null,
  formaPagamentoIds: [],
  tipos: [],
  local: "",
  valorMin: "",
  valorMax: "",
  texto: "",
};

/** Competência ISO (`AAAA-MM-01`) de uma data. */
function competenciaDe(d: Date): string {
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-01`;
}

/**
 * Converte o preset em intervalo de competência.
 *
 * É aritmética de calendário para montar a URL, não agregação — a soma
 * continua toda no banco (D-14).
 */
export function intervaloDoPeriodo(
  periodo: PeriodoPreset,
  hoje = new Date(),
): { inicio: string | null; fim: string | null } {
  const mesAtual = new Date(hoje.getFullYear(), hoje.getMonth(), 1);

  switch (periodo) {
    case "mes_atual":
      return { inicio: competenciaDe(mesAtual), fim: competenciaDe(mesAtual) };

    case "mes_passado": {
      const anterior = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
      return { inicio: competenciaDe(anterior), fim: competenciaDe(anterior) };
    }

    case "ultimos_3_meses": {
      const inicio = new Date(hoje.getFullYear(), hoje.getMonth() - 2, 1);
      return { inicio: competenciaDe(inicio), fim: competenciaDe(mesAtual) };
    }

    case "ano_atual":
      return {
        inicio: `${hoje.getFullYear()}-01-01`,
        fim: competenciaDe(mesAtual),
      };

    case "todo_periodo":
      return { inicio: null, fim: null };
  }
}

/** Parâmetros de query, no formato exato que a API espera (snake_case). */
export function filtrosParaQuery(filtros: Filtros): Record<string, unknown> {
  const { inicio, fim } = intervaloDoPeriodo(filtros.periodo);

  return {
    competencia_inicio: inicio,
    competencia_fim: fim,
    categoria_ids: filtros.categoriaIds,
    pessoa: filtros.pessoa === null ? null : String(filtros.pessoa),
    forma_pagamento_ids: filtros.formaPagamentoIds,
    tipos: filtros.tipos,
    local: filtros.local || null,
    valor_min: filtros.valorMin || null,
    valor_max: filtros.valorMax || null,
    texto: filtros.texto || null,
  };
}

/** Quantos filtros estão ativos além do período — alimenta o badge "Filtros (3)". */
export function contarFiltrosAtivos(filtros: Filtros): number {
  return (
    filtros.categoriaIds.length +
    (filtros.pessoa !== null ? 1 : 0) +
    filtros.formaPagamentoIds.length +
    filtros.tipos.length +
    (filtros.local ? 1 : 0) +
    (filtros.valorMin || filtros.valorMax ? 1 : 0)
  );
}

export function temFiltroAtivo(filtros: Filtros): boolean {
  return (
    filtros.periodo !== "todo_periodo" || contarFiltrosAtivos(filtros) > 0 || !!filtros.texto
  );
}
