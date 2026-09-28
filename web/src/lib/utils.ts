import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Helper padrão do shadcn/ui: junta classes e resolve conflitos do Tailwind. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
