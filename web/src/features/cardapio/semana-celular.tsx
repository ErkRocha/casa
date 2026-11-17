import type { ReactNode } from "react";

import { Icone } from "@/components/ui/icone";
import { cn } from "@/lib/utils";
import { diaCurto, diasDaSemana, numeroDoDia } from "./datas";
import { ChipsPessoas } from "./pratos";
import { nomeDoPrato, ROTULO_TIPO, TIPOS } from "./textos";
import type { VistaDaSemana } from "./vista";

/**
 * A semana no celular (`CardapioSemanaCelular`): os sete dias em cima, e
 * embaixo as quatro refeições do dia escolhido, cada prato com quem come e
 * como fica pronto. Dia passado apagado; hoje com contorno; o escolhido, azul.
 */
export function SemanaCelular({
  v,
  dia,
  onEscolherDia,
  children,
}: {
  v: VistaDaSemana;
  dia: string;
  onEscolherDia: (dia: string) => void;
  /** "A semana inteira": roteiro, lista e copiar, que a página monta. */
  children?: ReactNode;
}) {
  const refeicoesDoDia = v.semana.dias.find((d) => d.dia === dia)?.refeicoes ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div role="group" aria-label="Dia da semana" className="grid grid-cols-7 gap-2">
        {diasDaSemana(v.semana.inicio).map((d) => {
          const escolhido = d === dia;
          const passado = d < v.hoje;
          const hoje = d === v.hoje;
          return (
            <button
              key={d}
              type="button"
              aria-pressed={escolhido}
              aria-label={`${diaCurto(d)} ${numeroDoDia(d)}${hoje ? ", hoje" : ""}`}
              onClick={() => onEscolherDia(d)}
              className={cn(
                "flex h-28 cursor-pointer flex-col items-center justify-center gap-1 rounded-interno border-none",
                escolhido ? "bg-destaque text-white" : "bg-superficie text-texto",
                !escolhido && passado && "text-texto-2 opacity-70",
                !escolhido && hoje && "shadow-[inset_0_0_0_2px_var(--color-destaque)]",
              )}
            >
              <span className="text-selo font-medium">{diaCurto(d)}</span>
              <span className="text-enfase font-bold">{numeroDoDia(d)}</span>
            </button>
          );
        })}
      </div>

      {TIPOS.map((tipo) => {
        const pratos = refeicoesDoDia.filter((r) => r.tipo === tipo);
        return (
          <section
            key={tipo}
            aria-label={ROTULO_TIPO[tipo]}
            className="bg-superficie rounded-bloco flex flex-col gap-3 p-8"
          >
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-apoio font-forte text-texto-2 m-0">{ROTULO_TIPO[tipo]}</h2>
              <button
                type="button"
                onClick={() => v.onEditar({ dia, tipo, adicionar: pratos.length === 0 })}
                aria-label={
                  pratos.length === 0
                    ? `Adicionar prato no ${ROTULO_TIPO[tipo].toLowerCase()}`
                    : `Editar ${ROTULO_TIPO[tipo].toLowerCase()}`
                }
                className="text-destaque text-apoio flex min-h-22 cursor-pointer items-center gap-2 border-none bg-transparent px-2 font-semibold"
              >
                {pratos.length === 0 ? (
                  <>
                    <Icone nome="adicionar" tamanho={14} espessura={2.4} />
                    Adicionar
                  </>
                ) : (
                  "Editar"
                )}
              </button>
            </div>
            {pratos.length === 0 ? (
              <p className="text-apoio text-texto-2 m-0 pb-2">Nada planejado.</p>
            ) : (
              pratos.map((r) => {
                const preparo = v.preparo.get(r.id);
                const nome = (
                  <>
                    <span className="text-enfase font-semibold">{nomeDoPrato(r)}</span>
                    {preparo ? (
                      <span
                        className={cn(
                          "text-pequeno",
                          preparo.aviso ? "text-atencao-texto font-semibold" : "text-texto-2",
                        )}
                      >
                        {preparo.texto}
                      </span>
                    ) : null}
                  </>
                );
                return (
                  <div
                    key={r.id}
                    className="linha-acima flex min-h-22 items-center justify-between gap-5 py-2"
                  >
                    {r.receita && !r.receita.apagada ? (
                      <button
                        type="button"
                        onClick={() => v.onAbrirReceita(r.receita!.id)}
                        className="text-texto flex min-w-0 flex-1 cursor-pointer flex-col gap-1 border-none bg-transparent p-0 text-left"
                      >
                        {nome}
                      </button>
                    ) : (
                      <span className="flex min-w-0 flex-1 flex-col gap-1">{nome}</span>
                    )}
                    <span className="shrink-0">
                      <ChipsPessoas refeicao={r} pessoas={v.pessoas} />
                    </span>
                  </div>
                );
              })
            )}
          </section>
        );
      })}

      {children}
    </div>
  );
}
