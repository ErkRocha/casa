import { reais, sinal } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TotaisPeriodo } from "../types";

/**
 * Os totais do filtro (`LancamentosDesktop`): despesas, receitas, quantos
 * lançamentos e as transferências à parte, fora das somas (D-05). Tudo
 * somado no banco com a mesma cláusula da listagem (D-14). O celular mostra
 * só despesas e receitas, como a prancheta.
 */
export function TotaisDoFiltro({
  totais,
  quantidade,
}: {
  totais: TotaisPeriodo;
  quantidade: number;
}) {
  const transferencias = totais.quantidade_transferencias;
  return (
    <section
      aria-label="Totais do filtro"
      className="grid grid-cols-2 gap-4 md:grid-cols-4 md:gap-6"
    >
      <Total rotulo="Despesas" valor={reais(totais.total_despesa)} />
      <Total rotulo="Receitas" valor={reais(totais.total_receita)} receita />
      <Total
        rotulo="Lançamentos"
        valor={quantidade.toLocaleString("pt-BR")}
        className="hidden md:flex"
      />
      <div className="bg-superficie rounded-cartao hidden flex-col gap-2 px-8 py-7 md:flex">
        <span className="text-pequeno text-texto-2">Transferências</span>
        <span className="text-corpo font-medio leading-snug">
          {transferencias === 0 || sinal(totais.total_transferencia) === 0
            ? "Nenhuma neste filtro"
            : `${reais(totais.total_transferencia)}, fora das somas`}
        </span>
      </div>
    </section>
  );
}

function Total({
  rotulo,
  valor,
  receita = false,
  className,
}: {
  rotulo: string;
  valor: string;
  receita?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-superficie rounded-sub md:rounded-cartao flex flex-col gap-1 px-7 py-6 md:gap-2 md:px-8 md:py-7",
        className,
      )}
    >
      <span className="text-pequeno text-texto-2">{rotulo}</span>
      <span
        className={cn("md:text-valor-medio text-[19px] font-bold", receita && "text-receita")}
      >
        {valor}
      </span>
    </div>
  );
}
