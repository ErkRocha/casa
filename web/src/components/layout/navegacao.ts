import type { NomeIcone } from "@/components/ui/icone";
import type { Rota } from "@/lib/rotas";

/**
 * Os itens de navegação do README do desenho (D-24).
 *
 * Computador: três grupos sem rótulo, separados por espaço; Compras no
 * primeiro, depois de Lançamentos. Celular: cinco itens na barra inferior,
 * com Compras no meio (docs/design/COMPRAS.md); as telas de configuração
 * ficam em "Mais", aberto pelo topo do Início.
 */

export interface ItemNavegacao {
  rota: Rota;
  rotulo: string;
  icone: NomeIcone;
}

const ITENS: Record<Exclude<Rota, "mais" | "despensa">, ItemNavegacao> = {
  inicio: { rota: "inicio", rotulo: "Início", icone: "inicio" },
  lancamentos: { rota: "lancamentos", rotulo: "Lançamentos", icone: "lancamentos" },
  compras: { rota: "compras", rotulo: "Compras", icone: "compras" },
  revisar: { rota: "revisar", rotulo: "Revisar", icone: "revisar" },
  analises: { rota: "analises", rotulo: "Análises", icone: "analises" },
  relatorios: { rota: "relatorios", rotulo: "Relatórios do mês", icone: "relatorios" },
  contas: { rota: "contas", rotulo: "Contas e cartões", icone: "contas" },
  categorias: { rota: "categorias", rotulo: "Categorias", icone: "categorias" },
  sincronizacao: { rota: "sincronizacao", rotulo: "Sincronização", icone: "sincronizacao" },
};

export const GRUPOS_COMPUTADOR: ItemNavegacao[][] = [
  [ITENS.inicio, ITENS.lancamentos, ITENS.compras, ITENS.revisar],
  [ITENS.analises, ITENS.relatorios],
  [ITENS.contas, ITENS.categorias, ITENS.sincronizacao],
];

export const ITENS_CELULAR: ItemNavegacao[] = [
  ITENS.inicio,
  ITENS.lancamentos,
  ITENS.compras,
  ITENS.revisar,
  ITENS.analises,
];

/** As telas que no celular ficam atrás de "Mais". */
export const ITENS_MAIS: ItemNavegacao[] = [
  ITENS.relatorios,
  ITENS.contas,
  ITENS.categorias,
  ITENS.sincronizacao,
];

/** A despensa é parte de Compras: o item ativo é o de Compras. */
export function rotaAtiva(rota: Rota): Rota {
  return rota === "despensa" ? "compras" : rota;
}
