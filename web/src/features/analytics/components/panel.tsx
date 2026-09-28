import type { ReactNode } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Painel da grade de Analytics (`S.panel` / `S.panelWide`).
 * `wide` ocupa a linha inteira — é o caso da evolução mensal.
 */
export function Panel({
  title,
  note,
  wide = false,
  children,
  className,
}: {
  title: ReactNode;
  /** Aviso curto sob o título, ex.: período com um mês só. */
  note?: ReactNode;
  wide?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card
      className={cn(
        "flex flex-col p-9",
        wide && "col-span-full",
        className,
      )}
    >
      <CardTitle className="mb-9">{title}</CardTitle>
      {note ? <p className="text-body-sm text-text-tertiary mb-5">{note}</p> : null}
      {children}
    </Card>
  );
}
