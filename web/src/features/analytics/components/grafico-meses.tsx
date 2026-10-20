import { mesPorExtenso, reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import { altura, mesAbreviado, rotuloDoEixo, topoDaEscala } from "../textos";
import type { MesAnalise } from "../types";

const ALTURA = { computador: 220, celular: 150 } as const;

/**
 * Barras por mês (`AnalisesDesktop`: receitas e despesas; `AnalisesCelular`:
 * só o gasto). O mês corrente sai em azul claro: está pela metade. Para quem
 * não vê o gráfico, os mesmos números vão numa tabela oculta.
 */
export function GraficoMeses({
  meses,
  variante,
}: {
  meses: MesAnalise[];
  variante: "computador" | "celular";
}) {
  const comReceitas = variante === "computador";
  const total = ALTURA[variante];
  const topo = topoDaEscala(
    meses.flatMap((m) => (comReceitas ? [m.despesas, m.receitas] : [m.despesas])),
  );
  const primeiro = meses[0];
  const ultimo = meses[meses.length - 1];
  const descricao =
    primeiro && ultimo
      ? `${comReceitas ? "Receitas e despesas" : "Despesas"} de ${mesPorExtenso(primeiro.competencia).toLowerCase()} a ${mesPorExtenso(ultimo.competencia).toLowerCase()}`
      : "Sem meses no período";

  return (
    <>
      <div role="img" aria-label={descricao} className="flex gap-5">
        {comReceitas ? (
          <div
            aria-hidden
            className="text-selo text-texto-2 flex flex-col justify-between whitespace-nowrap"
            style={{ height: total }}
          >
            <span>{rotuloDoEixo(topo)}</span>
            <span>{rotuloDoEixo(topo / 2)}</span>
            <span>0</span>
          </div>
        ) : null}
        <div className="flex min-w-0 flex-1 flex-col gap-3 md:gap-4">
          <div
            aria-hidden
            className={cn(
              "grid items-end shadow-[inset_0_-1px_0_var(--color-linha)]",
              comReceitas ? "gap-5" : "gap-2.5",
            )}
            style={{ height: total, gridTemplateColumns: `repeat(${meses.length}, minmax(0, 1fr))` }}
          >
            {meses.map((m) => (
              <div key={m.competencia} className="flex h-full items-end justify-center gap-1.5">
                {comReceitas ? (
                  <div
                    className="bg-receita-barra w-[40%] max-w-11 rounded-t-[4px]"
                    style={{ height: altura(m.receitas, topo, total) }}
                  />
                ) : null}
                <div
                  className={cn(
                    "rounded-t-[4px]",
                    comReceitas ? "w-[40%] max-w-11" : "w-full",
                    m.em_curso ? "bg-destaque-parcial" : "bg-destaque",
                  )}
                  style={{ height: altura(m.despesas, topo, total) }}
                />
              </div>
            ))}
          </div>
          <div
            aria-hidden
            className={cn("grid", comReceitas ? "gap-5" : "gap-2.5")}
            style={{ gridTemplateColumns: `repeat(${meses.length}, minmax(0, 1fr))` }}
          >
            {meses.map((m) => (
              <span
                key={m.competencia}
                className={cn("text-texto-2 text-center", comReceitas ? "text-selo" : "text-[10px]")}
              >
                {mesAbreviado(m.competencia)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <table className="sr-only">
        <caption>{descricao}</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            <th scope="col">Despesas</th>
            {comReceitas ? <th scope="col">Receitas</th> : null}
          </tr>
        </thead>
        <tbody>
          {meses.map((m) => (
            <tr key={m.competencia}>
              <th scope="row">
                {mesPorExtenso(m.competencia)}
                {m.em_curso ? " (em andamento)" : ""}
              </th>
              <td>{reais(m.despesas)}</td>
              {comReceitas ? <td>{reais(m.receitas)}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
