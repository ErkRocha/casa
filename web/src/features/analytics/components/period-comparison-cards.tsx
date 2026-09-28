import { formatBRLTexto, formatDelta, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Comparativo } from "../types";

/**
 * Comparação com períodos anteriores. Três números, nenhum eixo: quando a
 * resposta é uma manchete, a forma certa é placar, não gráfico.
 *
 * Em gasto, subir é ruim — daí `expense` na alta e `income` na queda.
 */
export function PeriodComparisonCards({ data }: { data: Comparativo }) {
  return (
    <dl className="flex flex-col">
      {data.linhas.map((linha) => {
        const delta =
          linha.valor_base !== null
            ? formatDelta(toNumero(linha.valor), toNumero(linha.valor_base))
            : null;

        return (
          <div key={linha.chave} className="border-border-faint border-t py-6 first:border-t-0">
            <dt className="text-caption text-text-tertiary tracking-label uppercase">
              {linha.label}
            </dt>
            <dd className="tabular text-display-sm text-text-primary mt-2 font-bold">
              {formatBRLTexto(linha.valor)}
            </dd>
            {delta && linha.base_label ? (
              <dd
                className={cn(
                  "text-caption-lg mt-1 font-semibold",
                  delta.tone === "up" && "text-expense",
                  delta.tone === "down" && "text-income",
                  delta.tone === "flat" && "text-text-tertiary",
                )}
              >
                {delta.label} {linha.base_label}
              </dd>
            ) : (
              <dd className="text-caption-lg text-text-tertiary mt-1">referência</dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}
