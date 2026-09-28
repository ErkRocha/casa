/**
 * Formatação pt-BR / BRL. UI é 100% em português, moeda BRL, data DD/MM/AAAA
 * (CLAUDE.md § Convenções).
 *
 * Nenhuma destas funções calcula: elas só apresentam número que já veio
 * pronto. Agregação é do banco (D-14).
 */

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const brlAxis = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 0,
});

const percent = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 0,
});

/** `R$ 1.234,56`. Aceita negativo para saldo. */
export function formatBRL(value: number): string {
  return brl.format(value);
}

/**
 * A API manda dinheiro como string (`"1234.56"`) porque `numeric(12,2)`
 * virando number em JS perde centavo em algum ponto. Aqui a conversão é só
 * para exibir — nada é somado depois disso.
 */
export function formatBRLTexto(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return brl.format(0);
  return brl.format(Number(value));
}

/** Igual acima, mas para os rótulos compactos do gráfico. */
export function toNumero(value: string | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  return Number(value);
}

/** `R$ 1.235` — rótulo de eixo, sem centavos. */
export function formatBRLAxis(value: number): string {
  return `R$ ${brlAxis.format(Math.round(value))}`;
}

/** `1,2k` acima de mil, senão o inteiro. Rótulo em cima da barra. */
export function formatBRLCompact(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1).replace(".", ",")}k`;
  }
  return String(Math.round(value));
}

/** `42%`. */
export function formatPercent(value: number): string {
  return `${percent.format(value)}%`;
}

/**
 * Delta percentual com seta. Para gasto, subir é ruim — daí `tone`.
 * Base zero não vira divisão por zero: devolve `null` e o chamador decide.
 */
export function formatDelta(
  current: number,
  base: number,
): { label: string; tone: "up" | "down" | "flat" } | null {
  if (base === 0) return null;
  const delta = ((current - base) / base) * 100;
  if (Math.abs(delta) < 0.05) return { label: "0,0%", tone: "flat" };
  const arrow = delta > 0 ? "↑" : "↓";
  return {
    label: `${arrow} ${Math.abs(delta).toFixed(1).replace(".", ",")}%`,
    tone: delta > 0 ? "up" : "down",
  };
}

const MONTH_SHORT = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
] as const;

/** `Ago` — mês 1..12. */
export function monthShort(month: number): string {
  return MONTH_SHORT[month - 1] ?? "";
}

/**
 * `Ago/2026` a partir de uma competência ISO (`2026-08-01`).
 * Competência é sempre o dia 1º do mês de referência (D-02).
 */
export function formatCompetencia(competencia: string): string {
  const [year = "", month = ""] = competencia.split("-");
  return `${monthShort(Number(month))}/${year}`;
}

/** `Ago` — só o mês, para o eixo X da evolução mensal. */
export function competenciaMonthLabel(competencia: string): string {
  const [, month = ""] = competencia.split("-");
  return monthShort(Number(month));
}

/** `06/08/2026` a partir de uma data ISO (`2026-08-06`). */
export function formatDate(isoDate: string): string {
  const [year = "", month = "", day = ""] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}
