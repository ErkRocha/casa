import { cn } from "@/lib/utils";
import { rotuloDaForma } from "./forma-pagamento";
import type { TipoPagamento } from "./types";

/**
 * Etiqueta azul da forma de pagamento das pranchetas (D-22): "Cartão Nubank
 * 7704", "Débito Sicredi", "Pix Nubank", "Boleto". O apelido completo fica no
 * `title`, para quem quiser conferir qual forma exatamente.
 */
export function FormaPagamentoTag({
  tipo,
  apelido,
  contaNome,
  curto = false,
  className,
}: {
  tipo: TipoPagamento | null | undefined;
  apelido: string | null | undefined;
  contaNome?: string | null;
  curto?: boolean;
  className?: string;
}) {
  if (!tipo && !apelido) {
    return <span className="text-pequeno text-texto-2">—</span>;
  }
  return (
    <span
      title={apelido ?? undefined}
      className={cn(
        "bg-destaque-fundo text-destaque-hover text-pequeno rounded-selo inline-block",
        "max-w-full truncate px-4 py-0.5 align-middle font-semibold",
        curto ? "px-3.5 py-px" : "py-1.5",
        className,
      )}
    >
      {rotuloDaForma(tipo, apelido, contaNome, { curto })}
    </span>
  );
}
