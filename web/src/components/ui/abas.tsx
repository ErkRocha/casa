import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Pilula } from "./controls";

/**
 * Abas em pílula (`RevisarDesktop`: "Tudo (6) · Possíveis duplicatas (2)").
 * Teclado do padrão de abas: setas andam entre elas, Home e End vão às
 * pontas, e só a aba atual entra no Tab.
 */
export function Abas<T extends string>({
  rotulo,
  abas,
  atual,
  onMudar,
  idPainel,
  fundo = "superficie",
  className,
}: {
  rotulo: string;
  abas: Array<{ id: T; rotulo: ReactNode }>;
  atual: T;
  onMudar: (id: T) => void;
  /** O `id` do painel que as abas controlam. */
  idPainel: string;
  fundo?: "superficie" | "superficie-2";
  className?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function aoTeclar(evento: KeyboardEvent<HTMLDivElement>) {
    const indice = abas.findIndex((a) => a.id === atual);
    const ultimo = abas.length - 1;
    const destino =
      evento.key === "ArrowRight"
        ? indice === ultimo
          ? 0
          : indice + 1
        : evento.key === "ArrowLeft"
          ? indice === 0
            ? ultimo
            : indice - 1
          : evento.key === "Home"
            ? 0
            : evento.key === "End"
              ? ultimo
              : null;
    if (destino === null) return;
    evento.preventDefault();
    const aba = abas[destino];
    if (!aba) return;
    onMudar(aba.id);
    refs.current[destino]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={rotulo}
      onKeyDown={aoTeclar}
      className={cn("-mx-7 flex gap-4 overflow-x-auto px-7 md:mx-0 md:flex-wrap md:px-0", className)}
    >
      {abas.map((aba, i) => (
        <Pilula
          key={aba.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="tab"
          aria-selected={aba.id === atual}
          aria-controls={idPainel}
          tabIndex={aba.id === atual ? 0 : -1}
          ativa={aba.id === atual}
          fundo={fundo}
          onClick={() => onMudar(aba.id)}
        >
          {aba.rotulo}
        </Pilula>
      ))}
    </div>
  );
}
