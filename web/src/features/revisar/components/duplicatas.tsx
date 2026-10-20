import { Card } from "@/components/ui/card";
import { Button, Selo } from "@/components/ui/controls";
import { reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import { deOndeVeio } from "../textos";
import type { GrupoDuplicata, ItemRevisar } from "../types";

/**
 * Possíveis duplicatas (`RevisarDesktop`, `RevisarCelular`): os gêmeos lado
 * a lado e a pergunta. "Manter só um" descarta as cópias; "são dois" grava
 * todos, quando o banco aceita (D-07).
 */
export function Duplicatas({
  grupos,
  ocupado,
  onResolver,
}: {
  grupos: GrupoDuplicata[];
  ocupado: boolean;
  onResolver: (manter: number[], descartar: number[]) => void;
}) {
  return (
    <>
      {/* Celular: um bloco por grupo. */}
      <div className="flex flex-col gap-7 md:hidden">
        {grupos.map((grupo) => (
          <Card key={chave(grupo)} className="flex flex-col gap-6 p-8">
            <Selo tom="atencao" className="self-start">
              Possível duplicata
            </Selo>
            <Grupo grupo={grupo} ocupado={ocupado} onResolver={onResolver} curto />
          </Card>
        ))}
      </div>

      {/* Computador: um bloco com todos os grupos. */}
      <Card className="hidden flex-col gap-7 px-11 py-10 md:flex">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="text-bloco font-forte m-0">Possíveis duplicatas</h2>
          <span className="text-apoio text-texto-2">
            O banco enviou o mesmo valor duas vezes no mesmo dia
          </span>
        </div>
        {grupos.map((grupo) => (
          <div key={chave(grupo)} className="bg-superficie-2 rounded-sub flex flex-col gap-6 p-8">
            <Grupo grupo={grupo} ocupado={ocupado} onResolver={onResolver} />
          </div>
        ))}
      </Card>
    </>
  );
}

function chave(grupo: GrupoDuplicata): string {
  return grupo.itens.map((i) => i.id).join("-");
}

function Grupo({
  grupo,
  ocupado,
  onResolver,
  curto = false,
}: {
  grupo: GrupoDuplicata;
  ocupado: boolean;
  onResolver: (manter: number[], descartar: number[]) => void;
  curto?: boolean;
}) {
  const transferencia = grupo.itens.some((i) => i.tipo_sugerido === "transferencia");
  const pendentes = grupo.itens.filter((i) => i.status === "pendente");
  // Fica o que já é transação; senão, o primeiro que chegou.
  const fica = grupo.itens.find((i) => i.status === "aprovado") ?? pendentes[0];
  const descartar = pendentes.filter((i) => i.id !== fica?.id).map((i) => i.id);
  const sozinho = grupo.itens.length === 1;

  const pergunta = sozinho
    ? "A outra cópia já saiu da revisão."
    : transferencia
      ? "É a mesma transferência?"
      : "É o mesmo lançamento?";
  const manterUm = sozinho ? "Manter este" : transferencia ? "Sim, manter só uma" : "Sim, manter só um";
  const saoDois = transferencia ? "Não, são duas" : "Não, são dois";

  return (
    <>
      <div className={cn("grid gap-4", !curto && "grid-cols-2 gap-5")}>
        {grupo.itens.map((item) => (
          <Copia key={item.id} item={item} curto={curto} />
        ))}
      </div>
      <div
        className={cn(
          curto ? "flex flex-col gap-5" : "flex flex-wrap items-center gap-5",
        )}
      >
        <span className="text-corpo flex-1 font-semibold">{pergunta}</span>
        <div className={cn(curto ? "grid grid-cols-2 gap-4" : "flex flex-wrap gap-5")}>
          <Button
            disabled={ocupado || !fica}
            onClick={() => fica && onResolver([fica.id], descartar)}
            className={cn(
              curto && "text-corpo min-h-24",
              curto && (sozinho || !grupo.podem_ser_dois) && "col-span-2",
            )}
          >
            {manterUm}
          </Button>
          {!sozinho && grupo.podem_ser_dois ? (
            <Button
              variant="secondary"
              disabled={ocupado}
              onClick={() => onResolver(grupo.itens.map((i) => i.id), [])}
              className={cn(curto && "text-corpo min-h-24")}
            >
              {saoDois}
            </Button>
          ) : null}
        </div>
      </div>
      {!sozinho && !grupo.podem_ser_dois ? (
        <p className="text-pequeno text-texto-2 m-0 leading-normal">
          Para o banco os dois são o mesmo lançamento (mesma data, valor, descrição e forma de
          pagamento), e só um pode entrar. Se forem dois mesmo, mantenha um e lance o outro à
          mão em Lançamentos.
        </p>
      ) : null}
    </>
  );
}

function Copia({ item, curto }: { item: ItemRevisar; curto: boolean }) {
  const lancado = item.status === "aprovado";
  return (
    <div
      className={cn(
        "flex gap-2",
        curto
          ? "bg-superficie-2 rounded-interno items-center justify-between gap-5 p-6"
          : "bg-superficie rounded-botao flex-col px-7 py-6",
      )}
    >
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-corpo flex flex-wrap items-center gap-3 font-semibold">
          {item.descricao}
          {lancado ? <Selo tom="receita">Já lançado</Selo> : null}
        </span>
        <span className={cn("text-texto-2", curto ? "text-pequeno" : "text-apoio")}>
          {deOndeVeio(item, curto)}
        </span>
      </span>
      <span className={cn("font-bold whitespace-nowrap", curto ? "text-enfase" : "text-[17px]")}>
        {reais(item.valor)}
      </span>
    </div>
  );
}
