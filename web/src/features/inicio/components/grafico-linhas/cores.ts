/**
 * Cor de cada série dos gráficos de linhas do Início (D-28).
 *
 * A API manda o nome do token (`serie-1`, `serie-pix`...) e o front só o
 * traduz em classe. As classes aparecem por extenso de propósito: o Tailwind
 * só gera o que encontra escrito no código. Os tokens estão em `tokens.css`.
 * Texto nunca usa estas cores.
 */

interface ClassesDaCor {
  /** Contorno de linha ou círculo (`stroke-*`). */
  traco: string;
  /** Preenchimento de forma SVG (`fill-*`). */
  preenchimento: string;
  /** Fundo, para a bolinha da legenda (`bg-*`). */
  fundo: string;
  /** Contorno da bolinha da legenda (`border-*`). */
  borda: string;
}

const CLASSES: Record<string, ClassesDaCor> = {
  "serie-1": { traco: "stroke-serie-1", preenchimento: "fill-serie-1", fundo: "bg-serie-1", borda: "border-serie-1" },
  "serie-2": { traco: "stroke-serie-2", preenchimento: "fill-serie-2", fundo: "bg-serie-2", borda: "border-serie-2" },
  "serie-3": { traco: "stroke-serie-3", preenchimento: "fill-serie-3", fundo: "bg-serie-3", borda: "border-serie-3" },
  "serie-4": { traco: "stroke-serie-4", preenchimento: "fill-serie-4", fundo: "bg-serie-4", borda: "border-serie-4" },
  "serie-pix": {
    traco: "stroke-serie-pix",
    preenchimento: "fill-serie-pix",
    fundo: "bg-serie-pix",
    borda: "border-serie-pix",
  },
  "serie-debito": {
    traco: "stroke-serie-debito",
    preenchimento: "fill-serie-debito",
    fundo: "bg-serie-debito",
    borda: "border-serie-debito",
  },
  "serie-boleto": {
    traco: "stroke-serie-boleto",
    preenchimento: "fill-serie-boleto",
    fundo: "bg-serie-boleto",
    borda: "border-serie-boleto",
  },
  "serie-outros": {
    traco: "stroke-serie-outros",
    preenchimento: "fill-serie-outros",
    fundo: "bg-serie-outros",
    borda: "border-serie-outros",
  },
  "serie-soma": {
    traco: "stroke-serie-soma",
    preenchimento: "fill-serie-soma",
    fundo: "bg-serie-soma",
    borda: "border-serie-soma",
  },
};

/** As classes de uma cor da API; cor desconhecida cai no cinza de "outros". */
export function classesDaCor(cor: string): ClassesDaCor {
  return CLASSES[cor] ?? (CLASSES["serie-outros"] as ClassesDaCor);
}
