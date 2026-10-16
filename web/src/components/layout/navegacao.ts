import type { NomeIcone } from "@/components/ui/icone";
import type { Rota } from "@/lib/rotas";

/**
 * Os itens de navegação do README do desenho (D-22).
 *
 * Computador: três grupos sem rótulo, separados por espaço. Celular: quatro
 * itens na barra inferior e "Mais" para as telas de configuração.
 */

export interface ItemNavegacao {
  rota: Rota;
  rotulo: string;
  icone: NomeIcone;
}

const ITENS: Record<Exclude<Rota, "mais">, ItemNavegacao> = {
  inicio: { rota: "inicio", rotulo: "Início", icone: "inicio" },
  lancamentos: { rota: "lancamentos", rotulo: "Lançamentos", icone: "lancamentos" },
  revisar: { rota: "revisar", rotulo: "Revisar", icone: "revisar" },
  analises: { rota: "analises", rotulo: "Análises", icone: "analises" },
  relatorios: { rota: "relatorios", rotulo: "Relatórios do mês", icone: "relatorios" },
  contas: { rota: "contas", rotulo: "Contas e cartões", icone: "contas" },
  categorias: { rota: "categorias", rotulo: "Categorias", icone: "categorias" },
  sincronizacao: { rota: "sincronizacao", rotulo: "Sincronização", icone: "sincronizacao" },
};

export const GRUPOS_COMPUTADOR: ItemNavegacao[][] = [
  [ITENS.inicio, ITENS.lancamentos, ITENS.revisar],
  [ITENS.analises, ITENS.relatorios],
  [ITENS.contas, ITENS.categorias, ITENS.sincronizacao],
];

export const ITENS_CELULAR: ItemNavegacao[] = [
  ITENS.inicio,
  ITENS.lancamentos,
  ITENS.revisar,
  ITENS.analises,
  { rota: "mais", rotulo: "Mais", icone: "mais" },
];

/** As telas que no celular ficam atrás de "Mais". */
export const ITENS_MAIS: ItemNavegacao[] = [
  ITENS.relatorios,
  ITENS.contas,
  ITENS.categorias,
  ITENS.sincronizacao,
];

/** "Mais" fica ativo quando a tela atual é uma das que ele guarda. */
export function rotaAtivaNoCelular(rota: Rota): Rota {
  return ITENS_MAIS.some((item) => item.rota === rota) ? "mais" : rota;
}
