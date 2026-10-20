import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Card } from "@/components/ui/card";
import { AnalisesPage } from "@/features/analytics/analises-page";
import { ImportacoesPage } from "@/features/ingestao/importacoes-page";
import { InicioPage } from "@/features/inicio/inicio-page";
import { MaisPage } from "@/features/navegacao/mais-page";
import { RegrasPage } from "@/features/regras/regras-page";
import { RelatoriosPage } from "@/features/relatorios/relatorios-page";
import { RevisarPage } from "@/features/revisar/revisar-page";
import { LancamentosPage } from "@/features/transacoes/lancamentos-page";
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
  switch (rota) {
    case "inicio":
      return <InicioPage />;
    case "mais":
      return <MaisPage />;
    case "lancamentos":
      return <LancamentosPage />;
    case "analises":
      return <AnalisesPage />;
    case "relatorios":
      return <RelatoriosPage />;
    case "categorias":
      return (
        <TelaAnterior rota={rota}>
          <RegrasPage />
        </TelaAnterior>
      );
    case "revisar":
      return <RevisarPage />;
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
  children,
}: {
  rota: Rota;
  acao?: ReactNode;
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
      <div>{children}</div>
    </div>
  );
}
