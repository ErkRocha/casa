import { useState } from "react";

import { Button } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { quantidadeDoItem } from "@/features/compras/textos";
import { ApiError } from "@/lib/api";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { useGravarLista, useListaPrevia } from "./queries";
import type { ListaCardapio } from "./types";

/** Por que a semana não gera lista: a API dá 409 (D-30), e a tela avisa antes. */
const MOTIVO_ENCERRADA = "Semana encerrada: vira histórico e não gera lista.";

type Selo = "novo" | "ajustado" | "confira" | "sem_mudanca" | "removido";

const ROTULO_SELO: Record<Selo, string> = {
  novo: "novo",
  ajustado: "ajustado",
  confira: "confira",
  sem_mudanca: "sem mudança",
  removido: "sai da lista",
};

const TOM_SELO: Record<Selo, string> = {
  novo: "bg-destaque-fundo text-destaque-hover",
  ajustado: "bg-receita-fundo text-receita-texto",
  confira: "bg-atencao-fundo text-atencao-texto",
  sem_mudanca: "bg-superficie-2 text-texto-apoio",
  removido: "bg-perigo-fundo text-perigo",
};

interface LinhaPrevia {
  chave: string;
  produto: string;
  quantidade: string;
  selo: Selo;
  nota: string | null;
}

/** As linhas da prévia numa lista só, na ordem: novos, ajustados, confira, sem mudança. */
function linhasDaPrevia(p: ListaCardapio): LinhaPrevia[] {
  return [
    ...p.criados.map((c, i) => ({
      chave: `n${i}`,
      produto: c.produto,
      quantidade: quantidadeDoItem({ quantidade: c.quantidade, unidade: c.unidade }) || "sem quantidade",
      selo: "novo" as const,
      nota: c.de.length > 0 ? `de ${c.de.join(", ")}` : null,
    })),
    ...p.ajustados.map((a, i) => ({
      chave: `a${i}`,
      produto: a.produto,
      quantidade: a.removido
        ? "sai da lista"
        : a.antes && a.depois
          ? `${quantidadeDoItem({ quantidade: a.antes, unidade: a.unidade })} → ${quantidadeDoItem({ quantidade: a.depois, unidade: a.unidade })}`
          : quantidadeDoItem({ quantidade: a.depois ?? a.pedido, unidade: a.unidade }) || "sem quantidade",
      selo: a.removido ? ("removido" as const) : ("ajustado" as const),
      nota: a.de.length > 0 ? `de ${a.de.join(", ")}` : null,
    })),
    ...p.confira.map((c, i) => ({
      chave: `c${i}`,
      produto: c.produto,
      quantidade: quantidadeDoItem({ quantidade: c.pedido, unidade: c.unidade }) || "sem quantidade",
      selo: "confira" as const,
      nota: c.texto,
    })),
    ...p.sem_mudanca.map((s, i) => ({
      chave: `s${i}`,
      produto: s.produto,
      quantidade: quantidadeDoItem({ quantidade: s.pedido, unidade: s.unidade }) || "sem quantidade",
      selo: "sem_mudanca" as const,
      nota: null,
    })),
  ];
}

function Contagem({ n, rotulo, tom }: { n: number; rotulo: string; tom?: "atencao" }) {
  return (
    <div
      className={cn(
        "rounded-interno flex flex-col gap-1 p-5",
        tom === "atencao" ? "bg-atencao-fundo-2 text-atencao-texto" : "bg-superficie-2",
      )}
    >
      <span className="text-valor-medio font-bold">{n}</span>
      <span className={cn("text-pequeno", tom === "atencao" ? "" : "text-texto-2")}>{rotulo}</span>
    </div>
  );
}

function Linha({ l }: { l: LinhaPrevia }) {
  return (
    <div className="linha-acima flex items-start justify-between gap-5 py-4">
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-corpo font-semibold">{l.produto}</span>
        {l.nota ? <span className="text-pequeno text-texto-2">{l.nota}</span> : null}
      </span>
      <span className="flex shrink-0 flex-col items-end gap-2">
        <span className="text-corpo font-[650]">{l.quantidade}</span>
        <span className={cn("text-selo rounded-selo px-3 py-px font-semibold", TOM_SELO[l.selo])}>
          {ROTULO_SELO[l.selo]}
        </span>
      </span>
    </div>
  );
}

/**
 * Mandar para a lista de compras (`CardapioSemanaCelular` e `CardapioDesktop`):
 * a prévia (GET, não grava) com as contagens de novos, ajustados e "confira",
 * e o botão que grava (POST). Semana encerrada: os botões ficam desabilitados
 * com o motivo à vista, sem esperar o 409.
 */
