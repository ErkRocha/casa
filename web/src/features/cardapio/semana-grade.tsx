import { cn } from "@/lib/utils";
import { diaCurto, diasDaSemana, numeroDoDia } from "./datas";
import { ChipsPessoas } from "./pratos";
import { nomeDoPrato, ROTULO_TIPO, TIPOS } from "./textos";
import type { VistaDaSemana } from "./vista";

/**
 * A semana no computador (`CardapioDesktop`): grade de 7 dias por 4 refeições.
 * Cada célula é um botão que abre o prato para trocar; o dia passado fica
 * apagado e hoje com contorno. Mostra os pratos, quem come e como fica pronto.
 */
export function SemanaGrade({ v }: { v: VistaDaSemana }) {
  const dias = diasDaSemana(v.semana.inicio);

  return (
    <section aria-label="Semana" className="bg-superficie rounded-bloco p-4 pb-6">
      <div className="overflow-x-auto">
        <div className="grid min-w-[960px] grid-cols-[132px_repeat(7,minmax(118px,1fr))] gap-3">
          <span />
          {dias.map((d) => {
            const hoje = d === v.hoje;
            const passou = d < v.hoje;
            const sessao = v.semana.sessoes.find((s) => s.data === d);
            return (
              <div
                key={d}
                className={cn(
                  "rounded-interno flex flex-col gap-px px-5 pt-5 pb-4",
                  hoje ? "bg-destaque text-white" : "bg-[#F7F8FA] text-texto",
                  passou && "text-texto-2",
                )}
              >
                <span className="text-pequeno font-medium">{diaCurto(d)}</span>
                <span className="text-bloco font-bold">{numeroDoDia(d)}</span>
                <span className="text-selo">
                  {hoje ? "hoje" : passou ? "passou" : sessao ? "preparo" : " "}
                </span>
              </div>
            );
          })}

          {TIPOS.map((tipo) => (
            <Linha key={tipo} tipo={tipo} dias={dias} v={v} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Linha({
  tipo,
  dias,
  v,
}: {
  tipo: (typeof TIPOS)[number];
  dias: string[];
  v: VistaDaSemana;
}) {
  return (
    <>
      <div className="text-apoio font-forte text-texto-apoio linha-acima px-4 py-6">
        {ROTULO_TIPO[tipo]}
      </div>
      {dias.map((d) => {
        const pratos =
          v.semana.dias.find((x) => x.dia === d)?.refeicoes.filter((r) => r.tipo === tipo) ?? [];
        const passou = d < v.hoje;
        const hoje = d === v.hoje;
        const curtos = [
          ...new Set(
            pratos.map((r) => v.preparo.get(r.id)?.curto).filter((c): c is string => !!c),
          ),
        ];
        const primeiro = pratos[0];
        const nomes = pratos.map(nomeDoPrato).join(" · ");
        return (
          <button
            key={d}
            type="button"
            onClick={() => v.onEditar({ dia: d, tipo, adicionar: pratos.length === 0 })}
            aria-label={`${ROTULO_TIPO[tipo]}, ${diaCurto(d)} ${numeroDoDia(d)}: ${nomes || "nada planejado"}`}
            className={cn(
              "text-texto rounded-interno flex min-h-52 cursor-pointer flex-col justify-between gap-4 border-none bg-[#F7F8FA] p-5 text-left",
              hoje && "bg-selecao shadow-[inset_0_0_0_1.5px_#9DB4EA]",
              passou && "opacity-60",
            )}
          >
            {primeiro ? (
              <>
                <span className="text-pequeno font-medium leading-snug">{nomes}</span>
                <span className="flex flex-wrap items-center gap-2">
                  <ChipsPessoas refeicao={primeiro} pessoas={v.pessoas} curto />
                  {curtos.length > 0 ? (
                    <span
                      className={cn(
                        "text-selo",
                        curtos.includes("aviso") ? "text-atencao-texto font-semibold" : "text-texto-2",
                      )}
                    >
                      {curtos.join(" · ")}
                    </span>
                  ) : null}
                </span>
              </>
            ) : (
              <span className="text-selo text-texto-2">+ Adicionar</span>
            )}
          </button>
        );
      })}
    </>
  );
}
