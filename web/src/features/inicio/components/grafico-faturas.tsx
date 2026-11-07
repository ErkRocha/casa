import { useState } from "react";

import { CabecalhoBloco, Card } from "@/components/ui/card";
import { nomeDoMes, reais, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useFaturasCiclos } from "../queries";
import { dataCurta, nomeCurtoCartao } from "../textos";
import type { CicloFatura, FaturasCiclos } from "../types";
import type { VarianteGrafico } from "./grafico-gastos-30-dias";
import { GraficoLinhas } from "./grafico-linhas/grafico-linhas";
import { LegendaChips } from "./grafico-linhas/legenda-chips";
import type { LinhaGrafico, PontoDaLinha } from "./grafico-linhas/tipos";

/**
 * "Faturas" (D-29): uma linha por ciclo de fatura de cada cartão, dos últimos
 * 30 dias até o último vencimento dos próximos 15. A linha sobe com as compras,
 * fica reta depois do fechamento, cai a zero no pagamento identificado e, sem
 * pagamento, segue tracejada de hoje até o vencimento.
 *
 * Todo número e toda data vêm de `/analytics/inicio/faturas-ciclos`: os pontos
 * diários, os valores e as origens saem do banco. O estado daqui só diz quais
 * cartões estão ligados. O desenho mora em `grafico-linhas/`.
 */

/** Opacidade dos ciclos anteriores ao atual. */
const OPACIDADE_ANTERIOR = 0.45;
/** Com mais linhas que isto, só o ciclo atual e os não pagos levam rótulo. */
const MUITAS_LINHAS = 4;
/** Até quantas linhas rotuladas cabem no fim do gráfico. */
const MAX_ROTULADAS = 6;

const MS_DIA = 86_400_000;

function emDias(iso: string): number {
  const [a, m, d] = iso.split("-").map(Number);
  return Math.round(Date.UTC(a ?? 1970, (m ?? 1) - 1, d ?? 1) / MS_DIA);
}

/** Todos os dias de `inicio` a `fim`, em ISO. */
function diasEntre(inicio: string, fim: string): string[] {
  const primeiro = emDias(inicio);
  const total = Math.max(emDias(fim) - primeiro, 0);
  return Array.from({ length: total + 1 }, (_, k) =>
    new Date((primeiro + k) * MS_DIA).toISOString().slice(0, 10),
  );
}

/** "nov" a partir de `2026-11-01`. */
function mesAbreviado(iso: string): string {
  return nomeDoMes(Number(iso.slice(5, 7))).slice(0, 3);
}

function chaveCartao(ciclo: CicloFatura): string {
  return `cartao:${ciclo.forma_pagamento_id}`;
}

function paraLinha(ciclo: CicloFatura, inicio: string, n: number, rotular: boolean): LinhaGrafico {
  const base = emDias(inicio);
  const pontos: PontoDaLinha[] = ciclo.pontos.map((p) => ({
    i: emDias(p.data) - base,
    valor: toNumero(p.valor),
    tracejado: p.tracejado,
  }));
  const primeiro = pontos[0]?.i ?? 0;
  const ultimo = pontos[pontos.length - 1]?.i ?? 0;

  // Um valor por dia para o painel e o marcador; no dia do pagamento vale o
  // valor antes da queda (o primeiro ponto do dia).
  const valores = new Array<number>(n).fill(0);
  const acumulado = new Array<string>(n).fill("0");
  const jaTem = new Set<number>();
  ciclo.pontos.forEach((p, k) => {
    const ponto = pontos[k];
    if (!ponto || jaTem.has(ponto.i) || ponto.i < 0 || ponto.i >= n) return;
    jaTem.add(ponto.i);
    valores[ponto.i] = ponto.valor;
    acumulado[ponto.i] = p.valor;
  });
  const existe = Array.from({ length: n }, (_, i) => i >= primeiro && i <= ultimo);

  // O rótulo fica no último ponto com valor; o pago, no topo antes da queda.
  const comValor = pontos.filter((p) => p.valor > 0);
  const marca = comValor[comValor.length - 1] ?? pontos[pontos.length - 1];
  const nomeMes = `${nomeCurtoCartao(ciclo.cartao)} · ${mesAbreviado(ciclo.mes_fatura)}`;

  return {
    chave: ciclo.chave,
    rotulo: nomeMes,
    rotuloCurto: nomeMes,
    cor: ciclo.cor,
    valores,
    acumulado,
    pendenteAcumulado: new Array<string>(n).fill("0"),
    temPendente: new Array<boolean>(n).fill(false),
    pontos,
    existe,
    opacidade: ciclo.atual ? 1 : OPACIDADE_ANTERIOR,
    nota: ciclo.pago_em
      ? `paga em ${dataCurta(ciclo.pago_em)}`
      : `vence ${dataCurta(ciclo.vencimento)}`,
    fim: marca
      ? { i: marca.i, valor: marca.valor, texto: reais(String(marca.valor), { centavos: false }) }
      : undefined,
    semRotulo: !rotular,
  };
}

