import { usePessoas } from "@/features/cadastros/queries";
import { baldesDoCasal } from "@/features/filters/baldes";
import { cn } from "@/lib/utils";

/**
 * Ponto colorido de uma série de pessoa. 8px, redondo — `dotStyle` do
 * protótipo. Sempre acompanhado de texto: identidade nunca é só cor.
 */
export function PersonDot({ color, className }: { color: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-4 shrink-0 rounded-full", className)}
      style={{ background: color }}
    />
  );
}

/**
 * Legenda dos três baldes de gasto (D-03). Presente em toda tela que pinta
 * série por pessoa — com 3 séries a legenda é obrigatória.
 *
 * Os nomes vêm do cadastro, não de constante: quem renomeia "Pessoa A" para
 * "Ana" no painel vê "Ana" no gráfico.
 */
export function PersonLegend({
  orientation = "horizontal",
  className,
}: {
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  const { data: pessoas = [] } = usePessoas();
  const isVertical = orientation === "vertical";

  return (
    <div
      className={cn(
        "text-body-sm flex text-text-secondary",
        isVertical ? "flex-col" : "flex-wrap items-center gap-9",
        className,
      )}
    >
      {baldesDoCasal(pessoas).map((b) => (
        <span
          key={String(b.balde)}
          className={cn(
            "flex shrink-0 items-center gap-4 whitespace-nowrap",
            isVertical && "py-2",
          )}
        >
          <PersonDot color={b.cor} />
          {b.nome}
        </span>
      ))}
    </div>
  );
}
