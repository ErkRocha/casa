import { PersonDot } from "@/components/layout/person-legend";
import { usePessoas } from "@/features/cadastros/queries";
import { corDoBalde, rotuloDoBalde } from "@/features/filters/baldes";
import { formatBRLTexto, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TotaisPeriodo } from "../types";

/**
 * Rodapé da tabela: resultado do período filtrado, quebrado por balde.
 *
 * Os números vêm somados do banco com a mesma cláusula de filtro da listagem
 * — não são a soma da página que está na tela (D-14). Transferências ficam
 * fora: pagar fatura não é despesa nova.
 */
export function TotalsBar({ totais }: { totais: TotaisPeriodo }) {
  const { data: pessoas = [] } = usePessoas();
  const resultado = toNumero(totais.resultado);

  const baldes = [
    ...pessoas.slice(0, 2).map((p) => ({ chave: String(p.id), balde: p.id as number | "conjunto" })),
    { chave: "conjunto", balde: "conjunto" as const },
  ];

  return (
    <div className="border-border-faint flex flex-wrap items-center justify-between gap-5 border-t px-8 py-9">
      <div className="flex items-baseline gap-5">
        <span className="text-caption text-text-tertiary tracking-label-wide uppercase">
          Resultado do período filtrado
        </span>
        <span
          className={cn(
            "tabular text-title-lg font-bold",
            resultado < 0 ? "text-expense" : "text-income",
          )}
        >
          {formatBRLTexto(totais.resultado)}
        </span>
      </div>

      <div className="flex flex-wrap gap-9">
        <span className="text-body text-text-secondary flex items-center gap-3">
          Despesas
          <span className="tabular text-text-primary font-semibold">
            {formatBRLTexto(totais.total_despesa)}
          </span>
        </span>
        <span className="text-body text-text-secondary flex items-center gap-3">
          Receitas
          <span className="tabular text-text-primary font-semibold">
            {formatBRLTexto(totais.total_receita)}
          </span>
        </span>

        {baldes.map(({ chave, balde }) => (
          <span key={chave} className="text-body text-text-secondary flex items-center gap-3">
            <PersonDot color={corDoBalde(balde, pessoas)} />
            {rotuloDoBalde(balde, pessoas)}:
            <span className="tabular">{formatBRLTexto(totais.por_balde[chave] ?? "0")}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
