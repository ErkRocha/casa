import { CabecalhoBloco, Card } from "@/components/ui/card";
import { reais, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { dataCurta, diaDoIso, nomeCurtoCartao } from "../textos";
import type { FaturaAberta, Inicio } from "../types";

const LARGURA = 120;
const ALTURA = 28;

/** Mini-área em degraus da evolução da fatura, de zero ao máximo (sem eixos). */
function Evolucao({ fatura }: { fatura: FaturaAberta }) {
  const pontos = fatura.evolucao;
  const max = Math.max(...pontos.map((p) => toNumero(p.acumulado)), 0);
  if (pontos.length < 2 || max <= 0) {
    return (
      <svg width="100%" height={ALTURA} aria-hidden="true" className="block">
        <line
          x1="0"
          y1={ALTURA - 1}
          x2="100%"
          y2={ALTURA - 1}
          className="stroke-trilho"
          strokeWidth="2"
        />
      </svg>
    );
  }
  const x = (n: number) => (n / (pontos.length - 1)) * LARGURA;
  const y = (v: number) => ALTURA - 2 - (v / max) * (ALTURA - 4);
  let anterior = 0;
  const trajeto = pontos
    .map((p, n) => {
      const valor = toNumero(p.acumulado);
      const trecho = `${x(n).toFixed(1)},${y(anterior).toFixed(1)} ${x(n).toFixed(1)},${y(valor).toFixed(1)}`;
      anterior = valor;
      return trecho;
    })
    .join(" ");
  const linha = `0,${y(0)} ${trajeto}`;
  return (
    <svg
      width="100%"
      height={ALTURA}
      viewBox={`0 0 ${LARGURA} ${ALTURA}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className="block overflow-visible"
    >
      <polyline
        points={`${linha} ${LARGURA},${y(0)}`}
        className="fill-destaque-fundo"
        stroke="none"
      />
      <polyline
        points={linha}
        fill="none"
        className="stroke-destaque"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Faturas abertas hoje, uma por cartão (D-27). Só no mês corrente. */
export function FaturasAbertas({ i, className }: { i: Inicio; className?: string }) {
  if (i.situacao !== "corrente" || i.faturas_abertas.length === 0) return null;
  return (
    <Card className={cn("flex flex-col gap-5 px-9 py-9 md:px-10", className)}>
      <CabecalhoBloco titulo="Faturas abertas" />
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {i.faturas_abertas.map((f) => (
          <li
            key={f.forma_pagamento_id}
            className="bg-superficie-2 rounded-interno flex flex-col gap-2 p-6"
          >
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-apoio font-forte">{nomeCurtoCartao(f.cartao)}</span>
              <span className="text-apoio font-forte">
                {toNumero(f.valor) > 0 ? reais(f.valor) : "sem compras ainda"}
              </span>
            </div>
            <span className="text-pequeno text-texto-2">
              {`desde ${dataCurta(f.desde)} · fecha dia ${diaDoIso(f.fecha)}`}
              {f.vence ? `, vence dia ${diaDoIso(f.vence)}` : ""}
            </span>
            <Evolucao fatura={f} />
          </li>
        ))}
      </ul>
      <p className="text-pequeno text-texto-2 m-0">Compras pela data, desde o último fechamento.</p>
    </Card>
  );
}
