import { useState } from "react";

import { PersonDot } from "@/components/layout/person-legend";
import { Button } from "@/components/ui/controls";
import { usePessoas } from "@/features/cadastros/queries";
import { baldesDoCasal } from "@/features/filters/baldes";
import { useFiltros } from "@/features/filters/filter-context";
import { ApiError } from "@/lib/api";
import { formatCompetencia } from "@/lib/format";
import { BudgetProgressChart } from "./components/budget-progress-chart";
import { CategoryCompositionChart } from "./components/category-composition-chart";
import { MonthlyEvolutionChart } from "./components/monthly-evolution-chart";
import { Panel } from "./components/panel";
import { PeriodComparisonCards } from "./components/period-comparison-cards";
import { PersonSplitChart } from "./components/person-split-chart";
import { useAnalyticsResumo } from "./queries";

/**
 * Tela de Analytics — fase 4 do roadmap.
 *
 * Os filtros vêm do contexto compartilhado com a tela de transações, e o
 * recorte inteiro vira parâmetro de URL. Mudar um filtro dispara uma query
 * nova; nada é recalculado no navegador (D-14).
 */
export function AnalyticsPage() {
  const { filtros } = useFiltros();
  const [drillCategoriaId, setDrillCategoriaId] = useState<number | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useAnalyticsResumo(
    filtros,
    drillCategoriaId,
  );
  const { data: pessoas = [] } = usePessoas();

  if (isLoading) {
    return <EsqueletoAnalytics />;
  }

  if (isError || !data) {
    return (
      <div
        role="alert"
        className="bg-surface-sunken flex flex-col items-center gap-5 rounded-md px-12 py-32 text-center"
      >
        <div className="text-title text-expense font-semibold">
          Não foi possível carregar os gráficos
        </div>
        <p className="text-body text-text-tertiary max-w-200">
          {error instanceof ApiError ? error.detail : "Erro inesperado ao consultar o banco."}
        </p>
        <Button onClick={() => void refetch()}>Tentar novamente</Button>
      </div>
    );
  }

  const mesesDistintos = new Set(data.evolucao_mensal.pontos.map((p) => p.competencia)).size;

  return (
    <>
      <div className="mb-10 flex flex-wrap items-center gap-9">
        {baldesDoCasal(pessoas).map((b) => (
          <span
            key={String(b.balde)}
            className="text-body-sm text-text-secondary flex shrink-0 items-center gap-4 whitespace-nowrap"
          >
            <PersonDot color={b.cor} />
            {b.nome}
          </span>
        ))}
        {isFetching ? (
          <span className="text-caption text-text-tertiary ml-auto">atualizando...</span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 items-stretch gap-12">
        <Panel
          wide
          title="Evolução mensal"
          note={
            mesesDistintos <= 1
              ? "Período filtrado para um único mês — amplie o período para ver a evolução ao longo do tempo."
              : undefined
          }
        >
          <MonthlyEvolutionChart data={data.evolucao_mensal} />
        </Panel>

        <Panel title="Composição por categoria">
          <CategoryCompositionChart
            data={data.composicao_categoria}
            onDrillDown={setDrillCategoriaId}
            onClearDrill={() => setDrillCategoriaId(null)}
          />
        </Panel>

        <Panel title="Divisão entre pessoas">
          <PersonSplitChart data={data.divisao_pessoas} />
        </Panel>

        <Panel title={`Orçamento do mês · ${formatCompetencia(data.orcamento.competencia)}`}>
          <BudgetProgressChart data={data.orcamento} />
        </Panel>

        <Panel title="Comparativo">
          <PeriodComparisonCards data={data.comparativo} />
        </Panel>
      </div>
    </>
  );
}

function EsqueletoAnalytics() {
  return (
    <div className="grid grid-cols-2 gap-12" aria-busy aria-label="Carregando gráficos">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className={
            "bg-surface-sunken animate-shimmer rounded-md p-9 " +
            (i === 0 ? "col-span-full h-110" : "h-90")
          }
        />
      ))}
    </div>
  );
}
