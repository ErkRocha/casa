import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Bloco do desenho (D-22): superfície branca, raio 20px. Tudo no painel é um
 * bloco destes sobre o fundo `#EEF1F6`.
 */

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("bg-superficie rounded-bloco overflow-hidden", className)}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-2", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

/** Título de bloco: 18px/650, sem caixa alta (README). */
const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("text-bloco font-forte text-texto", className)}
      {...props}
    />
  ),
);
CardTitle.displayName = "CardTitle";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

/**
 * Cabeçalho de bloco das pranchetas: título à esquerda e, na linha de base,
 * um texto de apoio ou um link à direita ("Ver análise", "dia 16 de 31").
 */
function CabecalhoBloco({
  titulo,
  direita,
  nivel = "h2",
  className,
}: {
  titulo: React.ReactNode;
  direita?: React.ReactNode;
  nivel?: "h2" | "h3";
  className?: string;
}) {
  const Titulo = nivel;
  return (
    <div className={cn("flex flex-wrap items-baseline justify-between gap-4", className)}>
      <Titulo className="text-bloco-celular md:text-bloco font-forte m-0">{titulo}</Titulo>
      {direita ? <span className="text-apoio text-texto-2">{direita}</span> : null}
    </div>
  );
}

export { CabecalhoBloco, Card, CardContent, CardHeader, CardTitle };
