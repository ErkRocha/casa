import { useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { BotaoIcone } from "./controls";
import { Icone } from "./icone";

/**
 * Diálogo modal sobre o `<dialog>` nativo: o navegador prende o foco dentro,
 * fecha no Esc e devolve o foco a quem abriu. Clique no fundo também fecha.
 *
 * `lateral` é o painel que encosta à direita no computador (novo
 * lançamento) e ocupa a tela no celular; sem ele, o diálogo fica no centro.
 */
export function Dialogo({
  aberto,
  onFechar,
  titulo,
  lateral = false,
  children,
}: {
  aberto: boolean;
  onFechar: () => void;
  titulo: string;
  lateral?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();

  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    if (aberto && !dialogo.open) dialogo.showModal();
    if (!aberto && dialogo.open) dialogo.close();
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      onClose={onFechar}
      onClick={(evento) => {
        // O clique no fundo chega com o próprio <dialog> como alvo.
        if (evento.target === ref.current) onFechar();
      }}
      className={cn(
        "bg-superficie text-texto m-0 max-h-none max-w-none border-none p-0",
        "backdrop:bg-[rgba(23,32,51,0.45)]",
        lateral
          ? "fixed inset-0 h-full w-full md:inset-y-0 md:right-0 md:left-auto md:w-[420px]"
          : "rounded-bloco fixed top-1/2 left-1/2 max-h-[85vh] w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2",
      )}
    >
      {aberto ? (
        <div className="flex h-full flex-col">
          <div className="flex items-start justify-between gap-6 px-9 pt-8 md:px-11 md:pt-10">
            <h2 id={idTitulo} className="text-bloco font-forte m-0 pt-2">
              {titulo}
            </h2>
            <BotaoIcone rotulo="Fechar" onClick={onFechar} className="-mt-1 -mr-3">
              <Icone nome="fechar" tamanho={18} />
            </BotaoIcone>
          </div>
          <div className="flex-1 overflow-y-auto px-9 pt-4 pb-9 md:px-11 md:pb-10">{children}</div>
        </div>
      ) : null}
    </dialog>
  );
}
