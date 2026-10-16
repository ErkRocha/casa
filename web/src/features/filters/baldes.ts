/**
 * Mapa entre os baldes de gasto e as cores de série.
 *
 * O sistema é de um casal: duas pessoas individuais mais o conjunto, três
 * baldes que somam o total exato sem sobreposição (D-03). A ordem de cadastro
 * (id crescente) é o que fixa quem é a série A e quem é a B — igual ao que a
 * API faz em `AnalyticsService._pessoas_do_casal`.
 *
 * A cor segue a entidade, não a posição num ranking: filtrar não repinta
 * ninguém.
 */

import type { Pessoa } from "@/features/cadastros/types";
import type { BaldePessoa } from "./types";

/** D-22: a 1ª pessoa cadastrada é `pessoa-1`, a 2ª `pessoa-2`. */
const CORES = ["var(--color-pessoa-1)", "var(--color-pessoa-2)"] as const;

const CORES_SUAVES = ["var(--color-destaque-fundo)", "var(--color-destaque-fundo)"] as const;

const COR_CONJUNTO = "var(--color-juntos)";
const COR_CONJUNTO_SUAVE = "var(--color-superficie-2)";

/** O balde conjunto na tela (D-22). Na API ele é `conjunto`. */
export const ROTULO_JUNTOS = "Juntos";

function indiceDaPessoa(id: number, pessoas: Pessoa[]): number {
  return pessoas.findIndex((p) => p.id === id);
}

export function corDoBalde(balde: BaldePessoa | null, pessoas: Pessoa[]): string {
  if (balde === null || balde === "conjunto") return COR_CONJUNTO;
  const indice = indiceDaPessoa(balde, pessoas);
  return CORES[indice] ?? COR_CONJUNTO;
}

export function corSuaveDoBalde(balde: BaldePessoa | null, pessoas: Pessoa[]): string {
  if (balde === null || balde === "conjunto") return COR_CONJUNTO_SUAVE;
  const indice = indiceDaPessoa(balde, pessoas);
  return CORES_SUAVES[indice] ?? COR_CONJUNTO_SUAVE;
}

export function rotuloDoBalde(balde: BaldePessoa | null, pessoas: Pessoa[]): string {
  if (balde === null || balde === "conjunto") return ROTULO_JUNTOS;
  return pessoas.find((p) => p.id === balde)?.nome ?? `Pessoa ${balde}`;
}

/** Os três baldes na ordem canônica das séries, para legenda e gráfico. */
export function baldesDoCasal(pessoas: Pessoa[]): Array<{
  balde: BaldePessoa;
  nome: string;
  cor: string;
}> {
  return [
    ...pessoas.slice(0, 2).map((p) => ({
      balde: p.id as BaldePessoa,
      nome: p.nome,
      cor: corDoBalde(p.id, pessoas),
    })),
    { balde: "conjunto" as BaldePessoa, nome: ROTULO_JUNTOS, cor: COR_CONJUNTO },
  ];
}

/** Cor do balde pela chave que a API usa (`"12"` ou `"conjunto"`). */
export function corDaChave(chave: string, pessoas: Pessoa[]): string {
  return corDoBalde(chave === "conjunto" ? "conjunto" : Number(chave), pessoas);
}

/** Token de cor de categoria (`cat-3`) para a variável CSS correspondente. */
export function corDaCategoria(token: string | null | undefined): string {
  if (!token) return "var(--color-cat-1)";
  return `var(--color-${token})`;
}
