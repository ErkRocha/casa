import { PersonLegend } from "@/components/layout/person-legend";
import { useTheme } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

/**
 * Navegação lateral. Espelha `S.sidebar` do protótipo: 208px fixos, logo,
 * lista de telas, legenda de pessoas presa ao rodapé e o botão de tema.
 *
 * As telas ainda não implementadas aparecem desabilitadas com "em breve" —
 * é o próprio protótipo sinalizando o que é fase futura do roadmap.
 */

export type ScreenId = "transacoes" | "analytics" | "importacoes" | "regras";

interface NavItem {
  id: ScreenId;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "transacoes", label: "Transações" },
  { id: "analytics", label: "Analytics" },
  { id: "importacoes", label: "Importar" },
  { id: "regras", label: "Regras" },
];

const SOON_ITEMS = ["Orçamentos", "Relatórios"];

export function Sidebar({
  activeScreen,
  onNavigate,
}: {
  activeScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
}) {
  const { theme, toggleTheme } = useTheme();

  return (
    <nav className="bg-bg border-border-faint flex w-104 shrink-0 flex-col border-r px-7 py-10">
      <div className="flex items-center gap-5 px-4 pt-2 pb-12">
        <div className="bg-accent size-8 shrink-0 rounded-sm" aria-hidden />
        <div className="text-body-sm text-text-primary leading-tight font-semibold">
          Finanças
          <br />
          de Casa
        </div>
      </div>

      <div className="flex flex-col gap-px">
        {NAV_ITEMS.map((item) => {
          const isActive = item.id === activeScreen;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={isActive ? "page" : undefined}
              onClick={() => onNavigate(item.id)}
              className={cn(
                "text-body-lg cursor-pointer rounded-md px-5 py-4 text-left font-medium",
                isActive
                  ? "bg-surface-sunken text-text-primary font-semibold"
                  : "text-text-secondary hover:text-text-primary",
              )}
            >
              {item.label}
            </button>
          );
        })}

        {SOON_ITEMS.map((label) => (
          <div
            key={label}
            aria-disabled
            className="text-body-lg text-text-tertiary flex items-center justify-between px-5 py-4"
          >
            {label}
            <span className="text-tag tracking-label-wide uppercase">em breve</span>
          </div>
        ))}
      </div>

      <div className="flex-1" />

      <div className="border-border-faint mb-5 border-t px-5 py-7">
        <div className="text-label text-text-tertiary tracking-caps-wide mb-5 font-semibold uppercase">
          Pessoas
        </div>
        <PersonLegend orientation="vertical" />
      </div>

      <button
        type="button"
        onClick={toggleTheme}
        className="text-body-sm text-text-tertiary hover:text-text-secondary cursor-pointer rounded-md px-5 py-4 text-left"
      >
        {theme === "light" ? "Modo escuro" : "Modo claro"}
      </button>
    </nav>
  );
}