function Explicacao() {
  return (
    <p className="text-pequeno text-texto-2 m-0 flex flex-wrap items-center gap-x-7 gap-y-2">
      <span className="inline-flex items-center gap-3">
        <svg width="26" height="8" aria-hidden="true">
          <line
            x1="1"
            y1="4"
            x2="25"
            y2="4"
            strokeWidth="2"
            strokeDasharray="5 4"
            className="stroke-texto-2"
          />
        </svg>
        tracejado: até o vencimento
      </span>
      <span className="inline-flex items-center gap-3">
        <svg width="26" height="8" aria-hidden="true">
          <line
            x1="1"
            y1="4"
            x2="25"
            y2="4"
            strokeWidth="2"
            opacity={OPACIDADE_ANTERIOR}
            className="stroke-texto-2"
          />
        </svg>
        mais claro: fatura anterior
      </span>
    </p>
  );
}

export function GraficoFaturas({
  variante,
  className,
}: {
  variante: VarianteGrafico;
  className?: string;
}) {
  const consulta = useFaturasCiclos();
  const dados = consulta.data;

  const conteudo = (
    <>
      <CabecalhoBloco
        titulo="Faturas"
        direita={dados ? `de ${dataCurta(dados.inicio)} a ${dataCurta(dados.fim)}` : undefined}
      />
      {consulta.isError && !dados ? (
        <p role="alert" className="text-apoio text-texto-2 m-0">
          Não foi possível carregar o gráfico.{" "}
          <button
            type="button"
            onClick={() => void consulta.refetch()}
            className="text-destaque cursor-pointer border-none bg-transparent p-0 font-semibold"
          >
            Tentar de novo
          </button>
        </p>
      ) : !dados ? (
        <div
          aria-busy="true"
          aria-label="Carregando o gráfico"
          className="bg-superficie-2 rounded-interno animate-shimmer h-[220px]"
        />
      ) : (
        <Corpo dados={dados} />
      )}
    </>
  );

  if (variante === "celular") {
    return <div className="flex min-w-0 flex-col gap-5">{conteudo}</div>;
  }
  return <Card className={cn("flex min-w-0 flex-col gap-6 px-11 py-10", className)}>{conteudo}</Card>;
}

function Corpo({ dados }: { dados: FaturasCiclos }) {
  // Cartões desligados na legenda; estado só de tela, nada a pedir à API.
  const [desligados, setDesligados] = useState<string[]>([]);

  if (dados.ciclos.length === 0) {
    return (
      <p className="text-apoio text-texto-2 bg-superficie-2 rounded-interno m-0 px-6 py-8">
        Nenhuma fatura com datas conhecidas neste período.
      </p>
    );
  }

  const cartoes: Array<{ chave: string; rotulo: string; cor: string }> = [];
  for (const c of dados.ciclos) {
    const chave = chaveCartao(c);
    if (!cartoes.some((k) => k.chave === chave)) {
      cartoes.push({ chave, rotulo: nomeCurtoCartao(c.cartao), cor: c.cor });
    }
  }
  const alternar = (chave: string) =>
    setDesligados((atual) =>
      atual.includes(chave) ? atual.filter((c) => c !== chave) : [...atual, chave],
    );

  const visiveis = dados.ciclos.filter((c) => !desligados.includes(chaveCartao(c)));
  const dias = diasEntre(dados.inicio, dados.fim);
  const muitas = visiveis.length > MUITAS_LINHAS;
  const linhas = visiveis.map((c) =>
    paraLinha(c, dados.inicio, dias.length, !muitas || c.atual || c.situacao !== "paga"),
  );

  return (
    <>
      <LegendaChips
        itens={cartoes.map((k) => ({ ...k, ligada: !desligados.includes(k.chave) }))}
        onAlternar={alternar}
      />
      <Explicacao />
      <GraficoLinhas
        dias={dias}
        linhas={linhas}
        hoje={dados.hoje}
        maxRotulos={MAX_ROTULADAS}
        vazioNoDia="Nenhuma fatura em andamento neste dia."
        rotuloAcessivel={`Gráfico das faturas dos cartões, de ${dataCurta(dados.inicio)} a ${dataCurta(dados.fim)}`}
      />

      {/* sr-only no div: numa table a largura de 1px é ignorada e a tabela
          escondida alarga a página no celular. */}
      <div className="sr-only">
        <table>
          <caption>
            Faturas dos cartões, de {dataCurta(dados.inicio)} a {dataCurta(dados.fim)}
          </caption>
          <thead>
            <tr>
              <th>Cartão</th>
              <th>Fatura</th>
              <th>Abertura</th>
              <th>Fechamento</th>
              <th>Vencimento</th>
              <th>Situação</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            {visiveis.map((c) => (
              <tr key={c.chave}>
                <th>{c.cartao}</th>
                <td>{mesAbreviado(c.mes_fatura)}</td>
                <td>{dataCurta(c.abertura)}</td>
                <td>{dataCurta(c.fechamento)}</td>
                <td>{dataCurta(c.vencimento)}</td>
                <td>
                  {c.pago_em
                    ? `paga em ${dataCurta(c.pago_em)}`
                    : c.situacao === "aberta"
                      ? "aberta"
                      : "fechada, sem pagamento"}
                  {c.atual ? "" : ", fatura anterior"}
                </td>
                <td>{reais(c.valor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
