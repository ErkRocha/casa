import { reais, toNumero } from "@/lib/format";
import type { PontoAcumulado, SituacaoMes } from "../types";

/**
 * "Gasto acumulado no mês" (`InicioDesktop` / `InicioCelular`, D-22).
 *
 * A curva é a despesa somada dia a dia, como a API manda; a linha tracejada
 * é o orçamento do mês. Os valores viram número só aqui, para virar
 * coordenada no SVG — nada é somado no navegador.
 */

const GEOMETRIA = {
  computador: { largura: 700, altura: 230, base: 200, topo: 22, eixo: 222, fonte: 13, area: true },
  celular: { largura: 354, altura: 170, base: 150, topo: 18, eixo: 166, fonte: 12, area: false },
} as const;

export function GraficoAcumulado({
  serie,
  diasNoMes,
  diaReferencia,
  orcamento,
  situacao,
  variante,
}: {
  serie: PontoAcumulado[];
  diasNoMes: number;
  diaReferencia: number;
  orcamento: string | null;
  situacao: SituacaoMes;
  variante: keyof typeof GEOMETRIA;
}) {
  const g = GEOMETRIA[variante];
  const ultimo = serie.at(-1)?.acumulado ?? "0";
  const meta = orcamento ? toNumero(orcamento) : 0;
  const escala = Math.max(meta, toNumero(ultimo), 1);
  const y = (valor: number) => g.base - (valor / escala) * (g.base - g.topo);
  const x = (dia: number) => (dia / diasNoMes) * g.largura;

  const pontos = [[0, g.base], ...serie.map((p) => [x(p.dia), y(toNumero(p.acumulado))])];
  const curva = pontos.map(([px, py]) => `${px!.toFixed(1)},${py!.toFixed(1)}`).join(" ");
  const [hojeX, hojeY] = pontos.at(-1) as [number, number];
  const area = `${curva} ${hojeX.toFixed(1)},${g.base}`;
  const linhaOrcamento = meta > 0 ? y(meta) : null;

  // O rótulo do ponto vai para a esquerda quando encostaria na borda.
  const rotuloADireita = hojeX < g.largura * 0.78;
  const rotulo =
    variante === "celular"
      ? situacao === "corrente"
        ? "Hoje"
        : "Fim"
      : `${situacao === "corrente" ? "Hoje" : "Fechou"}: ${reais(ultimo, { centavos: false })}`;
  const mostrarDiaDoMeio =
    serie.length > 0 && diaReferencia > 2 && diaReferencia < diasNoMes - 2;

  const descricao =
    `Gasto acumulado até o dia ${diaReferencia}: ${reais(ultimo)}` +
    (orcamento ? `, comparado ao orçamento de ${reais(orcamento, { centavos: false })}` : "");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${g.largura} ${g.altura}`}
      role="img"
      aria-label={descricao}
      className="block overflow-visible"
    >
      <line x1="0" y1={g.base} x2={g.largura} y2={g.base} className="stroke-linha" strokeWidth="1" />
      {variante === "computador" ? (
        <line
          x1="0"
          y1={(g.base + g.topo) / 2}
          x2={g.largura}
          y2={(g.base + g.topo) / 2}
          className="stroke-linha-suave"
          strokeWidth="1"
        />
      ) : null}
      {linhaOrcamento !== null ? (
        <>
          <line
            x1="0"
            y1={linhaOrcamento}
            x2={g.largura}
            y2={linhaOrcamento}
            className="stroke-guia"
            strokeWidth="1.5"
            strokeDasharray={variante === "computador" ? "6 6" : "5 5"}
          />
          <text
            x={g.largura}
            y={linhaOrcamento - 8}
            textAnchor="end"
            fontSize={g.fonte}
            className="fill-texto-2"
          >
            Orçamento {reais(orcamento, { centavos: false })}
          </text>
        </>
      ) : null}

      {serie.length > 0 ? (
        <>
          {g.area ? <polyline points={area} className="fill-destaque-fundo" stroke="none" /> : null}
          <polyline
            points={curva}
            fill="none"
            className="stroke-destaque"
            strokeWidth={variante === "computador" ? 3.5 : 3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle
            cx={hojeX}
            cy={hojeY}
            r={variante === "computador" ? 7 : 6}
            className="fill-destaque stroke-superficie"
            strokeWidth="3"
          />
          <text
            x={rotuloADireita ? hojeX + 14 : hojeX - 14}
            y={hojeY + 5}
            textAnchor={rotuloADireita ? "start" : "end"}
            fontSize={variante === "computador" ? 14 : 12}
            fontWeight={variante === "computador" ? 650 : 600}
            className="fill-texto"
          >
            {rotulo}
          </text>
        </>
      ) : null}

      <text x="0" y={g.eixo} fontSize={g.fonte - 1} className="fill-texto-2">
        dia 1
      </text>
      {mostrarDiaDoMeio ? (
        <text x={hojeX} y={g.eixo} textAnchor="middle" fontSize={g.fonte - 1} className="fill-texto-2">
          dia {diaReferencia}
        </text>
      ) : null}
      <text x={g.largura} y={g.eixo} textAnchor="end" fontSize={g.fonte - 1} className="fill-texto-2">
        dia {diasNoMes}
      </text>
    </svg>
  );
}
