import { useState } from "react";
import type { KeyboardEvent } from "react";

import { reais, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { dataCurta, nomeCurtoCartao } from "../textos";
import type { DiaJanela, Dinheiro, Janela } from "../types";

/**
 * "Últimos 30 dias" (D-28; `InicioDesktop` / `InicioCelular`).
 *
 * Barras diárias empilhadas: Pix/débito/boleto embaixo, cartão lançado e cartão
 * pendente (tom mais claro) por cima. O pagamento de fatura é uma marca no dia
 * em que saiu da conta, nunca uma barra: o gasto já está nas compras. Depois de
 * hoje, a faixa "a pagar" mostra o vencimento de cada fatura. Os valores viram
 * número só aqui, para virar coordenada no SVG.
 */

const GEOMETRIA = {
  computador: { largura: 700, plotAlt: 170, esq: 58, fonte: 12, linha: 24 },
  celular: { largura: 354, plotAlt: 130, esq: 46, fonte: 11, linha: 22 },
} as const;

export type VarianteGrafico = keyof typeof GEOMETRIA;

/** Soma de dinheiro em centavos inteiros, só para texto (nunca float acumulado). */
function somar(...valores: Dinheiro[]): Dinheiro {
  const centavos = valores.reduce((s, v) => s + Math.round(toNumero(v) * 100), 0);
  return (centavos / 100).toFixed(2);
}

/** Eixo vertical: passo "redondo" (1, 2, 2,5, 5 × 10^k) com no máximo 4 faixas. */
function passoDoEixo(maximo: number): number {
  if (maximo <= 0) return 1;
  const base = 10 ** Math.floor(Math.log10(maximo / 4));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (maximo / (m * base) <= 4) return m * base;
  }
  return 10 * base;
}

/** "R$ 500", "R$ 1,5 mil". */
function rotuloEixo(valor: number): string {
  if (valor < 1000) return `R$ ${valor}`;
  const mil = valor / 1000;
  return `R$ ${Number.isInteger(mil) ? mil : mil.toFixed(1).replace(".", ",")} mil`;
}

interface Marca {
  chave: string;
  tipo: "pagamento" | "vencimento";
  cx: number;
  texto: string;
}

/** Total e a divisão entre cartão e Pix/débito/boleto, acima do gráfico. */
export function ResumoJanela({
  janela,
  comTitulo = true,
  className,
}: {
  janela: Janela;
  comTitulo?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {comTitulo ? <span className="text-apoio text-texto-2">Últimos 30 dias</span> : null}
      <span className="text-valor font-forte">{reais(janela.total)}</span>
      <span className="text-apoio text-texto-2">
        cartão {reais(janela.cartao)} · Pix, débito e boleto {reais(janela.conta)}
      </span>
      {toNumero(janela.cartao_pendente) > 0 ? (
        <span className="text-pequeno text-texto-2">
          {reais(janela.cartao_pendente)} do cartão ainda pendente no banco
        </span>
      ) : null}
      <span className="text-pequeno text-texto-2">
        de {dataCurta(janela.inicio)} a {dataCurta(janela.hoje)}
      </span>
    </div>
  );
}

function Legenda() {
  const item = "flex items-center gap-3";
  return (
    <ul className="text-pequeno text-texto-2 m-0 flex list-none flex-wrap gap-x-6 gap-y-2 p-0">
      <li className={item}>
        <span aria-hidden className="bg-destaque inline-block size-5 rounded-[3px]" />
        cartão
      </li>
      <li className={item}>
        <span aria-hidden className="bg-destaque-parcial inline-block size-5 rounded-[3px]" />
        cartão pendente
      </li>
      <li className={item}>
        <span aria-hidden className="bg-guia inline-block size-5 rounded-[3px]" />
        Pix, débito e boleto
      </li>
      <li className={item}>
        <span aria-hidden className="bg-texto inline-block size-4 rotate-45" />
        pagamento de fatura
      </li>
      <li className={item}>
        <span
          aria-hidden
          className="bg-atencao-fundo-2 border-atencao-borda inline-block h-5 w-6 rounded-[3px] border border-dashed"
        />
        a pagar
      </li>
    </ul>
  );
}

