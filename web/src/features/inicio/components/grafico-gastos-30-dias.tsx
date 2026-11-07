import { useState } from "react";
import type { ReactNode } from "react";

import { CabecalhoBloco, Card } from "@/components/ui/card";
import { reais, sinal, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useGastos30Dias } from "../queries";
import { dataCurta, nomeCurtoCartao } from "../textos";
import type { GastosJanela, SerieGasto } from "../types";
import { GraficoLinhas } from "./grafico-linhas/grafico-linhas";
import { LegendaChips } from "./grafico-linhas/legenda-chips";
import type { LinhaGrafico } from "./grafico-linhas/tipos";

/**
 * "Gastos nos últimos 30 dias" (D-28): uma linha acumulada por cartão, Pix,
 * débito, boleto e outros, pela data da compra. Compras pendentes no banco
 * entram na linha e aparecem como ponto vazado.
 *
 * Todo número vem de `/analytics/inicio/gastos-30-dias`: o acumulado, os totais
 * e a linha da soma saem do banco. O estado daqui só diz o que mostrar (pessoa,
 * séries ligadas, soma). O desenho, o crosshair e a legenda moram em
 * `grafico-linhas/` e servem também ao gráfico das faturas.
 */

export type VarianteGrafico = "celular" | "computador";

function paraLinha(serie: SerieGasto): LinhaGrafico {
  return {
    chave: serie.chave,
    rotulo: serie.rotulo,
    rotuloCurto: serie.tipo === "cartao" ? nomeCurtoCartao(serie.rotulo) : serie.rotulo,
    cor: serie.cor,
    valores: serie.pontos.map((p) => toNumero(p.acumulado)),
    acumulado: serie.pontos.map((p) => p.acumulado),
    pendenteAcumulado: serie.pontos.map((p) => p.pendente_acumulado),
    temPendente: serie.pontos.map((p) => p.tem_pendente),
  };
}

/** O que será desenhado: a linha da soma, se pedida e pronta, senão as visíveis. */
function seriesDesenhadas(dados: GastosJanela, somar: boolean): SerieGasto[] {
  if (somar && dados.soma) return [dados.soma];
  return dados.series.filter((s) => s.visivel);
}

function LegendaPendente() {
  return (
    <span className="text-pequeno text-texto-2 flex items-center gap-3">
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" className="shrink-0">
        <circle cx="7" cy="7" r="4.5" strokeWidth="2" className="fill-superficie stroke-texto-2" />
      </svg>
      pendente no banco
    </span>
  );
}

function BotaoSegmento({
  ligado,
  onClick,
  children,
}: {
  ligado: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={ligado}
      onClick={onClick}
      className={cn(
        "text-apoio min-h-22 cursor-pointer rounded-full border-none px-7 whitespace-nowrap",
        ligado ? "bg-texto font-semibold text-white" : "text-texto bg-transparent",
      )}
    >
      {children}
    </button>
  );
}

export function GraficoGastos30Dias({
  variante,
  className,
}: {
  variante: VarianteGrafico;
  className?: string;
}) {
  const [pessoaId, setPessoaId] = useState<number | null>(null);
  // Nulo = todas as séries; senão, as chaves ligadas (o que a API recebe).
  const [series, setSeries] = useState<string[] | null>(null);
  const [somar, setSomar] = useState(false);
  const consulta = useGastos30Dias({ pessoaId, series, somar });
  const dados = consulta.data;

  const alternarSerie = (chave: string) => {
    if (!dados) return;
    const todas = dados.series.map((s) => s.chave);
    const ligadas = dados.series.filter((s) => s.visivel).map((s) => s.chave);
    const novas = ligadas.includes(chave) ? ligadas.filter((c) => c !== chave) : [...ligadas, chave];
    if (novas.length === 0) return;
    setSeries(novas.length === todas.length ? null : novas);
  };

  const escolherPessoa = (id: number | null) => {
    // As séries mudam com a pessoa: volta a mostrar todas.
    setPessoaId(id);
    setSeries(null);
  };

  const conteudo = (
    <>
      <CabecalhoBloco
        titulo="Gastos nos últimos 30 dias"
        direita={dados ? `de ${dataCurta(dados.inicio)} a ${dataCurta(dados.hoje)}` : undefined}
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
          className="bg-superficie-2 rounded-interno animate-shimmer h-[260px]"
        />
      ) : (
        <Corpo
          dados={dados}
          somar={somar}
          pessoaId={pessoaId}
          onPessoa={escolherPessoa}
          onSomar={() => setSomar((s) => !s)}
          onAlternar={alternarSerie}
        />
      )}
    </>
  );

  if (variante === "celular") {
    return <div className="flex min-w-0 flex-col gap-5">{conteudo}</div>;
  }
  return <Card className={cn("flex min-w-0 flex-col gap-6 px-11 py-10", className)}>{conteudo}</Card>;
}

