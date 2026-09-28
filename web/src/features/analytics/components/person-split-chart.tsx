import { PersonDot } from "@/components/layout/person-legend";
import { usePessoas } from "@/features/cadastros/queries";
import { corDoBalde } from "@/features/filters/baldes";
import { formatBRLTexto, formatCompetencia, formatDelta, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DivisaoPessoas } from "../types";

/**
 * Quanto cada balde gastou no mês: uma barra 100% empilhada e três placares.
 *
 * Os três baldes somam exatamente o total, sem sobreposição — é a consequência
 * de `pessoa_id` nullable em vez de N:N (D-03). Barra de proporção única é
 * medidor, não plot: HTML dá o vão de 2px entre segmentos de graça e mantém o
 * número selecionável.
 *
 * Delta com sinal invertido de propósito: em gasto, subir é ruim.
 */
export function PersonSplitChart({ data }: { data: DivisaoPessoas }) {
  const { data: pessoas = [] } = usePessoas();
  const { linhas, competencia } = data;
  const total = toNumero(data.total);

  if (total === 0) {
    return (
      <p className="text-body-sm text-text-tertiary py-8">
        Sem gasto lançado em {formatCompetencia(competencia)}.
      </p>
    );
  }

  const corDe = (balde: string) =>
    corDoBalde(balde === "conjunto" ? "conjunto" : Number(balde), pessoas);

  return (
    <div className="flex flex-1 flex-col">
      {/* O vão de 2px é o `gap` sobre a superfície do painel. */}
      <div
        className="bg-surface-sunken mb-10 flex h-11 gap-1 overflow-hidden rounded-xs"
        role="img"
        aria-label={linhas
          .map((l) => `${l.nome}: ${Math.round(toNumero(l.percentual))}%`)
          .join(", ")}
      >
        {linhas.map((linha) => {
          const percentual = toNumero(linha.percentual);
          return (
            <div
              key={linha.balde}
              title={`${linha.nome} — ${formatBRLTexto(linha.valor)} (${percentual.toFixed(1)}%)`}
              className="flex items-center justify-center"
              style={{ width: `${percentual}%`, background: corDe(linha.balde) }}
            >
              {/* Rótulo direto só onde cabe; abaixo disso o placar resolve. */}
              {percentual >= 8 ? (
                <span className="text-on-color text-caption font-bold">
                  {Math.round(percentual)}%
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      <dl className="border-border-faint mt-auto flex gap-3 border-t pt-8">
        {linhas.map((linha) => {
          const delta = formatDelta(toNumero(linha.valor), toNumero(linha.valor_anterior));
          return (
            <div key={linha.balde} className="flex flex-1 flex-col gap-2 text-center">
              <dt className="text-label text-text-secondary tracking-label flex items-center justify-center gap-2 font-semibold whitespace-nowrap uppercase">
                <PersonDot color={corDe(linha.balde)} />
                {linha.nome}
              </dt>
              <dd className="tabular text-display text-text-primary font-bold">
                {formatBRLTexto(linha.valor)}
              </dd>
              <dd
                className={cn(
                  "text-caption font-semibold",
                  delta === null && "text-text-tertiary",
                  delta?.tone === "up" && "text-expense",
                  delta?.tone === "down" && "text-income",
                  delta?.tone === "flat" && "text-text-tertiary",
                )}
              >
                {delta ? `${delta.label} vs. mês ant.` : "sem base anterior"}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
