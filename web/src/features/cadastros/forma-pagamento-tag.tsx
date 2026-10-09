import { cn } from "@/lib/utils";
import { TIPO_PAGAMENTO_LABEL, type TipoPagamento } from "./types";

/**
 * A forma de pagamento com o que importa na frente: "Cartão •••• 1111",
 * "Pix", "Débito", "Boleto". O apelido (que diz a conta) vem embaixo, menor.
 *
 * Só o apelido não bastava: "Pix Sicredi" e "Débito Sicredi" ficavam com a
 * mesma cara na tabela, e desde a D-21 a conta corrente tem uma forma por
 * operação — a diferença entre elas é justamente o que se quer ver.
 */
export function FormaPagamentoTag({
  tipo,
  apelido,
  className,
}: {
  tipo: TipoPagamento | null | undefined;
  apelido: string | null | undefined;
  className?: string;
}) {
  if (!tipo && !apelido) {
    return <span className="text-body-sm text-text-tertiary">—</span>;
  }
  const rotulo = rotuloDaForma(tipo, apelido);
  return (
    <span className={cn("flex min-w-0 flex-col", className)} title={apelido ?? undefined}>
      <span className="text-body-sm text-text-primary truncate font-semibold">{rotulo}</span>
      {apelido && apelido !== rotulo ? (
        <span className="text-caption text-text-tertiary truncate">{apelido}</span>
      ) : null}
    </span>
  );
}

/** "Cartão •••• 1111" quando o apelido termina no final do cartão. */
function rotuloDaForma(
  tipo: TipoPagamento | null | undefined,
  apelido: string | null | undefined,
): string {
  if (!tipo) return apelido ?? "—";
  if (tipo === "credito") {
    const final = /(\d{4})\s*$/.exec(apelido ?? "")?.[1];
    return final ? `Cartão •••• ${final}` : "Cartão de crédito";
  }
  return TIPO_PAGAMENTO_LABEL[tipo];
}
