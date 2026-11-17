/**
 * Datas do cardápio. Tudo em texto `AAAA-MM-DD` (o que a API fala) e conta
 * feita em UTC, sem fuso no meio: "hoje" é que depende do fuso, e é sempre o
 * de São Paulo (D-30: a semana passou quando o domingo dela é anterior a hoje).
 */

const FUSO = "America/Sao_Paulo";
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
];
const DIAS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

/** Hoje em São Paulo, `AAAA-MM-DD`. */
export function hojeSP(agora: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: FUSO,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(agora);
}

function emUtc(iso: string): Date {
  const [ano = 0, mes = 1, dia = 1] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(ano, mes - 1, dia));
}

function paraIso(data: Date): string {
  return data.toISOString().slice(0, 10);
}

export function somarDias(iso: string, n: number): string {
  const data = emUtc(iso);
  data.setUTCDate(data.getUTCDate() + n);
  return paraIso(data);
}

/** 0 = domingo ... 6 = sábado. */
export function diaDaSemana(iso: string): number {
  return emUtc(iso).getUTCDay();
}

/** A segunda-feira da semana de uma data. */
export function segundaDe(iso: string): string {
  const d = diaDaSemana(iso);
  return somarDias(iso, d === 0 ? -6 : 1 - d);
}

export function domingoDa(inicio: string): string {
  return somarDias(inicio, 6);
}

/** A semana de `inicio` já passou: o domingo dela é anterior a hoje. */
export function semanaEncerrada(inicio: string, hoje: string = hojeSP()): boolean {
  return domingoDa(inicio) < hoje;
}

export function numeroDoDia(iso: string): number {
  return emUtc(iso).getUTCDate();
}

/** `domingo`, `quarta`: sem caixa alta. */
export function nomeDoDia(iso: string): string {
  return DIAS[diaDaSemana(iso)] ?? "";
}

/** `seg`, `ter`... */
export function diaCurto(iso: string): string {
  return nomeDoDia(iso).slice(0, 3);
}

export function maiuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** `no domingo`, `na quarta`. */
export function noDia(iso: string): string {
  const d = diaDaSemana(iso);
  return `${d === 0 || d === 6 ? "no" : "na"} ${nomeDoDia(iso)}`;
}

/** `17/11/2026`. */
export function dataBR(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

/** `17/11`. */
export function diaEMesBR(iso: string): string {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
}

/** `16 a 22 de novembro`, ou `30 de novembro a 6 de dezembro` na virada do mês. */
export function intervaloDaSemana(inicio: string): string {
  const fim = domingoDa(inicio);
  const a = emUtc(inicio);
  const b = emUtc(fim);
  const mesB = MESES[b.getUTCMonth()];
  if (a.getUTCMonth() === b.getUTCMonth()) {
    return `${a.getUTCDate()} a ${b.getUTCDate()} de ${mesB}`;
  }
  return `${a.getUTCDate()} de ${MESES[a.getUTCMonth()]} a ${b.getUTCDate()} de ${mesB}`;
}

/** `Terça, 17/11`. */
export function diaCompleto(iso: string): string {
  return `${maiuscula(nomeDoDia(iso))}, ${diaEMesBR(iso)}`;
}

/** Os 7 dias da semana que começa em `inicio`. */
export function diasDaSemana(inicio: string): string[] {
  return Array.from({ length: 7 }, (_, i) => somarDias(inicio, i));
}
