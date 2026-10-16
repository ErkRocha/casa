import { mesCurto, mesPorExtenso, somarMeses } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BotaoIcone } from "./controls";
import { Icone } from "./icone";

/**
 * O seletor de mês das pranchetas de Lançamentos: "‹ Outubro de 2026 ›" numa
 * pílula branca, "Out 2026" no celular. O nome do mês é anunciado quando
 * muda, para quem usa leitor de tela saber onde chegou.
 */
export function SeletorMes({
  competencia,
  onMudar,
  className,
}: {
  competencia: string;
  onMudar: (competencia: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("bg-superficie rounded-interno flex items-center md:px-2", className)}>
      <BotaoIcone
        rotulo="Mês anterior"
        className="w-20 bg-transparent"
        onClick={() => onMudar(somarMeses(competencia, -1))}
      >
        <Icone nome="esquerda" tamanho={16} />
      </BotaoIcone>
      <span aria-live="polite" className="text-apoio md:text-corpo font-semibold md:px-3">
        <span className="md:hidden">{mesCurto(competencia)}</span>
        <span className="hidden md:inline">{mesPorExtenso(competencia)}</span>
      </span>
      <BotaoIcone
        rotulo="Próximo mês"
        className="w-20 bg-transparent"
        onClick={() => onMudar(somarMeses(competencia, 1))}
      >
        <Icone nome="direita" tamanho={16} />
      </BotaoIcone>
    </div>
  );
}
