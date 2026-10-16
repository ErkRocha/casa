/**
 * O recorte da tela de Lançamentos (`LancamentosDesktop`, D-22): um mês, a
 * busca, quem, categoria, pagamento, tipo e o atalho "sem categoria".
 *
 * É da tela, não do contexto compartilhado: as pranchetas mostram Lançamentos
 * por mês, e Análises tem os seletores dela (fase 3 do redesenho).
 */

import type { BaldePessoa, TipoTransacao } from "@/features/filters/types";
import type { QueryValue } from "@/lib/api";

export interface FiltrosLancamentos {
  /** `AAAA-MM-01`. */
  competencia: string;
  texto: string;
  pessoa: BaldePessoa | null;
  categoriaIds: number[];
  formaPagamentoIds: number[];
  tipos: TipoTransacao[];
  semCategoria: boolean;
}

export function filtrosDoMes(competencia: string): FiltrosLancamentos {
  return {
    competencia,
    texto: "",
    pessoa: null,
    categoriaIds: [],
    formaPagamentoIds: [],
    tipos: [],
    semCategoria: false,
  };
}

/** Parâmetros de `/transacoes` e `/transacoes/dias`, como a API espera. */
export function paraQuery(f: FiltrosLancamentos): Record<string, QueryValue> {
  return {
    competencia_inicio: f.competencia,
    competencia_fim: f.competencia,
    texto: f.texto.trim() || null,
    pessoa: f.pessoa === null ? null : String(f.pessoa),
    categoria_ids: f.categoriaIds,
    forma_pagamento_ids: f.formaPagamentoIds,
    tipos: f.tipos,
    sem_categoria: f.semCategoria || null,
  };
}

/** Algum recorte além do mês? Decide o texto da tela vazia. */
export function temRecorte(f: FiltrosLancamentos): boolean {
  return (
    f.texto.trim() !== "" ||
    f.pessoa !== null ||
    f.categoriaIds.length > 0 ||
    f.formaPagamentoIds.length > 0 ||
    f.tipos.length > 0 ||
    f.semCategoria
  );
}

export const ROTULO_TIPO: Record<TipoTransacao, string> = {
  despesa: "Despesas",
  receita: "Receitas",
  transferencia: "Transferências",
};
