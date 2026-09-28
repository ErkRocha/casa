import type { ReactNode } from "react";

import { Sidebar, type ScreenId } from "@/components/layout/sidebar";

/**
 * Casca da aplicação: sidebar fixa + coluna de conteúdo que rola sozinha
 * (`S.page` / `S.main` / `S.contentScroll` do protótipo).
 *
 * Só a região `<main>` rola — a topbar e a barra de filtro ficam presas, que
 * é o que permite mexer no filtro sem perder o gráfico de vista.
 */
export function AppShell({
  activeScreen,
  onNavigate,
  header,
  children,
}: {
  activeScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
  /** Topbar, barra de filtro, chips — tudo que não deve rolar. */
  header?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="bg-bg text-text-primary font-sans text-body-lg flex h-screen w-full overflow-hidden">
      <Sidebar activeScreen={activeScreen} onNavigate={onNavigate} />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {header}
        <main className="flex-1 overflow-auto px-14 pb-16">{children}</main>
      </div>
    </div>
  );
}
