/**
 * Formatação pt-BR / BRL. UI é 100% em português, moeda BRL, data DD/MM/AAAA
 * (CLAUDE.md § Convenções).
 *
 * Nenhuma destas funções calcula: elas só apresentam número que já veio
 * pronto. Agregação é do banco (D-14).
 *
 * **Dinheiro é formatado como texto** (D-22): a API manda `numeric(12,2)`
 * como string (`"1234.56"`), e as funções `reais*` trabalham nos dígitos,
 * sem passar por `Number`. Um `float` no meio já seria o tipo de erro que a
 * regra 1 existe para impedir. `toNumero` continua existindo, só para a
 * geometria de gráfico (altura de barra, posição de ponto).
 */

/** Sinal de menos tipográfico, como nas pranchetas ("− R$ 186,40"). */
export const MENOS = "−";

type Valor = string | null | undefined;

interface Partes {
  negativo: boolean;
  inteiro: string;
  fracao: string;
}

function partes(valor: Valor): Partes {
  const texto = (valor ?? "").trim() || "0";
  const negativo = texto.startsWith("-");
  const [inteiroBruto = "0", fracao = ""] = texto.replace(/^[-+]/, "").split(".");
  const inteiro = inteiroBruto.replace(/^0+(?=\d)/, "") || "0";
  return { negativo, inteiro, fracao: fracao.replace(/\D/g, "") };
}

/** Soma 1 a um número escrito em dígitos decimais ("199" -> "200"). */
function incrementar(digitos: string): string {
  const lista = digitos.split("");
  for (let i = lista.length - 1; i >= 0; i -= 1) {
    if (lista[i] !== "9") {
      lista[i] = String(Number(lista[i]) + 1);
      return lista.join("");
    }
    lista[i] = "0";
  }
  return `1${lista.join("")}`;
}

/** Arredonda meio para cima, nos dígitos: `("12", "345", 2)` -> `("12", "35")`. */
function arredondar(inteiro: string, fracao: string, casas: number): [string, string] {
  if (fracao.length <= casas) return [inteiro, fracao.padEnd(casas, "0")];
  const mantida = fracao.slice(0, casas);
  if ((fracao[casas] ?? "0") < "5") return [inteiro, mantida];
  const junto = incrementar(`${inteiro}${mantida}`);
  const corte = junto.length - casas;
  return [junto.slice(0, corte) || "0", junto.slice(corte)];
}

