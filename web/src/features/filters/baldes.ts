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

const CORES = [
  "var(--color-person-a)",
  "var(--color-person-b)",
] as const;

const CORES_SUAVES = [
  "var(--color-person-a-soft)",
  "var(--color-person-b-soft)",
] as const;

const COR_CONJUNTO = "var(--color-person-c)";
const COR_CONJUNTO_SUAVE = "var(--color-person-c-soft)";

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
  if (balde === null || balde === "conjunto") return "Conjunto";
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
    { balde: "conjunto" as BaldePessoa, nome: "Conjunto", cor: COR_CONJUNTO },
  ];
}

/** Token de cor de categoria (`cat-3`) para a variável CSS correspondente. */
export function corDaCategoria(token: string | null | undefined): string {
  if (!token) return "var(--color-cat-5)";
  return `var(--color-${token})`;
}
