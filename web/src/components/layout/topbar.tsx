import type { ReactNode } from "react";

/**
 * Cabeçalho da área de conteúdo: título da tela à esquerda, ação primária à
 * direita (`S.topbar` do protótipo).
 */
export function Topbar({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <header className="flex items-center justify-between px-14 pt-16 pb-10">
      <h1 className="text-display text-text-primary tracking-tight font-bold">{title}</h1>
      {action}
    </header>
  );
}

/** Botão de ação primária (`S.primaryBtn`). */
export function PrimaryButton({
  children,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      className="bg-accent text-accent-fg text-body-lg cursor-pointer rounded-lg px-7 py-4 font-semibold"
    >
      {children}
    </button>
  );
}
