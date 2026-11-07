import { reais, sinal } from "@/lib/format";
import { cn } from "@/lib/utils";
import { dataCurta } from "../../textos";
import { classesDaCor } from "./cores";
import type { LinhaGrafico } from "./tipos";

/**
 * Painel do dia escolhido: a data e o valor acumulado de cada linha visível
 * naquele dia, com a bolinha da cor e quanto disso ainda é pendente. Fica sob
 * o gráfico (não flutua sobre ele), então não cobre linhas nem estoura a tela.
 */
export function PainelDoDia({
  data,
  ehHoje,
  indice,
  linhas,
  className,
}: {
  data: string;
  ehHoje: boolean;
  indice: number;
  linhas: LinhaGrafico[];
  className?: string;
}) {
  return (
    <div
      aria-live="polite"
      className={cn(
        "bg-superficie-2 rounded-interno text-pequeno flex min-h-[72px] flex-col gap-3 px-6 py-5 leading-snug",
        className,
      )}
    >
      <span className="font-forte">
        {dataCurta(data)}
        {ehHoje ? " · hoje" : ""}
      </span>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {linhas.map((linha) => {
          const pendente = linha.pendenteAcumulado[indice] ?? "0";
          return (
            <li key={linha.chave} className="flex items-center gap-3">
              <span
                aria-hidden
                className={cn(
                  "inline-block size-5 shrink-0 rounded-full",
                  classesDaCor(linha.cor).fundo,
                )}
              />
              <span className="min-w-0 flex-1">
                {linha.rotulo}
                {linha.temPendente[indice] ? (
                  <span className="text-texto-2"> · compra pendente neste dia</span>
                ) : null}
              </span>
              <span className="text-right">
                <span className="font-forte">{reais(linha.acumulado[indice] ?? "0")}</span>
                {sinal(pendente) > 0 ? (
                  <span className="text-texto-2 block">inclui {reais(pendente)} pendente</span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
