/**
 * Ponte entre os tokens CSS e o Recharts.
 *
 * Recharts precisa de uma string de cor para `fill`/`stroke`. Devolvemos
 * `var(--color-*)` em vez do valor resolvido: SVG aceita custom properties, e
 * assim a troca de tema repinta o gráfico sem re-render nem leitura de
 * `getComputedStyle`.
 *
 * As cores de *série* (pessoa, categoria) não moram aqui — elas dependem do
 * cadastro, então vivem em `features/filters/baldes.ts`. Este arquivo é só o
 * cromatismo fixo do gráfico.
 */

/** Cores de status. Reservadas — nunca viram série de gráfico. */
export const STATUS_COLOR = {
  income: "var(--color-income)",
  expense: "var(--color-expense)",
  alert: "var(--color-alert)",
} as const;

/** Tokens de superfície usados dentro do SVG. */
export const CHART_SURFACE = {
  grid: "var(--color-border-faint)",
  axisText: "var(--color-text-tertiary)",
  reference: "var(--color-text-tertiary)",
  /** Vão de 2px entre segmentos empilhados — pintado com a cor do painel. */
  gap: "var(--color-surface-sunken)",
} as const;