export function Grafico30Dias({
  janela,
  variante,
}: {
  janela: Janela;
  variante: VarianteGrafico;
}) {
  const g = GEOMETRIA[variante];
  const dias = janela.dias;
  const n = dias.length;
  const indiceHoje = Math.max(
    0,
    dias.findIndex((d) => d.data === janela.hoje),
  );
  const [escolhido, setEscolhido] = useState<number | null>(null);
  const selecionado = Math.min(escolhido ?? indiceHoje, Math.max(n - 1, 0));

  const larguraPlot = g.largura - g.esq;
  const faixa = larguraPlot / Math.max(n, 1);
  const xDia = (i: number) => g.esq + i * faixa;
  const centro = (i: number) => xDia(i) + faixa / 2;
  const indiceDe = (data: string) => dias.findIndex((d) => d.data === data);

  // Marcas (pagamentos e vencimentos): rótulos distribuídos em linhas para não se sobrepor.
  const marcas: Marca[] = [
    ...janela.pagamentos.flatMap((p, k) => {
      const i = indiceDe(p.data);
      if (i < 0) return [];
      const valor = reais(p.valor, { centavos: false });
      const nome = variante === "computador" && p.cartao ? `${nomeCurtoCartao(p.cartao)} ` : "";
      return [{ chave: `p${k}`, tipo: "pagamento" as const, cx: centro(i), texto: `${nome}${valor}` }];
    }),
    ...janela.vencimentos.flatMap((v, k) => {
      const i = indiceDe(v.data);
      if (i < 0) return [];
      const valor = reais(somar(v.valor, v.pendente), { centavos: false });
      return [
        {
          chave: `v${k}`,
          tipo: "vencimento" as const,
          cx: centro(i),
          texto: `${nomeCurtoCartao(v.cartao)} ${valor}`,
        },
      ];
    }),
  ].sort((a, b) => a.cx - b.cx);

  const fonteMarca = g.fonte - 1;
  const linhasOcupadas: Array<Array<[number, number]>> = [];
  const posicionadas = marcas.map((m) => {
    const largura = m.texto.length * fonteMarca * 0.56;
    const x1 = Math.min(Math.max(m.cx - largura / 2, g.esq), g.largura - largura);
    const x2 = x1 + largura;
    let linha = linhasOcupadas.findIndex((l) => l.every(([a, b]) => x2 + 6 < a || x1 - 6 > b));
    if (linha < 0) {
      linha = linhasOcupadas.length < 3 ? linhasOcupadas.length : 2;
    }
    (linhasOcupadas[linha] ??= []).push([x1, x2]);
    return { ...m, x1, linha };
  });
  const nLinhas = linhasOcupadas.length;

  const topoMarcas = 4;
  const topo = topoMarcas + nLinhas * g.linha + (nLinhas ? 4 : 8);
  const base = topo + g.plotAlt;
  const eixo = base + 16;
  const altura = eixo + 6;

  const maximo = Math.max(0, ...dias.map((d) => toNumero(d.total)));
  const passo = passoDoEixo(maximo);
  const teto = Math.max(Math.ceil(maximo / passo) * passo, passo);
  const y = (v: number) => base - (v / teto) * g.plotAlt;
  const grades: number[] = [];
  for (let v = 0; v <= teto + 1e-9; v += passo) grades.push(v);

  const larguraBarra = Math.max(Math.min(faixa * 0.68, 22), 2);
  const temFaixa = indiceHoje < n - 1;
  const xFaixa = xDia(indiceHoje + 1);

  // Rótulos do eixo: de 7 em 7 dias a partir de hoje, para os dois lados.
  const rotulosX = dias
    .map((d, i) => ({ d, i }))
    .filter(({ i }) => (i - indiceHoje) % 7 === 0 && i - indiceHoje <= 14)
    .map(({ d, i }) => ({ i, texto: i === indiceHoje ? "Hoje" : dataCurta(d.data) }));

  const dia = dias[selecionado];

  const mover = (e: KeyboardEvent<HTMLDivElement>) => {
    const passos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1 };
    let proximo: number | null = null;
    if (e.key in passos) proximo = selecionado + (passos[e.key] ?? 0);
    else if (e.key === "Home") proximo = 0;
    else if (e.key === "End") proximo = n - 1;
    if (proximo === null) return;
    e.preventDefault();
    setEscolhido(Math.min(Math.max(proximo, 0), n - 1));
  };

  if (n === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      <div
        role="group"
        tabIndex={0}
        aria-label="Gráfico dos últimos 30 dias. Use as setas para escolher o dia."
        onKeyDown={mover}
        className="focus-visible:outline-destaque rounded-interno outline-offset-4 focus-visible:outline-2"
      >
        <svg
          width="100%"
          viewBox={`0 0 ${g.largura} ${altura}`}
          aria-hidden="true"
          className="block touch-manipulation select-none"
        >
          {temFaixa ? (
            <>
              <rect
                x={xFaixa}
                y={topoMarcas}
                width={g.largura - xFaixa}
                height={base - topoMarcas}
                rx="6"
                className="fill-atencao-fundo-2 stroke-atencao-borda-2"
                strokeWidth="1"
                strokeDasharray="4 3"
              />
              {g.largura - xFaixa > 54 ? (
                <text
                  x={xFaixa + 6}
                  y={base - 6}
                  fontSize={g.fonte - 1}
                  className="fill-atencao-texto"
                >
                  a pagar
                </text>
              ) : null}
            </>
          ) : null}

          {grades.map((v) => (
            <g key={v}>
              <line
                x1={g.esq}
                y1={y(v)}
                x2={g.largura}
                y2={y(v)}
                className={v === 0 ? "stroke-linha" : "stroke-linha-suave"}
                strokeWidth="1"
              />
              <text
                x={g.esq - 6}
                y={y(v) + 4}
                textAnchor="end"
                fontSize={g.fonte - 1}
                className="fill-texto-2"
              >
                {rotuloEixo(v)}
              </text>
            </g>
          ))}

          <rect
            x={xDia(selecionado)}
            y={topoMarcas}
            width={faixa}
            height={base - topoMarcas}
            className="fill-superficie-2"
            opacity={dia?.a_pagar ? 0.6 : 1}
          />

          {dias.map((d, i) => {
            const conta = toNumero(d.conta);
            const cartao = toNumero(d.cartao);
            const pendente = toNumero(d.cartao_pendente);
            const bx = centro(i) - larguraBarra / 2;
            return (
              <g key={d.data}>
                {conta > 0 ? (
                  <rect
                    x={bx}
                    y={y(conta)}
                    width={larguraBarra}
                    height={base - y(conta)}
                    className="fill-guia"
                  />
                ) : null}
                {cartao > 0 ? (
                  <rect
                    x={bx}
                    y={y(conta + cartao)}
                    width={larguraBarra}
                    height={y(conta) - y(conta + cartao)}
                    className="fill-destaque"
                  />
                ) : null}
                {pendente > 0 ? (
                  <rect
                    x={bx}
                    y={y(conta + cartao + pendente)}
                    width={larguraBarra}
                    height={y(conta + cartao) - y(conta + cartao + pendente)}
                    className="fill-destaque-parcial"
                  />
                ) : null}
              </g>
            );
          })}

          {posicionadas.map((m) => {
            const topoLinha = topoMarcas + m.linha * g.linha;
            const cy = topoLinha + g.fonte + 6;
            const pagamento = m.tipo === "pagamento";
            return (
              <g key={m.chave}>
                <line
                  x1={m.cx}
                  y1={cy}
                  x2={m.cx}
                  y2={base}
                  className={pagamento ? "stroke-texto-2" : "stroke-atencao-selo"}
                  strokeWidth="1"
                  strokeDasharray={pagamento ? undefined : "3 3"}
                />
                <path
                  d={`M${m.cx} ${cy - 5} L${m.cx + 5} ${cy} L${m.cx} ${cy + 5} L${m.cx - 5} ${cy} Z`}
                  className={
                    pagamento
                      ? "fill-texto stroke-superficie"
                      : "fill-atencao-fundo stroke-atencao-selo"
                  }
                  strokeWidth="1.5"
                />
                <text
                  x={m.x1}
                  y={topoLinha + g.fonte - 2}
                  fontSize={fonteMarca}
                  fontWeight={600}
                  className={cn(
                    "stroke-superficie",
                    pagamento ? "fill-texto" : "fill-atencao-texto",
                  )}
                  strokeWidth="3"
                  strokeLinejoin="round"
                  style={{ paintOrder: "stroke" }}
                >
                  {m.texto}
                </text>
              </g>
            );
          })}

          {rotulosX.map(({ i, texto }) => (
            <text
              key={i}
              x={centro(i)}
              y={eixo}
              textAnchor="middle"
              fontSize={g.fonte - 1}
              fontWeight={i === indiceHoje ? 650 : 400}
              className={i === indiceHoje ? "fill-texto" : "fill-texto-2"}
            >
              {texto}
            </text>
          ))}

          {dias.map((d, i) => (
            <rect
              key={d.data}
              x={xDia(i)}
              y={topoMarcas}
              width={faixa}
              height={eixo - topoMarcas}
              fill="transparent"
              className="cursor-pointer"
              onMouseEnter={() => setEscolhido(i)}
              onClick={() => setEscolhido(i)}
            />
          ))}
        </svg>
      </div>

      <p
        aria-live="polite"
        className="bg-superficie-2 rounded-interno text-pequeno m-0 flex min-h-[72px] flex-col gap-1 px-6 py-5 leading-snug"
      >
        {dia ? <DetalheDoDia janela={janela} dia={dia} /> : null}
      </p>

      <Legenda />

      <table className="sr-only">
        <caption>Gasto por dia, de {dataCurta(janela.inicio)} a {dataCurta(janela.fim)}</caption>
        <thead>
          <tr>
            <th>Dia</th>
            <th>Cartão lançado</th>
            <th>Cartão pendente</th>
            <th>Pix, débito e boleto</th>
            <th>Total</th>
            <th>Fatura</th>
          </tr>
        </thead>
        <tbody>
          {dias.map((d) => (
            <tr key={d.data}>
              <th>{dataCurta(d.data)}</th>
              <td>{d.a_pagar ? "-" : reais(d.cartao)}</td>
              <td>{d.a_pagar ? "-" : reais(d.cartao_pendente)}</td>
              <td>{d.a_pagar ? "-" : reais(d.conta)}</td>
              <td>{d.a_pagar ? "-" : reais(d.total)}</td>
              <td>
                {[
                  ...janela.pagamentos
                    .filter((p) => p.data === d.data)
                    .map(
                      (p) =>
                        `pagamento ${p.cartao ? nomeCurtoCartao(p.cartao) : ""} ${reais(p.valor)}`,
                    ),
                  ...janela.vencimentos
                    .filter((v) => v.data === d.data)
                    .map(
                      (v) => `vence ${nomeCurtoCartao(v.cartao)} ${reais(somar(v.valor, v.pendente))}`,
                    ),
                ].join("; ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DetalheDoDia({ janela, dia }: { janela: Janela; dia: DiaJanela }) {
  const pagamentos = janela.pagamentos.filter((p) => p.data === dia.data);
  const vencimentos = janela.vencimentos.filter((v) => v.data === dia.data);
  const titulo = dia.data === janela.hoje ? `${dataCurta(dia.data)} · hoje` : dataCurta(dia.data);
  return (
    <>
      <span className="font-forte">
        {titulo}
        {dia.a_pagar ? "" : ` · ${reais(dia.total)}`}
      </span>
      {dia.a_pagar ? (
        vencimentos.length === 0 ? (
          <span className="text-texto-2">Nenhuma fatura vence neste dia.</span>
        ) : null
      ) : (
        <span className="text-texto-2">
          cartão {reais(dia.cartao)}
          {toNumero(dia.cartao_pendente) > 0
            ? ` · cartão pendente ${reais(dia.cartao_pendente)}`
            : ""}
          {` · Pix, débito e boleto ${reais(dia.conta)}`}
        </span>
      )}
      {pagamentos.map((p, k) => (
        <span key={`p${k}`}>
          Pagamento de fatura{p.cartao ? ` ${nomeCurtoCartao(p.cartao)}` : ""}: {reais(p.valor)}
          <span className="text-texto-2"> (já está nas compras, não soma nas barras)</span>
        </span>
      ))}
      {vencimentos.map((v) => (
        <span key={v.forma_pagamento_id}>
          Vence a fatura {nomeCurtoCartao(v.cartao)}: {reais(somar(v.valor, v.pendente))}
          {toNumero(v.pendente) > 0 ? (
            <span className="text-texto-2">
              {" "}
              ({reais(v.valor)} lançado + {reais(v.pendente)} pendente)
            </span>
          ) : null}
        </span>
      ))}
    </>
  );
}
