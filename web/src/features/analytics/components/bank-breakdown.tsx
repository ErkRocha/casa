import type { ReactNode } from "react";

import { useFiltros } from "@/features/filters/filter-context";
import { TIPO_PAGAMENTO_LABEL } from "@/features/cadastros/types";
import { formatBRLTexto, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FormaNoBanco, GastoPorBanco, LinhaBanco } from "../types";

const COR_CARTAO = "var(--color-cat-2)";
const COR_CONTA = "var(--color-cat-5)";

/**
 * Onde o dinheiro foi gasto: por banco, com o cartão separado do que saiu
 * direto da conta (débito, Pix, boleto).
 *
 * Clicar numa forma filtra a tela inteira por ela. Clicar de novo tira o
 * filtro, e dá para somar várias. O painel em si ignora o filtro de forma,
 * senão as outras sumiriam no primeiro clique.
 *
 * O tracejado é o que ainda está na revisão das importações. Não entra no
 * total até ser aprovado, e costuma ser a diferença entre o painel e o app
 * do banco.
 */
export function BankBreakdown({
  data,
  onVerTransacoes,
  onRevisar,
}: {
  data: GastoPorBanco;
  onVerTransacoes: () => void;
  onRevisar: () => void;
}) {
  const { filtros, setFiltros, alternarFormaPagamento } = useFiltros();
  const selecionadas = new Set(filtros.formaPagamentoIds);
  const revisao = toNumero(data.revisao_valor);

  if (data.linhas.length === 0) {
    return <p className="text-body-sm text-text-tertiary py-8">Sem gasto no período.</p>;
  }

  const maior = Math.max(
    ...data.linhas.map((b) => toNumero(b.total) + toNumero(b.revisao_valor)),
  );

  const filtrarBanco = (banco: LinhaBanco, irParaTransacoes: boolean) => {
    const ids = banco.formas.map((f) => f.forma_pagamento_id);
    const jaFiltrado =
      ids.length === selecionadas.size && ids.every((id) => selecionadas.has(id));
    setFiltros({ formaPagamentoIds: jaFiltrado && !irParaTransacoes ? [] : ids });
    if (irParaTransacoes) onVerTransacoes();
  };

  return (
    <div className="flex flex-col gap-9">
      <dl className="flex flex-wrap gap-x-12 gap-y-5">
        <Placar rotulo="Total gasto" valor={data.total} />
        <Placar rotulo="No cartão de crédito" valor={data.cartao} cor={COR_CARTAO} />
        <Placar rotulo="Débito, Pix e boleto" valor={data.conta} cor={COR_CONTA} />
      </dl>

      {revisao > 0 ? (
        <div className="bg-alert-soft text-body-sm flex flex-wrap items-center gap-x-6 gap-y-3 rounded-md px-6 py-4">
          <span className="text-text-primary">
            Mais <strong className="tabular">{formatBRLTexto(data.revisao_valor)}</strong> em{" "}
            {data.revisao_quantidade}{" "}
            {data.revisao_quantidade === 1 ? "compra aguardando" : "compras aguardando"} revisão.
            Esse valor só entra no total depois de aprovado.
          </span>
          <button
            type="button"
            onClick={onRevisar}
            className="text-accent focus-visible:ring-accent cursor-pointer rounded-xs font-semibold outline-none hover:underline focus-visible:ring-1"
          >
            Revisar agora →
          </button>
        </div>
      ) : null}

      <ul className="flex flex-col gap-10">
        {data.linhas.map((banco) => (
          <li key={banco.conta_id ?? "sem"} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
              <span className="text-body text-text-primary font-semibold" title={banco.nome}>
                {nomeCurto(banco.nome)}
              </span>
              <span className="tabular text-body text-text-primary font-bold">
                {formatBRLTexto(banco.total)}
              </span>
              <span className="text-caption text-text-tertiary tabular">
                {Math.round(toNumero(banco.percentual))}% do total
              </span>
              {banco.formas.length > 0 ? (
                <span className="ml-auto flex gap-5">
                  <LinkAcao onClick={() => filtrarBanco(banco, false)}>Filtrar banco</LinkAcao>
                  <LinkAcao onClick={() => filtrarBanco(banco, true)}>Ver lançamentos</LinkAcao>
                </span>
              ) : null}
            </div>

            <BarraDoBanco banco={banco} maior={maior} />

            {banco.formas.length > 0 ? (
              <div className="flex flex-wrap gap-3">
                {banco.formas.map((forma, _, todas) => (
                  <ChipForma
                    key={forma.forma_pagamento_id}
                    forma={forma}
                    rotulo={rotuloUnico(forma, todas)}
                    ativo={selecionadas.has(forma.forma_pagamento_id)}
                    onClick={() => alternarFormaPagamento(forma.forma_pagamento_id)}
                  />
                ))}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Placar({ rotulo, valor, cor }: { rotulo: string; valor: string; cor?: string }) {
  return (
    <div className="flex flex-col gap-2">
      <dt className="text-label text-text-secondary tracking-label flex items-center gap-3 font-semibold uppercase">
        {cor ? <span className="size-4 rounded-xs" style={{ background: cor }} /> : null}
        {rotulo}
      </dt>
      <dd className="tabular text-display text-text-primary font-bold">{formatBRLTexto(valor)}</dd>
    </div>
  );
}

/**
 * Cartão e conta lado a lado, na escala do maior banco: a barra mais longa
 * é o banco onde mais se gastou. O tracejado no fim é a revisão.
 */
function BarraDoBanco({ banco, maior }: { banco: LinhaBanco; maior: number }) {
  const cartao = toNumero(banco.cartao);
  const conta = toNumero(banco.conta);
  const revisao = toNumero(banco.revisao_valor);
  const largura = (v: number) => (maior > 0 ? `${(v / maior) * 100}%` : "0%");

  const descricao = [
    cartao > 0 ? `cartão ${formatBRLTexto(banco.cartao)}` : null,
    conta > 0 ? `débito, Pix e boleto ${formatBRLTexto(banco.conta)}` : null,
    revisao > 0 ? `mais ${formatBRLTexto(banco.revisao_valor)} na revisão` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="bg-surface-sunken flex h-8 gap-1 overflow-hidden rounded-xs"
      role="img"
      aria-label={`${nomeCurto(banco.nome)}: ${descricao}`}
    >
      {cartao > 0 ? (
        <div
          title={`Cartão de crédito — ${formatBRLTexto(banco.cartao)}`}
          style={{ width: largura(cartao), background: COR_CARTAO }}
        />
      ) : null}
      {conta > 0 ? (
        <div
          title={`Débito, Pix e boleto — ${formatBRLTexto(banco.conta)}`}
          style={{ width: largura(conta), background: COR_CONTA }}
        />
      ) : null}
      {revisao > 0 ? (
        <div
          title={`Aguardando revisão — ${formatBRLTexto(banco.revisao_valor)}`}
          className="border-alert rounded-xs border border-dashed"
          style={{ width: largura(revisao) }}
        />
      ) : null}
    </div>
  );
}

function ChipForma({
  forma,
  rotulo,
  ativo,
  onClick,
}: {
  forma: FormaNoBanco;
  rotulo: string;
  ativo: boolean;
  onClick: () => void;
}) {
  const revisao = toNumero(forma.revisao_valor);
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      title={
        ativo
          ? `Tirar o filtro de ${forma.apelido}`
          : `Filtrar a tela por ${forma.apelido} (${forma.quantidade} lançamentos)`
      }
      className={cn(
        "text-caption-lg inline-flex cursor-pointer items-center gap-3 rounded-md px-4 py-2",
        "focus-visible:ring-accent outline-none focus-visible:ring-1",
        ativo
          ? "bg-text-primary text-surface"
          : "bg-surface-sunken text-text-secondary hover:bg-surface",
      )}
    >
      <span
        className="size-3 shrink-0 rounded-xs"
        style={{ background: forma.cartao ? COR_CARTAO : COR_CONTA }}
      />
      <span className="font-medium">{rotulo}</span>
      <span className={cn("tabular", ativo ? "opacity-80" : "text-text-primary")}>
        {formatBRLTexto(forma.valor)}
      </span>
      {revisao > 0 ? (
        <span className={cn("tabular", ativo ? "opacity-80" : "text-alert")}>
          +{formatBRLTexto(forma.revisao_valor)} na revisão
        </span>
      ) : null}
    </button>
  );
}

function LinkAcao({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-caption text-text-secondary hover:text-text-primary focus-visible:ring-accent cursor-pointer rounded-xs outline-none hover:underline focus-visible:ring-1"
    >
      {children}
    </button>
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
