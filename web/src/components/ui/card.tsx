import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Primitiva de superfície no padrão shadcn/ui, com os tokens deste design.
 * O protótipo chama de `S.card` (tabela) e `S.panel` (analytics): mesma
 * superfície `surface-sunken` com raio 4px, o que muda é o padding.
 */

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("bg-surface-sunken rounded-md overflow-hidden", className)}
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

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "text-caption font-semibold uppercase tracking-caps-wide text-text-tertiary",
        className,
      )}
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

export { Card, CardContent, CardHeader, CardTitle };
