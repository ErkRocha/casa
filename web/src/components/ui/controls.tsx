import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Controles de formulário no padrão shadcn/ui (forwardRef + `cn`), com os
 * tokens do desenho (D-22): alvo de toque de 44px, raio interno de 12px.
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
        "bg-superficie-2 text-texto placeholder:text-texto-2",
        "text-corpo rounded-interno min-h-22 border-none px-7 outline-none",
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
        "bg-superficie-2 text-texto text-apoio cursor-pointer",
        "rounded-interno min-h-22 border-none px-6 outline-none",
        className,
      )}
      {...props}
    />
  ),
);
Select.displayName = "Select";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "filter" | "filterActive";

const VARIANTES: Record<ButtonVariant, string> = {
  primary: "bg-destaque hover:bg-destaque-hover font-forte text-white",
  secondary:
    "bg-superficie text-texto font-semibold shadow-[inset_0_0_0_1px_var(--color-contorno)]",
  ghost: "bg-transparent text-texto-2 hover:text-texto",
  danger: "bg-transparent text-perigo font-semibold",
  filter: "bg-superficie-2 text-texto",
  filterActive: "bg-texto font-semibold text-white",
};

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<"button"> & { variant?: ButtonVariant }
>(({ className, variant = "primary", type = "button", ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    className={cn(
      "text-apoio rounded-interno inline-flex min-h-22 cursor-pointer items-center",
      "justify-center gap-4 border-none px-8 whitespace-nowrap",
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
      className={cn("accent-destaque size-9 cursor-pointer", className)}
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
        "bg-superficie shadow-popover absolute top-[calc(100%+4px)] left-0 z-20",
        "rounded-interno min-w-120 p-3",
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
        "inline-block size-9 shrink-0 rounded-[5px] border-[1.5px]",
        marcado ? "bg-destaque border-destaque" : "border-caixa bg-superficie",
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
        "text-pequeno rounded-selo inline-block px-4 py-1 font-semibold",
        onClick && "cursor-pointer",
      )}
      style={{ background: fundo, color: cor }}
    >
      {nome}
    </span>
  );
}


type TomSelo = "atencao" | "atencaoSolido" | "receita" | "destaque" | "neutro" | "inativo";

const TONS_SELO: Record<TomSelo, string> = {
  atencao: "bg-atencao-fundo text-atencao-texto",
  atencaoSolido: "bg-atencao-selo text-white",
  receita: "bg-receita-fundo text-receita-texto",
  destaque: "bg-destaque-fundo text-destaque-hover",
  neutro: "bg-superficie-2 text-texto-apoio",
  inativo: "bg-transparent text-texto-inativo",
};

/** Selo das pranchetas: 13px/650, raio 6px ("Reajuste", "Sincronizando"). */
export function Selo({
  tom = "neutro",
  className,
  children,
}: {
  tom?: TomSelo;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "text-pequeno font-forte rounded-selo inline-block px-4 py-0.5 leading-snug",
        TONS_SELO[tom],
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * Botão só com ícone, 44px (o alvo mínimo do README). `rotulo` vira o
 * `aria-label`: sem ele o leitor de tela anunciaria só "botão".
 */
export const BotaoIcone = React.forwardRef<
  HTMLButtonElement,
  Omit<React.ComponentProps<"button">, "aria-label"> & { rotulo: string }
>(({ rotulo, className, type = "button", ...props }, ref) => (
  <button
    ref={ref}
    type={type}
    aria-label={rotulo}
    title={rotulo}
    className={cn(
      "bg-superficie text-texto rounded-interno flex size-22 shrink-0 cursor-pointer",
      "items-center justify-center border-none",
      "disabled:cursor-not-allowed disabled:opacity-40",
      className,
    )}
    {...props}
  />
));
BotaoIcone.displayName = "BotaoIcone";
