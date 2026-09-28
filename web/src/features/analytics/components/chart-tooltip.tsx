import { formatBRL } from "@/lib/format";

/**
 * Tooltip compartilhada dos gráficos Recharts.
 *
 * Um gráfico HTML é interativo por natureza — a camada de hover é padrão, não
 * enfeite. Sempre com o rótulo textual da série ao lado do marcador, porque a
 * identidade não pode depender só da cor.
 */

export interface TooltipEntry {
  label: string;
  color: string;
  value: number;
}

export function ChartTooltipCard({
  title,
  subtitle,
  entries,
  total,
}: {
  title: string;
  subtitle?: string;
  entries: TooltipEntry[];
  total?: number;
}) {
  return (
    <div className="bg-surface border-border-faint shadow-popover rounded-xl border px-6 py-5">
      <div className="text-body text-text-primary font-semibold">{title}</div>
      {subtitle ? <div className="text-caption text-text-tertiary mt-1">{subtitle}</div> : null}

      <div className="mt-4 flex flex-col gap-2">
        {entries.map((entry) => (
          <div key={entry.label} className="flex items-center gap-4 whitespace-nowrap">
            <span
              aria-hidden
              className="size-4 shrink-0 rounded-xs"
              style={{ background: entry.color }}
            />
            <span className="text-body-sm text-text-secondary flex-1">{entry.label}</span>
            <span className="tabular text-body-sm text-text-primary font-semibold">
              {formatBRL(entry.value)}
            </span>
          </div>
        ))}
      </div>

      {total !== undefined ? (
        <div className="border-border-faint mt-4 flex items-center justify-between gap-6 border-t pt-4">
          <span className="text-caption text-text-tertiary tracking-label uppercase">Total</span>
          <span className="tabular text-body text-text-primary font-bold">{formatBRL(total)}</span>
        </div>
      ) : null}
    </div>
  );
}
