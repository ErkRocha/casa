import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Controles de formulário no padrão shadcn/ui (forwardRef + `cn`), com os
 * tokens deste design.
 *
 * Nada de Radix aqui: o protótipo usa `<select>` e `<input>` nativos e
 * popover posicionado na mão. Manter isso evita cinco dependências para
 * reproduzir o que o navegador já faz, e o teclado funciona de graça.
 */

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "bg-surface-sunken text-text-primary placeholder:text-text-tertiary",
        "text-body rounded-lg border-none px-5 py-3.5 outline-none",
        "focus-visible:ring-accent focus-visible:ring-1",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Select = React.forwardRef<HTMLSelectElement, React.ComponentProps<"select">>(
  ({ className, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "bg-surface-sunken text-text-primary text-body cursor-pointer",
        "rounded-lg border-none px-4 py-3 outline-none",
        "focus-visible:ring-accent focus-visible:ring-1",
        className,
      )}
      {...props}
    />
  ),
);
Select.displayName = "Select";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "filter" | "filterActive";

const VARIANTES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-accent-fg font-semibold",
  secondary: "bg-surface text-text-primary font-semibold",
  ghost: "bg-transparent text-text-secondary hover:text-text-primary",
  danger: "bg-transparent text-expense font-semibold",
  filter: "bg-surface-sunken text-text-secondary",
  filterActive: "bg-surface text-text-primary",
};

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> & { variant?: ButtonVariant }
>(({ className, variant = "primary", type = "button", ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    className={cn(
      "text-body cursor-pointer rounded-lg px-7 py-4 whitespace-nowrap",
      "disabled:cursor-not-allowed disabled:opacity-50",
      VARIANTES[variant],
      className,
    )}
    {...props}
  />
));
Button.displayName = "Button";

export const Checkbox = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn("accent-accent size-6 cursor-pointer", className)}
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";

/**
 * Popover ancorado, fechando por clique fora e Esc.
 *
 * `onClose` roda no `pointerdown` do documento — usar `click` deixaria o
 * mesmo clique que abriu o popover fechá-lo em seguida.
 */
export function Popover({
  aberto,
  onClose,
  children,
  className,
}: {
  aberto: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!aberto) return;

    function aoClicarFora(evento: PointerEvent) {
      if (ref.current && !ref.current.contains(evento.target as Node)) onClose();
    }
    function aoTeclar(evento: KeyboardEvent) {
      if (evento.key === "Escape") onClose();
    }

    document.addEventListener("pointerdown", aoClicarFora);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("pointerdown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto, onClose]);

  if (!aberto) return null;

  return (
    <div
      ref={ref}
      className={cn(
        "bg-surface border-border-faint shadow-popover absolute top-[calc(100%+4px)] left-0 z-20",
        "min-w-100 rounded-xl border p-3",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Caixinha de seleção múltipla dos popovers de filtro. */
export function CheckBox({ marcado }: { marcado: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-6 shrink-0 rounded-sm border-[1.5px]",
        marcado ? "bg-accent border-accent" : "border-border bg-transparent",
      )}
    />
  );
}

/** Badge de pessoa na tabela — fundo suave, texto na cor da série. */
export function PessoaBadge({
  nome,
  fundo,
  cor,
  onClick,
}: {
  nome: string;
  fundo: string;
  cor: string;
  onClick?: () => void;
}) {
  return (
    <span
      onClick={onClick}
      className={cn(
        "text-caption inline-block rounded-md px-4 py-1.5 font-semibold",
        onClick && "cursor-pointer",
      )}
      style={{ background: fundo, color: cor }}
    >
      {nome}
    </span>
  );
}