function agrupar(inteiro: string): string {
  return inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function ehZero(inteiro: string, fracao: string): boolean {
  return /^0*$/.test(inteiro) && /^0*$/.test(fracao);
}

/**
 * `R$ 1.234,56` (ou `R$ 1.235` com `centavos: false`), com `−` à frente se
 * negativo.
 */
export function reais(valor: Valor, opcoes: { centavos?: boolean } = {}): string {
  const { negativo, inteiro, fracao } = partes(valor);
  const casas = opcoes.centavos === false ? 0 : 2;
  const [int, frac] = arredondar(inteiro, fracao, casas);
  const corpo = casas ? `R$ ${agrupar(int)},${frac}` : `R$ ${agrupar(int)}`;
  return negativo && !ehZero(int, frac) ? `${MENOS}${corpo}` : corpo;
}

/** O valor sem sinal, para quando o sinal vai em outro lugar. */
export function reaisAbs(valor: Valor, opcoes: { centavos?: boolean } = {}): string {
  return reais((valor ?? "0").replace(/^-/, ""), opcoes);
}

/** Um decimal em texto arredondado para inteiro, nos dígitos: `"90.91"` -> `"91"`. */
export function inteiro(valor: Valor): string {
  const { negativo, inteiro: int, fracao } = partes(valor);
  const [arredondado] = arredondar(int, fracao, 0);
  return negativo && arredondado !== "0" ? `${MENOS}${arredondado}` : arredondado;
}

/** `-1`, `0` ou `1`, lido do texto. */
export function sinal(valor: Valor): -1 | 0 | 1 {
  const { negativo, inteiro, fracao } = partes(valor);
  if (ehZero(inteiro, fracao)) return 0;
  return negativo ? -1 : 1;
}

/**
 * Valor de um lançamento como nas pranchetas: despesa `− R$ 186,40`, receita
 * `+ R$ 320,00`, transferência sem sinal (não é gasto nem ganho, D-05).
 */
export function reaisDoLancamento(valor: Valor, tipo: string | null | undefined): string {
  const corpo = reaisAbs(valor);
  if (tipo === "despesa") return `${MENOS} ${corpo}`;
  if (tipo === "receita") return `+ ${corpo}`;
  return corpo;
}

/**
 * O valor que a pessoa digitou, como a API espera (`"1234.56"`), ou nulo.
 *
 * Aceita "186,40", "1.186,40", "R$ 1.186,40" e "186.40". Com vírgula, o
 * ponto é milhar; sem vírgula, um ponto com uma ou duas casas depois é
 * decimal. Tudo em texto: o número nunca passa por `float` (regra 1).
 */
export function valorDigitado(texto: string): string | null {
  const limpo = texto.trim().replace(/^R\$/, "").replace(/\s/g, "");
  let inteiro: string;
  let fracao = "";
  if (/^(\d{1,3}(\.\d{3})*|\d{1,10}),\d{1,2}$/.test(limpo)) {
    [inteiro = "", fracao = ""] = limpo.replace(/\./g, "").split(",");
  } else if (/^\d{1,10}\.\d{1,2}$/.test(limpo)) {
    [inteiro = "", fracao = ""] = limpo.split(".");
  } else if (/^(\d{1,3}(\.\d{3})+|\d{1,10})$/.test(limpo)) {
    inteiro = limpo.replace(/\./g, "");
  } else {
    return null;
  }
  return `${inteiro.replace(/^0+(?=\d)/, "")}.${fracao.padEnd(2, "0")}`;
}

// --------------------------------------------------------------------------
// Datas
// --------------------------------------------------------------------------

const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

const DIAS_SEMANA = [
  "Domingo",
  "Segunda",
  "Terça",
  "Quarta",
  "Quinta",
  "Sexta",
  "Sábado",
] as const;

function maiuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function lerData(iso: string): { ano: number; mes: number; dia: number } {
  const [ano = "0", mes = "1", dia = "1"] = iso.slice(0, 10).split("-");
  return { ano: Number(ano), mes: Number(mes), dia: Number(dia) };
}

/** `outubro` — mês 1..12. */
export function nomeDoMes(mes: number): string {
  return MESES[mes - 1] ?? "";
}

/** `Outubro de 2026` a partir de `2026-10-01`. */
export function mesPorExtenso(competencia: string): string {
  const { ano, mes } = lerData(competencia);
  return `${maiuscula(nomeDoMes(mes))} de ${ano}`;
}

/** `Out 2026`, para o seletor de mês do celular. */
export function mesCurto(competencia: string): string {
  const { ano, mes } = lerData(competencia);
  return `${maiuscula(nomeDoMes(mes).slice(0, 3))} ${ano}`;
}

/** `16 out`. */
export function diaEMes(iso: string): string {
  const { mes, dia } = lerData(iso);
  return `${dia} ${nomeDoMes(mes).slice(0, 3)}`;
}

/** `16 de outubro`. */
export function diaDeMes(iso: string): string {
  const { mes, dia } = lerData(iso);
  return `${dia} de ${nomeDoMes(mes)}`;
}

/** `Quinta, 16 de outubro`. */
export function diaDaSemanaEMes(iso: string): string {
  const { ano, mes, dia } = lerData(iso);
  const semana = DIAS_SEMANA[new Date(Date.UTC(ano, mes - 1, dia)).getUTCDay()];
  return `${semana}, ${diaDeMes(iso)}`;
}

/** Competência (dia 1º) do mês de uma data local. */
export function competenciaDe(data: Date): string {
  const mes = String(data.getMonth() + 1).padStart(2, "0");
  return `${data.getFullYear()}-${mes}-01`;
}

/** A competência `n` meses adiante (ou atrás, com `n` negativo). */
export function somarMeses(competencia: string, n: number): string {
  const { ano, mes } = lerData(competencia);
  const indice = ano * 12 + (mes - 1) + n;
  const novoMes = String((indice % 12) + 1).padStart(2, "0");
  return `${Math.floor(indice / 12)}-${novoMes}-01`;
}

/** `6h` ou `18h30`. */
function hora(momento: Date): string {
  const minutos = momento.getMinutes();
  return minutos ? `${momento.getHours()}h${String(minutos).padStart(2, "0")}` : `${momento.getHours()}h`;
}

/**
 * `hoje às 6h`, `ontem às 18h30`, `14 out às 6h`. Para "Bancos atualizados
 * ..." e o histórico da sincronização.
 */
export function quandoRelativo(iso: string, agora: Date = new Date()): string {
  const momento = new Date(iso);
  const dia = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diferenca = Math.round((dia(agora) - dia(momento)) / 86_400_000);
  if (diferenca === 0) return `hoje às ${hora(momento)}`;
  if (diferenca === 1) return `ontem às ${hora(momento)}`;
  const isoLocal = `${momento.getFullYear()}-${momento.getMonth() + 1}-${momento.getDate()}`;
  return `${diaEMes(isoLocal)} às ${hora(momento)}`;
}

// --------------------------------------------------------------------------
// Geometria e as funções que a tela antiga de importações ainda usa
// (sai na fase de configurações do redesenho).
// --------------------------------------------------------------------------

/** Número para geometria de gráfico (altura de barra, posição de ponto). Nada é somado depois disso. */
export function toNumero(value: Valor): number {
  if (value === null || value === undefined || value === "") return 0;
  return Number(value);
}

/** `R$ 1.234,56` a partir do texto da API, sem passar por float. */
export function formatBRLTexto(value: Valor): string {
  return reais(value);
}

/** `06/08/2026` a partir de uma data ISO (`2026-08-06`). */
export function formatDate(isoDate: string): string {
  const [year = "", month = "", day = ""] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}
