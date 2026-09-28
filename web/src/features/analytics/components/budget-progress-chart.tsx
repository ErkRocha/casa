import { formatBRLTexto, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ProgressoOrcamento, StatusOrcamento } from "../types";

/**
 * Meta contra realizado por categoria no mês (`vw_orcamento_mes`).
 *
 * Medidor, não gráfico. O marcador vertical é o ritmo esperado: 60% da meta no
 * dia 10 é uma história, no dia 28 é outra — sem ele o percentual sozinho
 * engana no começo do mês.
 *
 * Status nunca é só cor: cada linha estourada ou em atenção leva ícone e texto
 * acessível junto.
 */

const STATUS_META: Record<StatusOrcamento, { icone: string; texto: string }> = {
  estourado: { icone: "✗", texto: "estourado" },
  atencao: { icone: "!", texto: "em atenção" },
  ok: { icone: "", texto: "dentro da meta" },
};

export function BudgetProgressChart({ data }: { data: ProgressoOrcamento }) {
  const { linhas } = data;
  const fracao = toNumero(data.fracao_decorrida);
  const ritmoPct = Math.round(fracao * 100);

  if (linhas.length === 0) {
    return (
      <p className="text-body-sm text-text-tertiary py-8">
        Nenhum orçamento definido para esta competência. Cadastre em /orcamentos.
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      {linhas.map((linha) => {
        const status = STATUS_META[linha.status];
        const estourado = linha.status === "estourado";
        const percentual = toNumero(linha.percentual);

        return (
          <div key={linha.categoria_id} className="flex items-center gap-4 py-2.5">
            <span
              aria-hidden
              className="text-accent text-caption w-6 shrink-0 text-center font-bold"
            >
              {status.icone}
            </span>

            <span className="text-body-sm text-text-primary w-46 shrink-0 truncate font-medium">
              {linha.nome}
            </span>

            <div
              className={cn("bg-surface relative flex-1 rounded-xs", estourado ? "h-4" : "h-3")}
              role="img"
              aria-label={`${linha.nome}: ${formatBRLTexto(linha.realizado)} de ${formatBRLTexto(linha.meta)}, ${Math.round(percentual)}% da meta — ${status.texto}. Ritmo esperado: ${ritmoPct}% do mês.`}
            >
              <div
                className={cn(
                  "h-full rounded-xs",
                  linha.status === "ok" ? "bg-text-secondary" : "bg-accent",
                )}
                style={{ width: `${Math.min(100, percentual)}%` }}
              />
              {/* Ritmo esperado até hoje. */}
              <div
                aria-hidden
                title="Ritmo esperado para o dia de hoje"
                className="bg-text-tertiary absolute -top-1.5 -bottom-1.5 w-px"
                style={{ left: `${fracao * 100}%` }}
              />
            </div>

            <span
              className={cn(
                "tabular text-body-lg w-20 shrink-0 text-right font-bold",
                estourado ? "text-accent" : "text-text-primary",
              )}
            >
              {Math.round(percentual)}%
            </span>

            <span className="text-label-lg text-text-tertiary w-61 shrink-0 text-right tabular-nums">
              {formatBRLTexto(linha.realizado)} / {formatBRLTexto(linha.meta)}
            </span>
          </div>
        );
      })}

      <p className="text-caption text-text-tertiary mt-5">
        A marca vertical é o ritmo esperado até hoje ({ritmoPct}% do mês).
      </p>
    </div>
  );
}
