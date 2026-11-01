import { CabecalhoBloco, Card } from "@/components/ui/card";
import { TIPO_PAGAMENTO_LABEL } from "@/features/cadastros/types";
import type { BaldePessoa } from "@/features/filters/types";
import { inteiro, reais, toNumero } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { usePorBanco } from "../queries";
import type { FormaNoBanco, GastoPorBanco, LinhaBanco } from "../types";

const COR_CARTAO = "bg-cat-2";
const COR_CONTA = "bg-cat-5";

/**
 * "Por banco": onde o dinheiro foi gasto no período, com o cartão de
 * crédito separado do que saiu direto da conta (débito, Pix, boleto).
 *
 * O tracejado é o que ainda está na revisão das importações. Ele não entra
 * no total até ser aprovado, e costuma ser a diferença entre o painel e o
 * app do banco.
 */
export function PorBanco({
  inicio,
  fim,
  pessoa,
  className,
}: {
  inicio: string;
  fim: string;
  pessoa: BaldePessoa | null;
  className?: string;
}) {
  const consulta = usePorBanco(inicio, fim, pessoa);
  return (
    <Card className={cn("flex flex-col gap-7 px-8 py-9 md:px-11 md:py-10", className)}>
      <CabecalhoBloco titulo="Por banco" direita="no período" />
      {consulta.isLoading ? (
        <div className="bg-superficie-2 h-40 animate-pulse rounded-md" aria-busy />
      ) : consulta.isError || !consulta.data ? (
        <p className="text-apoio text-texto-2 m-0">Não foi possível carregar o gasto por banco.</p>
      ) : (
        <Conteudo d={consulta.data} />
      )}
    </Card>
  );
}

function Conteudo({ d }: { d: GastoPorBanco }) {
  if (d.linhas.length === 0) {
    return <p className="text-apoio text-texto-2 m-0">Nenhuma despesa no período.</p>;
  }
  const maior = Math.max(...d.linhas.map((b) => toNumero(b.total) + toNumero(b.revisao_valor)));

  return (
    <>
      <dl className="m-0 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Numero rotulo="Total gasto" valor={d.total} />
        <Numero rotulo="No cartão de crédito" valor={d.cartao} cor={COR_CARTAO} />
        <Numero rotulo="Débito, Pix e boleto" valor={d.conta} cor={COR_CONTA} />
      </dl>

      {toNumero(d.revisao_valor) > 0 ? (
        <p className="bg-atencao-fundo text-atencao-texto text-apoio rounded-interno m-0 px-6 py-5">
          Mais <strong>{reais(d.revisao_valor)}</strong> em {d.revisao_quantidade}{" "}
          {d.revisao_quantidade === 1 ? "compra aguardando" : "compras aguardando"} revisão. Esse
          valor só entra no total depois de aprovado.{" "}
          <a href={href("revisar")} className="font-semibold">
            Revisar agora
          </a>
        </p>
      ) : null}

      <ul className="m-0 flex list-none flex-col gap-8 p-0">
        {d.linhas.map((banco) => (
          <Banco key={banco.conta_id ?? "sem"} banco={banco} maior={maior} />
        ))}
      </ul>
    </>
  );
}

function Numero({ rotulo, valor, cor }: { rotulo: string; valor: string; cor?: string }) {
  return (
    <div className="bg-superficie-2 rounded-interno flex flex-col gap-1 px-6 py-5">
      <dt className="text-selo text-texto-2 flex items-center gap-3">
        {cor ? <span aria-hidden className={cn("inline-block size-4 rounded-[3px]", cor)} /> : null}
        {rotulo}
      </dt>
      <dd className="text-bloco-celular font-forte m-0">{reais(valor)}</dd>
    </div>
  );
}

function Banco({ banco, maior }: { banco: LinhaBanco; maior: number }) {
  const cartao = toNumero(banco.cartao);
  const conta = toNumero(banco.conta);
  const revisao = toNumero(banco.revisao_valor);
  const largura = (v: number) => `${maior > 0 ? (v / maior) * 100 : 0}%`;
  const nome = nomeCurto(banco.nome);
  const descricao = [
    cartao > 0 ? `cartão ${reais(banco.cartao)}` : null,
    conta > 0 ? `débito, Pix e boleto ${reais(banco.conta)}` : null,
    revisao > 0 ? `mais ${reais(banco.revisao_valor)} na revisão` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <li className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <span className="text-corpo font-semibold" title={banco.nome}>
          {nome}
        </span>
        <span className="text-corpo">
          <span className="font-forte">{reais(banco.total)}</span>
          <span className="text-texto-2"> · {inteiro(banco.percentual)}%</span>
        </span>
      </div>

      <div
        role="img"
        aria-label={`${nome}: ${descricao}`}
        className="bg-linha-suave flex h-5 gap-1 overflow-hidden rounded-full"
      >
        {cartao > 0 ? <div className={COR_CARTAO} style={{ width: largura(cartao) }} /> : null}
        {conta > 0 ? <div className={COR_CONTA} style={{ width: largura(conta) }} /> : null}
        {revisao > 0 ? (
          <div
            className="border-atencao-borda rounded-full border border-dashed"
            style={{ width: largura(revisao) }}
          />
        ) : null}
      </div>

      {banco.formas.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {banco.formas.map((forma, _, todas) => (
            <li
              key={forma.forma_pagamento_id}
              className="text-apoio text-texto-apoio flex flex-wrap justify-between gap-x-4"
            >
              <span className="flex items-center gap-3">
                <span
                  aria-hidden
                  className={cn(
                    "inline-block size-3 rounded-[3px]",
                    forma.cartao ? COR_CARTAO : COR_CONTA,
                  )}
                />
                {rotuloUnico(forma, todas)}
                <span className="text-texto-2">
                  ({forma.quantidade} {forma.quantidade === 1 ? "lançamento" : "lançamentos"})
                </span>
              </span>
              <span>
                {reais(forma.valor)}
                {toNumero(forma.revisao_valor) > 0 ? (
                  <span className="text-atencao-texto">
                    {" "}
                    + {reais(forma.revisao_valor)} na revisão
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** "Nubank (conta pré-paga)" vira "Nubank"; o nome inteiro fica no title. */
function nomeCurto(nome: string): string {
  return nome.replace(/\s*\(.*\)\s*$/, "") || nome;
}

/** O rótulo curto, ou o apelido quando o curto se repete no banco (Pix de cada um). */
function rotuloUnico(forma: FormaNoBanco, todas: FormaNoBanco[]): string {
  const rotulo = rotuloDaForma(forma);
  const repete = todas.filter((f) => rotuloDaForma(f) === rotulo).length > 1;
  return repete ? forma.apelido : rotulo;
}

/** "Cartão •••• 7704", "Pix", "Débito": o banco já está no título da linha. */
function rotuloDaForma(forma: FormaNoBanco): string {
  if (forma.tipo === "credito") {
    const final = /(\d{4})\s*$/.exec(forma.apelido)?.[1];
    return final ? `Cartão •••• ${final}` : "Cartão de crédito";
  }
  return TIPO_PAGAMENTO_LABEL[forma.tipo];
}
