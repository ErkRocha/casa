import { cn } from "@/lib/utils";
import { numeroCurto, tomDaPessoa } from "./textos";
import type { Pessoa, Refeicao } from "./types";

/**
 * Quem come e quanto: "Erik 1,5", "Laura 1". A porção ajustada nesta
 * refeição fica com contorno (e "ajustada" para o leitor de tela); a padrão
 * do perfil é só a pílula. `curto` abrevia o nome ("E 1,5") para a grade.
 */
export function ChipsPessoas({
  refeicao,
  pessoas,
  curto = false,
}: {
  refeicao: Refeicao;
  /** Todas as pessoas, na ordem de cadastro: a ordem fixa a cor de cada uma. */
  pessoas: Pessoa[];
  curto?: boolean;
}) {
  if (refeicao.pessoas.length === 0) {
    return <span className="text-selo text-texto-2">Ninguém</span>;
  }
  return (
    <span className="flex flex-wrap gap-2">
      {refeicao.pessoas.map((p) => {
        const indice = pessoas.findIndex((x) => x.id === p.pessoa_id);
        return (
          <span
            key={p.pessoa_id}
            title={p.ajustada ? "Porção ajustada nesta refeição" : undefined}
            className={cn(
              "rounded-full px-4 py-[3px] text-[12px] font-[650]",
              tomDaPessoa(indice),
              p.ajustada && "shadow-[inset_0_0_0_1.5px_currentColor]",
            )}
          >
            {curto ? p.nome.charAt(0) : p.nome} {numeroCurto(p.porcoes)}
            {p.ajustada ? <span className="sr-only"> (ajustada)</span> : null}
          </span>
        );
      })}
    </span>
  );
}
