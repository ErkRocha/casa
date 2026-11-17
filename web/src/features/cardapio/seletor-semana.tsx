import { BotaoIcone } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { cn } from "@/lib/utils";
import { intervaloDaSemana } from "./datas";

/** Anterior e próxima semana, com o intervalo no meio ("16 a 22 de novembro"). */
export function SeletorSemana({
  inicio,
  resumo,
  naSemanaAtual,
  onIr,
  onHoje,
  className,
}: {
  inicio: string;
  /** Linha de baixo: "41 pratos · Erik e Laura". */
  resumo?: string;
  naSemanaAtual: boolean;
  /** Pula `n` semanas: -1 ou 1. */
  onIr: (n: number) => void;
  onHoje: () => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-4", className)}>
      <div className="bg-superficie rounded-sub flex flex-1 items-center justify-between p-2 md:max-w-[420px]">
        <BotaoIcone rotulo="Semana anterior" className="bg-transparent" onClick={() => onIr(-1)}>
          <Icone nome="esquerda" tamanho={16} />
        </BotaoIcone>
        <span className="flex flex-col items-center gap-px px-2 text-center">
          <span aria-live="polite" className="text-enfase font-forte">
            {intervaloDaSemana(inicio)}
          </span>
          {resumo ? <span className="text-selo text-texto-2">{resumo}</span> : null}
        </span>
        <BotaoIcone rotulo="Próxima semana" className="bg-transparent" onClick={() => onIr(1)}>
          <Icone nome="direita" tamanho={16} />
        </BotaoIcone>
      </div>
      {naSemanaAtual ? null : (
        <button
          type="button"
          onClick={onHoje}
          className="bg-superficie text-destaque text-apoio min-h-22 cursor-pointer rounded-full border-none px-7 font-semibold"
        >
          Esta semana
        </button>
      )}
    </div>
  );
}
