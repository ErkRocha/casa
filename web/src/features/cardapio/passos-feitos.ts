import type { QueryClient } from "@tanstack/react-query";

import type { PassoFeitoLinha, Roteiro } from "./types";

/**
 * A caixa de "feito" de cada passo do roteiro (D-30). O roteiro é calculado e
 * vem inteiro da API; o que muda sozinho é o `feito` de cada passo, e quem o
 * traz ao outro celular é o mesmo polling de `/mudancas` da lista
 * (`useSincronizacaoCompras`), na chave `passos_feitos`.
 */

/** Prefixo das consultas do roteiro: `["cardapio", "roteiro", semanaId]`. */
export const CHAVE_ROTEIRO = ["cardapio", "roteiro"] as const;

/**
 * Passos com escrita otimista em curso (`sessao:receita`). O polling não os
 * sobrescreve: a resposta ainda não chegou e a cópia do servidor viria velha.
 */
const emVoo = new Set<string>();

export function chaveDoPasso(sessaoId: number, receitaId: number): string {
  return `${sessaoId}:${receitaId}`;
}

export function passoEmVoo(chave: string, estado: boolean): void {
  if (estado) emVoo.add(chave);
  else emVoo.delete(chave);
}

export type Feito = { por: string; em: string } | null;

/** O roteiro com o `feito` de um passo trocado. */
export function comPassoFeito(
  roteiro: Roteiro,
  sessaoId: number,
  receitaId: number,
  feito: Feito,
): Roteiro {
  return {
    ...roteiro,
    sessoes: roteiro.sessoes.map((s) =>
      s.sessao_id !== sessaoId
        ? s
        : {
            ...s,
            passos: s.passos.map((p) => (p.receita.id === receitaId ? { ...p, feito } : p)),
          },
    ),
  };
}

/** Uma linha de `passos_feitos` como o `feito` do passo: apagada é desfeita. */
export function feitoDaLinha(linha: PassoFeitoLinha | null): Feito {
  return linha && !linha.deleted_em ? { por: linha.feito_por, em: linha.feito_em } : null;
}

/** Aplica o que o `/mudancas` trouxe nas cópias locais do roteiro. */
export function aplicarPassosFeitos(queryClient: QueryClient, linhas: PassoFeitoLinha[]): void {
  for (const linha of linhas) {
    if (emVoo.has(chaveDoPasso(linha.sessao_id, linha.receita_id))) continue;
    queryClient.setQueriesData<Roteiro>({ queryKey: CHAVE_ROTEIRO }, (atual) =>
      atual ? comPassoFeito(atual, linha.sessao_id, linha.receita_id, feitoDaLinha(linha)) : atual,
    );
  }
}
