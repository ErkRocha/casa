/**
 * Tipos de filtro que as telas dividem.
 *
 * Cada tela do redesenho tem o próprio recorte (D-24): Lançamentos por mês,
 * Análises por período e pessoa. O que é comum fica aqui.
 */

/** Balde de pessoa: id numérico, ou o gasto conjunto (D-03). */
export type BaldePessoa = number | "conjunto";

/** `estorno` abate o gasto (D-34): usa categoria de despesa e nunca é receita. */
export type TipoTransacao = "despesa" | "receita" | "transferencia" | "estorno";
