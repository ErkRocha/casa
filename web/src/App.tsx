import { useState, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/controls";
import { AnalyticsPage } from "@/features/analytics/analytics-page";
import { ActiveChips } from "@/features/filters/active-chips";
import { FilterBar } from "@/features/filters/filter-bar";
import { ImportacoesPage } from "@/features/ingestao/importacoes-page";
import { InicioPage } from "@/features/inicio/inicio-page";
import { MaisPage } from "@/features/navegacao/mais-page";
import { RegrasPage } from "@/features/regras/regras-page";
import { RelatoriosPage } from "@/features/relatorios/relatorios-page";
import { TransacoesPage } from "@/features/transacoes/transacoes-page";
import { TITULO_DA_ROTA, useRota, type Rota } from "@/lib/rotas";

/**
 * As telas por endereço (D-22).
 *
 * O redesenho entra por fases. As telas que ainda não foram redesenhadas
 * aparecem dentro de `TelaAnterior`, com o título no estilo novo; cada fase
 * troca uma delas pela versão nova.
 */
export default function App() {
  const rota = useRota();
  return (
    <AppShell rota={rota}>
      <Tela rota={rota} />
    </AppShell>
  );
}

function Tela({ rota }: { rota: Rota }) {
  const [drawerAberto, setDrawerAberto] = useState(false);

  switch (rota) {
    case "inicio":
      return <InicioPage />;
    case "mais":
      return <MaisPage />;
    case "lancamentos":
      return (
        <TelaAnterior
          rota={rota}
          acao={<Button onClick={() => setDrawerAberto(true)}>Novo lançamento</Button>}
          filtro
        >
          <TransacoesPage
            drawerAberto={drawerAberto}
            onAbrirDrawer={() => setDrawerAberto(true)}
            onFecharDrawer={() => setDrawerAberto(false)}
          />
        </TelaAnterior>
      );
    case "analises":
      return (
        <TelaAnterior rota={rota} filtro>
          <AnalyticsPage />
        </TelaAnterior>
      );
    case "relatorios":
      return (
        <TelaAnterior rota={rota}>
          <RelatoriosPage />
        </TelaAnterior>
      );
    case "categorias":
      return (
        <TelaAnterior rota={rota}>
          <RegrasPage />
        </TelaAnterior>
      );
    case "revisar":
    case "sincronizacao":
      return (
        <TelaAnterior rota={rota}>
          <ImportacoesPage />
        </TelaAnterior>
      );
    case "contas":
      return (
        <TelaAnterior rota={rota}>
          <Card className="px-11 py-10">
            <p className="text-corpo text-texto-2 m-0">
              Contas e cartões entram na fase de configurações do redesenho.
            </p>
          </Card>
        </TelaAnterior>
      );
  }
}

/** Tela do visual anterior, com o cabeçalho no estilo novo. Sai por fases. */
function TelaAnterior({
  rota,
  acao,
  filtro = false,
  children,
}: {
  rota: Rota;
  acao?: ReactNode;
  filtro?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex max-w-[1100px] flex-col gap-8">
      <header className="flex flex-wrap items-center gap-5">
        <h1 className="text-pagina-celular md:text-pagina m-0 flex-1 font-bold tracking-[-0.4px]">
          {TITULO_DA_ROTA[rota]}
        </h1>
        {acao}
      </header>
      {filtro ? (
        <div className="bg-superficie rounded-bloco">
          <FilterBar />
          <ActiveChips />
        </div>
      ) : null}
      <div>{children}</div>
    </div>
  );
}
