/** Escala, eixos e posição dos rótulos dos gráficos de linhas do Início. */

import { dataCurta } from "../../textos";

/** Eixo vertical: passo "redondo" (1, 2, 2,5, 5 × 10^k) com no máximo 4 faixas. */
export function passoDoEixo(maximo: number): number {
  if (maximo <= 0) return 1;
  const base = 10 ** Math.floor(Math.log10(maximo / 4));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (maximo / (m * base) <= 4) return m * base;
  }
  return 10 * base;
}

/** "R$ 500", "R$ 1,5 mil". */
export function rotuloEixo(valor: number): string {
  if (valor < 1000) return `R$ ${valor}`;
  const mil = valor / 1000;
  return `R$ ${Number.isInteger(mil) ? mil : mil.toFixed(1).replace(".", ",")} mil`;
}

/** Valores das guias horizontais (de 0 ao teto) e o teto do eixo. */
export function guiasDoEixo(maximo: number): { guias: number[]; teto: number } {
  const passo = passoDoEixo(maximo);
  const teto = Math.max(Math.ceil(maximo / passo) * passo, passo);
  const guias: number[] = [];
  for (let v = 0; v <= teto + 1e-9; v += passo) guias.push(v);
  return { guias, teto };
}

/**
 * Rótulos do eixo X: "Hoje" (por padrão o último dia) e, para trás, um a cada
 * 7 dias (ou 14, 21… quando 7 dias medem menos que `minimoPx` e as datas se
 * encostariam). Se hoje não é o último dia, os dias à frente também ganham
 * rótulo, no mesmo passo.
 */
export function rotulosDoEixoX(
  dias: string[],
  passoX = Infinity,
  minimoPx = 56,
  indiceHoje = dias.length - 1,
): Array<{ i: number; texto: string }> {
  const ultimo = dias.length - 1;
  const salto = 7 * Math.max(1, Math.ceil(minimoPx / (7 * passoX)));
  const saida: Array<{ i: number; texto: string }> = [];
  for (let i = indiceHoje; i >= 0; i -= salto) {
    const data = dias[i];
    if (data === undefined) continue;
    saida.push({ i, texto: i === indiceHoje ? "Hoje" : dataCurta(data) });
  }
  saida.reverse();
  for (let i = indiceHoje + salto; i <= ultimo; i += salto) {
    const data = dias[i];
    if (data === undefined) continue;
    saida.push({ i, texto: dataCurta(data) });
  }
  return saida;
}

/**
 * Rótulos no fim das linhas sem colisão: ordena por posição, empurra para
 * baixo o que encosta no de cima e, se estourar a base, sobe tudo o que for
 * preciso. `ys` e o resultado seguem a mesma ordem de entrada.
 */
export function distribuirRotulos(
  ys: number[],
  espaco: number,
  topo: number,
  base: number,
): number[] {
  const ordem = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y || a.i - b.i);
  const posicao = ordem.map((o) => Math.max(o.y, topo));
  for (let k = 1; k < posicao.length; k++) {
    posicao[k] = Math.max(posicao[k] ?? 0, (posicao[k - 1] ?? 0) + espaco);
  }
  const ultimo = posicao.length - 1;
  if (ultimo >= 0 && (posicao[ultimo] ?? 0) > base) {
    posicao[ultimo] = base;
    for (let k = ultimo - 1; k >= 0; k--) {
      posicao[k] = Math.min(posicao[k] ?? 0, (posicao[k + 1] ?? 0) - espaco);
    }
  }
  const saida = new Array<number>(ys.length).fill(0);
  ordem.forEach((o, k) => {
    saida[o.i] = posicao[k] ?? o.y;
  });
  return saida;
}

/**
 * Corta o texto com reticências para caber em `max` caracteres. Em "nome ·
 * detalhe" (ex. "Nubank · nov") corta o nome e mantém o detalhe, que é o que
 * distingue duas linhas do mesmo cartão.
 */
export function encurtar(texto: string, max: number): string {
  if (texto.length <= max) return texto;
  const corte = texto.lastIndexOf(" · ");
  if (corte > 0) {
    const detalhe = texto.slice(corte);
    const resto = max - detalhe.length;
    if (resto >= 2) return `${texto.slice(0, resto - 1).trimEnd()}…${detalhe}`;
  }
  return `${texto.slice(0, Math.max(max - 1, 1)).trimEnd()}…`;
}
