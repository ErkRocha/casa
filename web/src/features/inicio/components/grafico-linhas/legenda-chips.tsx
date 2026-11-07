import { reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Dinheiro } from "../../types";
import { classesDaCor } from "./cores";

export interface ItemLegenda {
  chave: string;
  rotulo: string;
  cor: string;
  /** Total da série; opcional (a legenda do gráfico de faturas pode não ter). */
  total?: Dinheiro;
  ligada: boolean;
}

/**
 * Legenda clicável: um chip por série, com a bolinha da cor, o nome e o total.
 * Cada chip liga/desliga a série (`aria-pressed`). Alvo de 44px de altura. Num
 * contêiner estreito os chips rolam na horizontal dentro da própria faixa
 * (`overflow-x-auto`), nunca na página.
 */
export function LegendaChips({
  itens,
  onAlternar,
  desabilitarUltima = true,
  className,
}: {
  itens: ItemLegenda[];
  onAlternar: (chave: string) => void;
  /** Não deixa desligar a última série ligada. */
  desabilitarUltima?: boolean;
  className?: string;
}) {
  const ligadas = itens.filter((i) => i.ligada).length;
  return (
    <ul
      aria-label="Séries do gráfico"
      className={cn(
        "m-0 flex list-none gap-3 overflow-x-auto p-0 pb-1 md:flex-wrap md:overflow-visible",
        className,
      )}
    >
      {itens.map((item) => {
        const ultima = desabilitarUltima && item.ligada && ligadas <= 1;
        return (
          <li key={item.chave} className="shrink-0">
            <button
              type="button"
              aria-pressed={item.ligada}
              aria-disabled={ultima || undefined}
              title={ultima ? "Mantenha ao menos uma série ligada" : undefined}
              onClick={() => {
                if (!ultima) onAlternar(item.chave);
              }}
              className={cn(
                "text-apoio inline-flex min-h-22 cursor-pointer items-center gap-3 rounded-full px-6 whitespace-nowrap",
                item.ligada
                  ? "bg-superficie-2 text-texto border-contorno border-[1.5px] font-semibold"
                  : "bg-superficie text-texto-2 border-contorno border-[1.5px] border-dashed",
                ultima && "cursor-default",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "inline-block size-5 shrink-0 rounded-full border-[2px]",
                  classesDaCor(item.cor).borda,
                  item.ligada ? classesDaCor(item.cor).fundo : "bg-superficie",
                )}
              />
              <span>{item.rotulo}</span>
              {item.total !== undefined ? (
                <span className={item.ligada ? "text-texto-2" : "text-texto-2 font-normal"}>
                  {reais(item.total, { centavos: false })}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