function Corpo({
  dados,
  somar,
  pessoaId,
  onPessoa,
  onSomar,
  onAlternar,
}: {
  dados: GastosJanela;
  somar: boolean;
  pessoaId: number | null;
  onPessoa: (id: number | null) => void;
  onSomar: () => void;
  onAlternar: (chave: string) => void;
}) {
  const desenhadas = seriesDesenhadas(dados, somar);
  const linhas = desenhadas.map(paraLinha);
  const dias = desenhadas[0]?.pontos.map((p) => p.data) ?? [];
  const mostraPessoas = dados.pessoas_conectadas.length > 1;
  const algumPendente = sinal(dados.pendente) > 0;

  return (
    <>
      <div className="flex flex-col gap-2">
        <span className="text-valor font-forte">{reais(dados.total)}</span>
        {algumPendente ? (
          <span className="text-pequeno text-texto-2">
            {reais(dados.pendente)} ainda pendente no banco
          </span>
        ) : null}
      </div>

      {mostraPessoas || dados.series.length > 0 ? (
        <div className="flex flex-wrap items-center gap-4">
          {mostraPessoas ? (
            <div
              role="group"
              aria-label="Filtrar por pessoa"
              className="bg-superficie-2 inline-flex max-w-full gap-1 overflow-x-auto rounded-full p-1"
            >
              <BotaoSegmento ligado={pessoaId === null} onClick={() => onPessoa(null)}>
                Todos
              </BotaoSegmento>
              {dados.pessoas_conectadas.map((p) => (
                <BotaoSegmento key={p.id} ligado={pessoaId === p.id} onClick={() => onPessoa(p.id)}>
                  {p.nome}
                </BotaoSegmento>
              ))}
            </div>
          ) : null}
          {dados.series.length > 0 ? (
            <button
              type="button"
              aria-pressed={somar}
              onClick={onSomar}
              className={cn(
                "text-apoio min-h-22 cursor-pointer rounded-full px-7 whitespace-nowrap",
                somar
                  ? "bg-texto border-texto border-[1.5px] font-semibold text-white"
                  : "bg-superficie text-texto border-contorno border-[1.5px]",
              )}
            >
              Somar selecionadas
            </button>
          ) : null}
        </div>
      ) : null}

      {dados.series.length === 0 ? (
        <p className="text-apoio text-texto-2 bg-superficie-2 rounded-interno m-0 px-6 py-8">
          Nenhuma despesa nos últimos 30 dias
          {pessoaId !== null ? " para esta pessoa" : ""}.
        </p>
      ) : (
        <>
          <LegendaChips
            itens={dados.series.map((s) => ({
              chave: s.chave,
              rotulo: s.tipo === "cartao" ? nomeCurtoCartao(s.rotulo) : s.rotulo,
              cor: s.cor,
              total: s.total,
              ligada: s.visivel,
            }))}
            onAlternar={onAlternar}
          />
          {linhas.length > 0 ? (
            <GraficoLinhas
              dias={dias}
              linhas={linhas}
              hoje={dados.hoje}
              rotuloAcessivel={`Gráfico dos gastos acumulados nos últimos 30 dias, de ${dataCurta(dados.inicio)} a ${dataCurta(dados.hoje)}`}
            />
          ) : null}
          {algumPendente ? <LegendaPendente /> : null}

          {/* sr-only no div: numa table a largura de 1px é ignorada e a tabela
              escondida alarga a página no celular. */}
          <div className="sr-only">
            <table>
              <caption>
                Gasto acumulado por dia, de {dataCurta(dados.inicio)} a {dataCurta(dados.hoje)}
              </caption>
              <thead>
                <tr>
                  <th>Dia</th>
                  {desenhadas.map((s) => (
                    <th key={s.chave}>{s.rotulo}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dias.map((data, i) => (
                  <tr key={data}>
                    <th>{dataCurta(data)}</th>
                    {desenhadas.map((s) => {
                      const ponto = s.pontos[i];
                      return (
                        <td key={s.chave}>
                          {ponto ? reais(ponto.acumulado) : "-"}
                          {ponto?.tem_pendente ? " (compra pendente no dia)" : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
