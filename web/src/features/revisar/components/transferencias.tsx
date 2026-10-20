import { useState, type ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { Button, SelectSobreposto } from "@/components/ui/controls";
import type { Conta } from "@/features/cadastros/types";
import { diaDeMes, reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import { nomeDoCartao } from "../textos";
import type { ConfirmarTransferencia, TransferenciaRevisar } from "../types";

type Escolhas = Record<number, { origem?: number; destino?: number }>;

/**
 * Transferências entre as contas (`RevisarDesktop`, `RevisarCelular`): de
 * onde saiu, para onde foi, confirmar, "não é transferência" e "Confirmar as
 * N". O que a API não sabe dizer (a conta da outra ponta) vira um seletor.
 */
export function Transferencias({
  lista,
  contas,
  ocupado,
  onConfirmar,
  onNaoE,
}: {
  lista: TransferenciaRevisar[];
  contas: Conta[];
  ocupado: boolean;
  onConfirmar: (pedidos: ConfirmarTransferencia[]) => void;
  onNaoE: (id: number, tipo?: "despesa" | "receita") => void;
}) {
  const [escolhas, setEscolhas] = useState<Escolhas>({});
  const [perguntando, setPerguntando] = useState<Set<number>>(new Set());

  function escolher(id: number, lado: "origem" | "destino", conta: number) {
    setEscolhas((atual) => ({ ...atual, [id]: { ...atual[id], [lado]: conta } }));
  }

  function contasDe(t: TransferenciaRevisar) {
    const escolha = escolhas[t.item.id] ?? {};
    return {
      origem: escolha.origem ?? t.origem?.id,
      destino: escolha.destino ?? t.destino?.id,
      escolha,
    };
  }

  function pronta(t: TransferenciaRevisar): boolean {
    if (t.ao_confirmar === "descartar" && !escolhas[t.item.id]) return true;
    const { origem, destino } = contasDe(t);
    return origem !== undefined && destino !== undefined && origem !== destino;
  }

  // Só as contas escolhidas vão no pedido; o resto a API sugere de novo.
  function pedido(t: TransferenciaRevisar): ConfirmarTransferencia {
    const { escolha } = contasDe(t);
    return {
      item_id: t.item.id,
      conta_origem_id: escolha.origem ?? null,
      conta_destino_id: escolha.destino ?? null,
    };
  }

  const prontas = lista.filter(pronta);
  const nomeDaConta = new Map(contas.map((c) => [c.id, c.nome]));

  function lado(t: TransferenciaRevisar, qual: "origem" | "destino"): ReactNode {
    const { origem, destino } = contasDe(t);
    if (qual === "destino" && t.fatura_de) {
      const ladoDoCartao =
        t.tipo === "pagamento_fatura_cartao" && t.ao_confirmar === "descartar"
          ? " (mesmo pagamento, lado do cartão)"
          : "";
      const conta =
        t.ao_confirmar === "transferencia" && t.destino ? `, conta ${t.destino.nome}` : "";
      return `Fatura ${nomeDoCartao(t.fatura_de)}${conta}${ladoDoCartao}`;
    }
    const sugerida = qual === "origem" ? t.origem : t.destino;
    if (sugerida && !escolhas[t.item.id]?.[qual]) return sugerida.nome;
    if (t.ao_confirmar === "descartar") return "—";
    const atual = qual === "origem" ? origem : destino;
    const outra = qual === "origem" ? destino : origem;
    return (
      <SelectSobreposto
        rotulo={`${qual === "origem" ? "De onde saiu" : "Para onde foi"}: ${t.item.descricao}`}
        mostrar={atual !== undefined ? (nomeDaConta.get(atual) ?? `Conta ${atual}`) : "escolher conta"}
        value={atual ?? ""}
        onChange={(e) => escolher(t.item.id, qual, Number(e.target.value))}
        className="text-apoio bg-destaque-fundo text-destaque-hover rounded-campo px-4 py-1 align-middle font-semibold"
      >
        <option value="" disabled>
          Escolha a conta
        </option>
        {contas
          .filter((c) => c.id !== outra)
          .map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
      </SelectSobreposto>
    );
  }

  function acoes(t: TransferenciaRevisar, curto: boolean) {
    const id = t.item.id;
    const descarta = t.tipo === "pagamento_fatura_cartao" && t.ao_confirmar === "descartar";
    const classe = cn(curto && "min-h-22");
    if (perguntando.has(id)) {
      return (
        <>
          <Button variant="secondary" disabled={ocupado} onClick={() => onNaoE(id, "despesa")} className={classe}>
            É despesa
          </Button>
          <Button variant="secondary" disabled={ocupado} onClick={() => onNaoE(id, "receita")} className={classe}>
            É receita
          </Button>
        </>
      );
    }
    return (
      <>
        <Button
          disabled={ocupado || !pronta(t)}
          onClick={() => onConfirmar([pedido(t)])}
          className={classe}
        >
          {descarta ? "Descartar" : "Confirmar"}
        </Button>
        <Button
          variant="secondary"
          disabled={ocupado}
          aria-label="Não é transferência"
          onClick={() => {
            if (t.direcao) onNaoE(id);
            else setPerguntando((atual) => new Set(atual).add(id));
          }}
          className={classe}
        >
          {curto ? "Não é transferência" : "Não é"}
        </Button>
      </>
    );
  }

  const confirmarTodas =
    prontas.length > 0 ? (
      <Button
        variant="ghost"
        disabled={ocupado}
        onClick={() => onConfirmar(prontas.map(pedido))}
        className="bg-destaque-fundo text-destaque-hover hover:text-destaque-hover font-forte rounded-botao shrink-0"
      >
        Confirmar {prontas.length === 1 ? "a única" : `as ${prontas.length}`}
      </Button>
    ) : null;
  const faltam = lista.length - prontas.length;

  return (
    <Card className="flex flex-col gap-2 p-8 md:gap-3 md:px-11 md:py-10">
      <div className="flex items-center justify-between gap-5 pb-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-enfase md:text-bloco font-forte m-0">
            Transferências entre suas contas
          </h2>
          <span className="text-apoio text-texto-2 hidden md:inline">
            Não contam como gasto. Confirme de onde saiu e para onde foi.
          </span>
        </div>
        {confirmarTodas}
      </div>
      {faltam > 0 && prontas.length > 0 ? (
        <p className="text-pequeno text-texto-2 m-0 pb-2">
          {faltam === 1
            ? "Uma precisa que você escolha a conta antes."
            : `${faltam} precisam que você escolha a conta antes.`}
        </p>
      ) : null}

      <ul className="m-0 flex list-none flex-col p-0">
        {lista.map((t) => (
          <li key={t.item.id} className="linha-acima">
            {/* Celular. */}
            <div className="flex flex-col gap-5 py-6 md:hidden">
              <div className="flex items-baseline justify-between gap-5">
                <span className="text-corpo font-semibold">{t.item.descricao}</span>
                <span className="text-enfase font-bold whitespace-nowrap">{reais(t.item.valor)}</span>
              </div>
              <span className="text-pequeno text-texto-2 leading-normal">
                {t.item.data ? `${diaDeMes(t.item.data)}. ` : ""}Saiu de {lado(t, "origem")}, foi para{" "}
                {lado(t, "destino")}.
              </span>
              <div className="grid grid-cols-2 gap-4">{acoes(t, true)}</div>
            </div>

            {/* Computador. */}
            <div className="hidden grid-cols-[minmax(0,1.4fr)_minmax(0,1.6fr)_120px_220px] items-center gap-7 py-7 md:grid">
              <span className="flex min-w-0 flex-col gap-1">
                <span className="text-corpo font-semibold">{t.item.descricao}</span>
                <span className="text-pequeno text-texto-2">
                  {t.item.data ? diaDeMes(t.item.data) : "sem data"}
                </span>
              </span>
              <span className="text-apoio flex min-w-0 flex-col gap-1">
                <span>
                  <span className="text-texto-2">Saiu de</span> {lado(t, "origem")}
                </span>
                <span>
                  <span className="text-texto-2">Foi para</span> {lado(t, "destino")}
                </span>
              </span>
              <span className="text-enfase text-right font-bold">{reais(t.item.valor)}</span>
              <span className="flex justify-end gap-4">{acoes(t, false)}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
