import { Icone } from "@/components/ui/icone";
import type { Roteiro } from "./types";

/**
 * Os avisos do roteiro no topo da semana (validade estourada: "a aveia não
 * dura até domingo"). Vêm prontos da API; "Ver no roteiro" abre o roteiro.
 */
export function AvisosRoteiro({
  avisos,
  onVerRoteiro,
}: {
  avisos: Roteiro["avisos"];
  onVerRoteiro?: () => void;
}) {
  if (avisos.length === 0) return null;
  return (
    <div
      role="status"
      className="bg-atencao-fundo-2 text-atencao-texto rounded-cartao flex items-start gap-5 px-7 py-6 shadow-[inset_0_0_0_1px_#F0D9A6]"
    >
      <span className="mt-1 flex shrink-0">
        <Icone nome="aviso" tamanho={18} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {avisos.map((a) => (
          <span key={a.refeicao_id} className="text-apoio leading-normal">
            {a.texto}
          </span>
        ))}
      </div>
      {onVerRoteiro ? (
        <button
          type="button"
          onClick={onVerRoteiro}
          className="bg-superficie text-atencao-texto text-apoio min-h-20 shrink-0 cursor-pointer rounded-[9px] border-none px-6 font-semibold shadow-[inset_0_0_0_1px_var(--color-atencao-borda-2)]"
        >
          Ver no roteiro
        </button>
      ) : null}
    </div>
  );
}
