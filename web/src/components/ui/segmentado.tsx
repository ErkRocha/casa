import { useRef, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

/**
 * Seletor segmentado das pranchetas de Análises ("Este mês · 3 meses · 12
 * meses", "Todos · Erik · Laura · Juntos"): uma escolha entre poucas, que
 * vale para a tela inteira. É um grupo de rádio: setas mudam a escolha, e só
 * a escolhida entra no Tab.
 *
 * `tom` é a cor da escolhida: `escuro` (período) ou `destaque` (pessoa).
 * `cheio` divide a largura em partes iguais, como no celular.
 */
export function Segmentado<T extends string | number>({
  rotulo,
  opcoes,
  atual,
  onMudar,
  tom = "escuro",
  cheio = false,
  className,
}: {
  rotulo: string;
  opcoes: Array<{ id: T; rotulo: string }>;
  atual: T;
  onMudar: (id: T) => void;
  tom?: "escuro" | "destaque";
  cheio?: boolean;
  className?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function aoTeclar(evento: KeyboardEvent<HTMLDivElement>) {
    const passo =
      evento.key === "ArrowRight" || evento.key === "ArrowDown"
        ? 1
        : evento.key === "ArrowLeft" || evento.key === "ArrowUp"
          ? -1
          : 0;
    if (passo === 0) return;
    evento.preventDefault();
    const indice = opcoes.findIndex((o) => o.id === atual);
    const destino = (indice + passo + opcoes.length) % opcoes.length;
    const opcao = opcoes[destino];
    if (!opcao) return;
    onMudar(opcao.id);
    refs.current[destino]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={rotulo}
      onKeyDown={aoTeclar}
      className={cn(
        "bg-superficie rounded-interno gap-1 p-2",
        cheio ? "grid auto-cols-fr grid-flow-col" : "flex",
        className,
      )}
    >
      {opcoes.map((opcao, i) => {
        const escolhida = opcao.id === atual;
        return (
          <button
            key={String(opcao.id)}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={escolhida}
            tabIndex={escolhida ? 0 : -1}
            onClick={() => onMudar(opcao.id)}
            className={cn(
              "text-apoio min-h-22 cursor-pointer rounded-[9px] border-none px-7 whitespace-nowrap",
              escolhida
                ? tom === "escuro"
                  ? "bg-texto font-semibold text-white"
                  : "bg-destaque-fundo text-destaque-hover font-semibold"
                : "text-texto-apoio bg-transparent",
            )}
          >
            {opcao.rotulo}
          </button>
        );
      })}
    </div>
  );
}
