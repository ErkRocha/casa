import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_SURFACE } from "@/styles/chart-palette";
import {
  competenciaMonthLabel,
  formatBRLAxis,
  formatBRLCompact,
  formatCompetencia,
  toNumero,
} from "@/lib/format";
import type { EvolucaoMensal } from "../types";
import { ChartTooltipCard } from "./chart-tooltip";

/**
 * Evolução mensal do gasto, empilhada pelos três baldes de pessoa.
 *
 * É o único painel da tela que é de fato um gráfico: série temporal de
 * magnitude. Os outros são medidores e placares, e por isso são HTML — barra
 * de progresso não vira SVG só para usar a biblioteca.
 *
 * Transferências já vêm excluídas pelo backend (regra de ouro do analytics).
 */

/** Ponto já convertido para número — Recharts precisa medir, não somar. */
interface PontoPlot {
  competencia: string;
  pessoaA: number;
  pessoaB: number;
  conjunto: number;
  total: number;
  emCurso: boolean;
}

const CORES = {
  pessoaA: "var(--color-person-a)",
  pessoaB: "var(--color-person-b)",
  conjunto: "var(--color-person-c)",
} as const;

/**
 * Teto do eixo arredondado para cima em múltiplos de 500 — geometria de
 * apresentação, não conta de dinheiro.
 */
function tetoDoEixo(pontos: PontoPlot[]): number {
  const maior = pontos.reduce((max, p) => Math.max(max, p.total), 0);
  return Math.max(500, Math.ceil(maior / 500) * 500);
}

interface MonthTickProps {
  x?: number;
  y?: number;
  payload?: { value?: string };
}

/**
 * O mês em curso vem em negrito e na cor primária. O realce por trás da barra
 * do protótipo não tem equivalente estável no Recharts, e um rótulo mais forte
 * carrega o mesmo sinal sem depender de interno da biblioteca.
 */
function renderMonthTick(props: MonthTickProps, pontos: PontoPlot[]) {
  const competencia = props.payload?.value ?? "";
  const emCurso = pontos.find((p) => p.competencia === competencia)?.emCurso ?? false;

  return (
    <text
      x={props.x}
      y={props.y}
      dy={12}
      textAnchor="middle"
      className={emCurso ? "fill-text-primary" : "fill-text-tertiary"}
      style={{ fontSize: "10.5px", fontWeight: emCurso ? 700 : 400 }}
    >
      {competenciaMonthLabel(competencia)}
    </text>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload?: PontoPlot }>;
}

export function MonthlyEvolutionChart({ data }: { data: EvolucaoMensal }) {
  const pontos: PontoPlot[] = data.pontos.map((p) => ({
    competencia: p.competencia,
    pessoaA: toNumero(p.pessoa_a),
    pessoaB: toNumero(p.pessoa_b),
    conjunto: toNumero(p.conjunto),
    total: toNumero(p.total),
    emCurso: p.em_curso,
  }));

  const series = [
    { key: "pessoaA" as const, nome: data.rotulo_a, cor: CORES.pessoaA },
    { key: "pessoaB" as const, nome: data.rotulo_b, cor: CORES.pessoaB },
    { key: "conjunto" as const, nome: "Conjunto", cor: CORES.conjunto },
  ];

  const max = tetoDoEixo(pontos);
  const media = toNumero(data.media_total);
  const temMesEmCurso = pontos.some((p) => p.emCurso);

  function Tip({ active, payload }: TooltipProps) {
    const ponto = payload?.[0]?.payload;
    if (!active || !ponto) return null;

    return (
      <ChartTooltipCard
        title={formatCompetencia(ponto.competencia)}
        subtitle={ponto.emCurso ? "Mês em curso — total parcial" : undefined}
        entries={series.map((s) => ({
          label: s.nome,
          color: s.cor,
          value: ponto[s.key],
        }))}
        total={ponto.total}
      />
    );
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={196}>
        <BarChart
          data={pontos}
          margin={{ top: 20, right: 8, bottom: 4, left: 0 }}
          barCategoryGap={6}
        >
          <CartesianGrid vertical={false} stroke={CHART_SURFACE.grid} />

          <XAxis
            dataKey="competencia"
            axisLine={false}
            tickLine={false}
            interval={0}
            tick={(props: MonthTickProps) => renderMonthTick(props, pontos)}
          />

          <YAxis
            width={50}
            axisLine={false}
            tickLine={false}
            domain={[0, max]}
            tickCount={4}
            tickFormatter={formatBRLAxis}
            tick={{ fill: CHART_SURFACE.axisText, fontSize: 10, fontFamily: "var(--font-mono)" }}
          />

          <Tooltip
            cursor={{ fill: "var(--color-surface)", opacity: 0.5 }}
            content={(props: TooltipProps) => <Tip {...props} />}
          />

          {/* Média do período. Rótulo direto — a linha sozinha não se explica. */}
          <ReferenceLine
            y={media}
            stroke={CHART_SURFACE.reference}
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: "média",
              position: "right",
              fill: "var(--color-text-secondary)",
              fontSize: 10,
              fontWeight: 700,
            }}
          />

          {/* Ordem fixa A → B → Conjunto, de baixo para cima. O stroke na cor
              do painel é o vão de 2px entre segmentos empilhados. */}
          {series.map((serie, index) => {
            const isTopo = index === series.length - 1;
            return (
              <Bar
                key={serie.key}
                dataKey={serie.key}
                stackId="gasto"
                name={serie.nome}
                fill={serie.cor}
                stroke={CHART_SURFACE.gap}
                strokeWidth={2}
                radius={isTopo ? [2, 2, 0, 0] : undefined}
                isAnimationActive={false}
              >
                {isTopo ? (
                  <LabelList
                    dataKey="total"
                    position="top"
                    offset={8}
                    formatter={(valor: number) => (valor > 0 ? formatBRLCompact(valor) : "")}
                    style={{
                      fill: "var(--color-text-primary)",
                      fontSize: 11,
                      fontWeight: 700,
                      fontFamily: "var(--font-mono)",
                    }}
                  />
                ) : null}
              </Bar>
            );
          })}
        </BarChart>
      </ResponsiveContainer>

      {temMesEmCurso ? (
        <p className="text-caption text-text-tertiary mt-5">
          O mês em curso aparece em negrito e está parcial — só conta o que já foi lançado.
        </p>
      ) : null}
    </div>
  );
}
