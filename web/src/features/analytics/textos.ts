import { nomeDoMes, toNumero } from "@/lib/format";

/** Textos e escala dos gráficos de Análises, fora dos componentes (D-22). */

function mesDe(competencia: string): number {
  return Number(competencia.slice(5, 7));
}

/** `out`. */
export function mesAbreviado(competencia: string): string {
  return nomeDoMes(mesDe(competencia)).slice(0, 3);
}

/** `outubro`. */
export function mesDoAno(competencia: string): string {
  return nomeDoMes(mesDe(competencia));
}

/**
 * O topo do eixo: o menor valor "redondo" (1, 2, 2,5, 4, 5 ou 8 vezes uma
 * potência de 10) que cabe o maior valor. Só geometria: a altura das barras
 * sai da proporção, o valor mostrado continua o texto da API.
 */
export function topoDaEscala(valores: string[]): number {
  const maior = Math.max(0, ...valores.map(toNumero));
  if (maior <= 0) return 1;
  const potencia = 10 ** Math.floor(Math.log10(maior));
  const passo = [1, 2, 2.5, 4, 5, 8, 10].find((m) => m * potencia >= maior) ?? 10;
  return passo * potencia;
}

/** "R$ 8 mil", "R$ 750", para o eixo. */
export function rotuloDoEixo(valor: number): string {
  if (valor === 0) return "0";
  if (valor >= 1000) {
    return `R$ ${(valor / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  }
  return `R$ ${valor.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

/** Altura em px de um valor na escala. */
export function altura(valor: string, topo: number, total: number): number {
  return Math.round((Math.max(0, toNumero(valor)) / topo) * total);
}