export function ListaPrevia({
  semanaId,
  encerrada,
  quem,
  variante,
}: {
  semanaId: number;
  encerrada: boolean;
  quem: string | null;
  /** `computador` mostra os primeiros itens na própria tela; `celular`, só as contagens. */
  variante: "celular" | "computador";
}) {
  const previa = useListaPrevia(semanaId, !encerrada);
  const gravar = useGravarLista(quem ?? "");
  const [aberto, setAberto] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const dados = previa.data;
  const linhas = dados ? linhasDaPrevia(dados) : [];
  const mudancas = dados ? dados.criados.length + dados.ajustados.length : 0;
  const semNada = dados !== undefined && linhas.length === 0;

  function mandar() {
    if (!quem) return;
    setErro(null);
    setResultado(null);
    gravar.mutate(semanaId, {
      onSuccess: (r) => {
        setAberto(false);
        setResultado(
          r.criados.length + r.ajustados.length === 0
            ? "A lista já estava em dia: nada mudou."
            : `Lista atualizada: ${r.criados.length} novos e ${r.ajustados.length} ajustados.`,
        );
      },
      onError: (e) =>
        setErro(
          e instanceof ApiError && e.status === 409
            ? MOTIVO_ENCERRADA
            : e instanceof ApiError
              ? e.detail
              : "Não foi possível mandar para a lista. Tente de novo.",
        ),
    });
  }

  const motivo = encerrada
    ? MOTIVO_ENCERRADA
    : !quem
      ? "Diga quem você é para mandar para a lista."
      : null;

  return (
    <section
      aria-label="Mandar para a lista de compras"
      className={cn(
        variante === "computador"
          ? "bg-superficie rounded-bloco flex flex-col gap-6 px-11 py-10"
          : "bg-superficie-2 rounded-interno flex flex-col gap-5 p-6",
      )}
    >
      <div className="flex flex-col gap-1">
        <h2 className={cn("font-forte m-0", variante === "computador" ? "text-bloco" : "text-corpo")}>
          Mandar para a lista de compras
        </h2>
        <span className="text-apoio text-texto-2">
          Prévia: nada muda na lista até você confirmar.
        </span>
      </div>

      {encerrada ? null : previa.isLoading ? (
        <p role="status" className="text-apoio text-texto-2 m-0">
          Calculando a prévia…
        </p>
      ) : previa.isError || !dados ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-apoio text-perigo m-0">
            {previa.error instanceof ApiError
              ? previa.error.detail
              : "Não foi possível calcular a prévia."}
          </p>
          <Button variant="secondary" onClick={() => void previa.refetch()}>
            Tentar de novo
          </Button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Contagem n={dados.criados.length} rotulo="itens novos" />
            <Contagem n={dados.ajustados.length} rotulo="já na lista, com quantidade ajustada" />
            <Contagem
              n={dados.confira.length}
              rotulo={'"confira": a despensa diz que tem'}
              tom="atencao"
            />
          </div>
          {dados.avisos.length > 0 ? (
            <ul className="text-pequeno text-atencao-texto bg-atencao-fundo-2 rounded-interno m-0 flex list-none flex-col gap-2 p-5">
              {dados.avisos.map((a, i) => (
                <li key={i}>
                  {a.produto ? <strong>{a.produto}: </strong> : null}
                  {a.texto}
                </li>
              ))}
            </ul>
          ) : null}
          {variante === "computador" && linhas.length > 0 ? (
            <div className="flex flex-col">
              {linhas.slice(0, 6).map((l) => (
                <Linha key={l.chave} l={l} />
              ))}
            </div>
          ) : null}
          {semNada ? (
            <p className="text-apoio text-texto-2 m-0">
              O cardápio desta semana não pede nada para a lista.
            </p>
          ) : null}
        </>
      )}

      {motivo ? (
        <p
          role={encerrada ? "status" : undefined}
          className={cn("text-apoio m-0", encerrada ? "text-atencao-texto font-semibold" : "text-texto-2")}
        >
          {motivo}
        </p>
      ) : null}
      {resultado ? (
        <p role="status" className="text-apoio text-receita-texto m-0">
          {resultado}{" "}
          <a href={href("compras")} className="font-semibold">
            Ver a lista
          </a>
        </p>
      ) : null}
      {erro && !aberto ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-4">
        {variante === "computador" ? (
          <>
            <Button
              disabled={encerrada || !quem || !dados || semNada || gravar.isPending}
              onClick={mandar}
            >
              {gravar.isPending ? "Mandando…" : "Mandar para a lista"}
            </Button>
            {linhas.length > 6 ? (
              <Button variant="secondary" onClick={() => setAberto(true)}>
                Ver os {linhas.length} itens
              </Button>
            ) : null}
          </>
        ) : (
          <Button
            className="h-24 w-full"
            disabled={encerrada || !dados}
            onClick={() => setAberto(true)}
          >
            Ver prévia e mandar
          </Button>
        )}
      </div>
      {mudancas === 0 && dados && !semNada && !encerrada ? (
        <span className="text-pequeno text-texto-2">
          Nada novo para a lista: o que o cardápio pede já está lá ou é só de conferir.
        </span>
      ) : null}

      <Dialogo aberto={aberto} onFechar={() => setAberto(false)} titulo="Prévia da lista">
        {aberto ? (
          <div className="flex flex-col gap-5">
            <p className="text-apoio text-texto-2 m-0 leading-normal">
              O que vai para a lista de compras. Os "confira" são produtos que a despensa diz que
              vocês têm: não entram na lista, só avisam.
            </p>
            <div className="flex flex-col">
              {linhas.length === 0 ? (
                <p className="text-apoio text-texto-2 m-0">Nada a mandar.</p>
              ) : (
                linhas.map((l) => <Linha key={l.chave} l={l} />)
              )}
            </div>
            {erro ? (
              <p role="alert" className="text-apoio text-perigo m-0">
                {erro}
              </p>
            ) : null}
            <Button disabled={encerrada || !quem || gravar.isPending || semNada} onClick={mandar}>
              {gravar.isPending ? "Mandando…" : "Mandar para a lista"}
            </Button>
          </div>
        ) : null}
      </Dialogo>
    </section>
  );
}
