import { useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import type { ScreenId } from "@/components/layout/sidebar";
import { PrimaryButton, Topbar } from "@/components/layout/topbar";
import { AnalyticsPage } from "@/features/analytics/analytics-page";
import { ActiveChips } from "@/features/filters/active-chips";
import { FilterBar } from "@/features/filters/filter-bar";
import { ImportacoesPage } from "@/features/ingestao/importacoes-page";
import { RegrasPage } from "@/features/regras/regras-page";
import { RelatoriosPage } from "@/features/relatorios/relatorios-page";
import { TransacoesPage } from "@/features/transacoes/transacoes-page";

const TITULOS: Record<ScreenId, string> = {
  transacoes: "Transações",
  analytics: "Analytics",
  importacoes: "Importar",
  regras: "Regras de categorização",
  relatorios: "Relatórios do mês",
};

/**
 * A barra de filtro fica acima de Transações e Analytics, no cabeçalho fixo.
 * Trocar entre essas duas mantém o recorte — é o que "filtros compartilhados"
 * quer dizer.
 *
 * A tela de importação não usa filtro: ela é sobre um arquivo específico, e
 * mostrar a barra ali só sugeriria que o recorte muda alguma coisa.
 */
export default function App() {
  const [tela, setTela] = useState<ScreenId>("transacoes");
  const [drawerAberto, setDrawerAberto] = useState(false);

  const usaFiltro = tela === "transacoes" || tela === "analytics";

  return (
    <AppShell
      activeScreen={tela}
      onNavigate={setTela}
      header={
        <>
          <Topbar
            title={TITULOS[tela]}
            action={
              tela === "importacoes" || tela === "regras" || tela === "relatorios" ? undefined : (
                <PrimaryButton onClick={() => setDrawerAberto(true)}>
                  + Nova transação
                </PrimaryButton>
              )
            }
          />
          {usaFiltro ? (
            <>
              <FilterBar />
              <ActiveChips />
            </>
          ) : null}
        </>
      }
    >
      {tela === "analytics" ? (
        <AnalyticsPage />
      ) : tela === "importacoes" ? (
        <ImportacoesPage />
      ) : tela === "regras" ? (
        <RegrasPage />
      ) : tela === "relatorios" ? (
        <RelatoriosPage />
      ) : (
        <TransacoesPage
          drawerAberto={drawerAberto}
          onAbrirDrawer={() => setDrawerAberto(true)}
          onFecharDrawer={() => setDrawerAberto(false)}
        />
      )}
    </AppShell>
  );
}
