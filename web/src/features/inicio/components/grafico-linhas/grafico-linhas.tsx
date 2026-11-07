import { useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

import { reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import { classesDaCor } from "./cores";
import { distribuirRotulos, encurtar, guiasDoEixo, rotuloEixo, rotulosDoEixoX } from "./escala";
import { PainelDoDia } from "./painel-do-dia";
import type { LinhaGrafico, PontoDaLinha } from "./tipos";
import { useLargura } from "./use-largura";

/**
 * Gráfico de linhas acumuladas por dia, em SVG (sem biblioteca). Serve ao
 * gráfico dos gastos e, depois, ao das faturas: quem chama entrega as linhas
 * prontas (`LinhaGrafico`) e o desenho, o crosshair, o painel do dia e o
 * teclado vêm daqui.
 *
 * - Linhas de 2px na cor do token da série; texto sempre em cor de texto.
 * - Ponto vazado (miolo branco) nos dias com compra pendente no banco.
 * - Até `maxRotulos` linhas (padrão 4), cada uma leva o nome e o valor no fim.
 * - Linhas esparsas (faturas): `pontos` com dias repetidos (queda vertical) e
 *   trechos tracejados; o eixo pode passar de hoje, que ganha uma guia.
 * - Mouse, toque (arrastar) ou setas do teclado escolhem o dia; o painel sob o
 *   gráfico lista o valor de todas as linhas naquele dia.
 * - A largura é a do contêiner (1 unidade = 1px): nada estoura no celular.
 */

/** Até quantas linhas recebem o rótulo no fim; com mais, a legenda basta. */
const MAX_ROTULOS_DIRETOS = 4;
/** Padrão do trecho que ainda vai acontecer. */
const TRACEJADO = "5 4";

/** Caminhos SVG de uma linha esparsa, um por trecho contínuo de mesmo estilo. */
function trechos(
  pontos: PontoDaLinha[],
  x: (i: number) => number,
  y: (v: number) => number,
): Array<{ d: string; tracejado: boolean }> {
  const saida: Array<{ d: string; tracejado: boolean }> = [];
  let atual: { d: string; tracejado: boolean } | null = null;
  pontos.forEach((p, k) => {
    const anterior = pontos[k - 1];
    if (!anterior) return;
    if (!atual || atual.tracejado !== p.tracejado) {
      atual = {
        d: `M${x(anterior.i).toFixed(1)} ${y(anterior.valor).toFixed(1)}`,
        tracejado: p.tracejado,
      };
      saida.push(atual);
    }
    atual.d += ` L${x(p.i).toFixed(1)} ${y(p.valor).toFixed(1)}`;
  });
  const unico = pontos[0];
  if (pontos.length === 1 && unico) {
    const ponto = `${x(unico.i).toFixed(1)} ${y(unico.valor).toFixed(1)}`;
    saida.push({ d: `M${ponto} L${ponto}`, tracejado: false });
  }
  return saida;
}
/** Abaixo desta largura (px) vale a altura e a fonte do celular. */
const LARGURA_CELULAR = 600;

export function GraficoLinhas({
  dias,
  linhas,
  hoje,
  rotuloAcessivel,
  maxRotulos = MAX_ROTULOS_DIRETOS,
  vazioNoDia,
  className,
}: {
  /** Datas ISO, em ordem; o último dia é o fim da janela. */
  dias: string[];
  linhas: LinhaGrafico[];
  hoje: string;
  rotuloAcessivel: string;
  /** Até quantas linhas recebem o rótulo no fim. */
  maxRotulos?: number;
  /** Texto do painel quando nenhuma linha existe no dia escolhido. */
  vazioNoDia?: string;
  className?: string;
}) {
  const { ref, largura } = useLargura<HTMLDivElement>();
  const n = dias.length;
  const celular = largura < LARGURA_CELULAR;
  const altura = celular ? 220 : 260;
  const fonteEixo = celular ? 10 : 11;
  const fonteRotulo = celular ? 11 : 12;

  const [escolhido, setEscolhido] = useState<number | null>(null);
  // Hoje é o último dia, a menos que o eixo siga além (faturas até o vencimento).
  const achado = dias.indexOf(hoje);
  const indiceHoje = achado >= 0 ? achado : n - 1;
  const selecionado = Math.min(escolhido ?? indiceHoje, Math.max(n - 1, 0));

  const esq = celular ? 50 : 58;
  const topo = 12;
  const base = altura - 24;
  const rotuloX = base + 16;

  const rotuladas = linhas.filter((l) => !l.semRotulo);
  const comRotulos = rotuladas.length > 0 && rotuladas.length <= maxRotulos;
  const textos = rotuladas.map((l) => ({
    nome: l.rotuloCurto,
    valor: l.fim?.texto ?? reais(l.acumulado[n - 1] ?? "0", { centavos: false }),
    i: l.fim?.i ?? n - 1,
    v: l.fim?.valor ?? l.valores[n - 1] ?? 0,
  }));
  const larguraTexto = (t: { nome: string; valor: string }) =>
    (Math.min(t.nome.length, 12) + 1 + t.valor.length) * fonteRotulo * 0.6;
  const dir = comRotulos
    ? Math.min(Math.max(...textos.map(larguraTexto)) + 18, largura * 0.45)
    : 14;
  const caracteresMax = Math.max(Math.floor((dir - 18) / (fonteRotulo * 0.6)), 4);

  const larguraPlot = Math.max(largura - esq - dir, 1);
  const passoX = larguraPlot / Math.max(n - 1, 1);
  const x = (i: number) => esq + i * passoX;

  const maximo = Math.max(0, ...linhas.flatMap((l) => l.valores));
  const { guias, teto } = guiasDoEixo(maximo);
  const y = (v: number) => base - (v / teto) * (base - topo);

  const yFinais = textos.map((t) => y(t.v));
  const yRotulos = distribuirRotulos(yFinais, fonteRotulo + 3, topo + 4, base);

  const rotulosX = rotulosDoEixoX(dias, passoX, undefined, indiceHoje);

  const dia = dias[selecionado];

  const indiceDoPonteiro = (e: PointerEvent<SVGSVGElement>) => {
    const caixa = e.currentTarget.getBoundingClientRect();
    const i = Math.round((e.clientX - caixa.left - esq) / passoX);
    return Math.min(Math.max(i, 0), n - 1);
  };

  const mover = (e: KeyboardEvent<HTMLDivElement>) => {
    let proximo: number | null = null;
    if (e.key === "ArrowLeft") proximo = selecionado - 1;
    else if (e.key === "ArrowRight") proximo = selecionado + 1;
    else if (e.key === "Home") proximo = 0;
    else if (e.key === "End") proximo = n - 1;
    if (proximo === null) return;
    e.preventDefault();
    setEscolhido(Math.min(Math.max(proximo, 0), n - 1));
  };

  if (n === 0) return null;

  return (
    <div className={cn("flex min-w-0 flex-col gap-4", className)}>
      <div
        ref={ref}
        role="group"
        tabIndex={0}
        aria-label={`${rotuloAcessivel}. Use as setas para escolher o dia.`}
        onKeyDown={mover}
        className="focus-visible:outline-destaque rounded-interno w-full min-w-0 outline-offset-4 focus-visible:outline-2"
      >
        <svg
          width="100%"
          height={altura}
          viewBox={`0 0 ${largura} ${altura}`}
          aria-hidden="true"
          className="block touch-pan-y select-none"
          onPointerDown={(e) => setEscolhido(indiceDoPonteiro(e))}
          onPointerMove={(e) => setEscolhido(indiceDoPonteiro(e))}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") setEscolhido(null);
          }}
        >
          {guias.map((v) => (
            <g key={v}>
              <line
                x1={esq}
                y1={y(v)}
                x2={esq + larguraPlot}
                y2={y(v)}
                className={v === 0 ? "stroke-linha" : "stroke-linha-suave"}
                strokeWidth="1"
              />
              <text
                x={esq - 6}
                y={y(v) + 4}
                textAnchor="end"
                fontSize={fonteEixo}
                className="fill-texto-2"
              >
                {rotuloEixo(v)}
              </text>
            </g>
          ))}

          {rotulosX.map(({ i, texto }) => (
            <text
              key={i}
              x={x(i)}
              y={rotuloX}
              textAnchor={i === n - 1 ? "end" : "middle"}
              fontSize={fonteEixo}
              fontWeight={i === indiceHoje ? 650 : 400}
              className={i === indiceHoje ? "fill-texto" : "fill-texto-2"}
            >
              {texto}
            </text>
          ))}

          {indiceHoje < n - 1 ? (
            <>
              <rect
                x={x(indiceHoje)}
                y={topo}
                width={x(n - 1) - x(indiceHoje)}
                height={base - topo}
                className="fill-superficie-2"
                opacity="0.6"
              />
              <line
                x1={x(indiceHoje)}
                y1={topo}
                x2={x(indiceHoje)}
                y2={base}
                className="stroke-contorno"
                strokeWidth="1.5"
              />
            </>
          ) : null}

          <line
            x1={x(selecionado)}
            y1={topo}
            x2={x(selecionado)}
            y2={base}
            className="stroke-texto-2"
            strokeWidth="1"
          />

          {linhas.map((linha) =>
            linha.pontos ? (
              <g key={linha.chave} opacity={linha.opacidade}>
                {trechos(linha.pontos, x, y).map((t) => (
                  <path
                    key={t.d}
                    d={t.d}
                    fill="none"
                    strokeWidth="2"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    strokeDasharray={t.tracejado ? TRACEJADO : undefined}
                    className={classesDaCor(linha.cor).traco}
                  />
                ))}
              </g>
            ) : (
              <path
                key={linha.chave}
                d={linha.valores
                  .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
                  .join(" ")}
                fill="none"
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                className={classesDaCor(linha.cor).traco}
              />
            ),
          )}

          {linhas.map((linha) =>
            linha.temPendente.map((tem, i) =>
              tem ? (
                <circle
                  key={`${linha.chave}-${i}`}
                  cx={x(i)}
                  cy={y(linha.valores[i] ?? 0)}
                  r="3.5"
                  strokeWidth="2"
                  className={cn("fill-superficie", classesDaCor(linha.cor).traco)}
                />
              ) : null,
            ),
          )}

          {linhas.map((linha) =>
            linha.existe?.[selecionado] === false ? null : (
            <circle
              key={`sel-${linha.chave}`}
              cx={x(selecionado)}
              cy={y(linha.valores[selecionado] ?? 0)}
              r="4.5"
              strokeWidth="2"
              className={cn("stroke-superficie", classesDaCor(linha.cor).preenchimento)}
            />
            ),
          )}

          {comRotulos
            ? rotuladas.map((linha, k) => {
                const texto = textos[k];
                const yr = yRotulos[k] ?? 0;
                if (!texto) return null;
                const nome = encurtar(
                  texto.nome,
                  Math.max(caracteresMax - texto.valor.length - 1, 3),
                );
                return (
                  <g key={`rot-${linha.chave}`}>
                    {/* Linha que acaba antes do fim: marca no ponto e guia até o rótulo. */}
                    {texto.i < n - 1 ? (
                      <>
                        <line
                          x1={x(texto.i)}
                          y1={y(texto.v)}
                          x2={esq + larguraPlot + 8}
                          y2={yr}
                          strokeWidth="1"
                          strokeDasharray="1 3"
                          opacity="0.6"
                          className={classesDaCor(linha.cor).traco}
                        />
                        <circle
                          cx={x(texto.i)}
                          cy={y(texto.v)}
                          r="2.5"
                          opacity={linha.opacidade}
                          className={classesDaCor(linha.cor).preenchimento}
                        />
                      </>
                    ) : null}
                    {/* Com hoje escolhido, a marca da linha já está ao lado. */}
                    {selecionado === n - 1 && texto.i === n - 1 ? null : (
                      <circle
                        cx={esq + larguraPlot + 8}
                        cy={yr}
                        r="3"
                        className={classesDaCor(linha.cor).preenchimento}
                      />
                    )}
                    <text
                      x={esq + larguraPlot + 15}
                      y={yr + 4}
                      fontSize={fonteRotulo}
                      fontWeight={600}
                      className="fill-texto"
                    >
                      {nome} {texto.valor}
                    </text>
                  </g>
                );
              })
            : null}
        </svg>
      </div>

      {dia ? (
        <PainelDoDia
          data={dia}
          ehHoje={dia === hoje}
          indice={selecionado}
          linhas={linhas}
          vazio={vazioNoDia}
        />
      ) : null}
    </div>
  );
}
