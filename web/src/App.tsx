import { AppShell } from "@/components/layout/app-shell";
import { AnalisesPage } from "@/features/analytics/analises-page";
import { ComprasPage, DespensaPage } from "@/features/compras/compras-page";
import { CategoriasPage } from "@/features/configuracoes/categorias-page";
import { ContasPage } from "@/features/configuracoes/contas-page";
import { SincronizacaoPage } from "@/features/configuracoes/sincronizacao-page";
import { InicioPage } from "@/features/inicio/inicio-page";
import { MaisPage } from "@/features/navegacao/mais-page";
import { RelatoriosPage } from "@/features/relatorios/relatorios-page";
import { RevisarPage } from "@/features/revisar/revisar-page";
import { LancamentosPage } from "@/features/transacoes/lancamentos-page";
import { useRota, type Rota } from "@/lib/rotas";

/** As telas por endereço (D-24), cada uma no desenho de `docs/design/`. */
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
    case "lancamentos":
      return <LancamentosPage />;
    case "compras":
      return <ComprasPage />;
    case "despensa":
      return <DespensaPage />;
    case "revisar":
      return <RevisarPage />;
    case "analises":
      return <AnalisesPage />;
    case "relatorios":
      return <RelatoriosPage />;
    case "contas":
      return <ContasPage />;
    case "categorias":
      return <CategoriasPage />;
    case "sincronizacao":
      return <SincronizacaoPage />;
    case "mais":
      return <MaisPage />;
  }
}
