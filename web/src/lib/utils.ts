import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * O `tailwind-merge` com os nomes dos tokens do desenho (D-22).
 *
 * Sem isto ele lê `text-corpo` como cor (só conhece os tamanhos `text-sm`,
 * `text-lg`...) e, ao juntar `text-white` com `text-corpo`, joga fora o
 * branco: o texto do botão azul saía escuro. O mesmo para peso (`font-forte`)
 * e raio (`rounded-bloco`).
 */
const juntar = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "numero-grande",
            "numero",
            "pagina",
            "pagina-celular",
            "valor",
            "valor-medio",
            "bloco",
            "bloco-celular",
            "enfase",
            "corpo",
            "apoio",
            "pequeno",
            "selo",
          ],
        },
      ],
      "font-weight": [{ font: ["medio", "forte"] }],
      rounded: [
        { rounded: ["bloco", "cartao", "sub", "interno", "botao", "campo", "selo"] },
      ],
      shadow: [{ shadow: ["flutuante"] }],
    },
  },
});

/** Helper padrão do shadcn/ui: junta classes e resolve conflitos do Tailwind. */
export function cn(...inputs: ClassValue[]) {
  return juntar(clsx(inputs));
}
