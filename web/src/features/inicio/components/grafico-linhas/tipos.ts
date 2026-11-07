import type { Dinheiro } from "../../types";

/** Um ponto de uma linha esparsa: o dia (índice em `dias`) e o valor. */
export interface PontoDaLinha {
  i: number;
  valor: number;
  /** O trecho que chega a este ponto é tracejado (ainda vai acontecer). */
  tracejado: boolean;
}

/**
 * Uma linha pronta para desenhar. Os valores acumulados chegam do banco; aqui
 * viram número só para virar coordenada (`valores`). Os textos de dinheiro
 * (`acumulado`, `pendenteAcumulado`) seguem como a API mandou.
 *
 * Os campos opcionais servem ao gráfico das faturas, cujas linhas começam e
 * terminam em dias diferentes. Sem eles a linha é a de sempre: um valor por dia.
 */
export interface LinhaGrafico {
  chave: string;
  rotulo: string;
  /** Nome curto, para o fim da linha. */
  rotuloCurto: string;
  /** Token de cor (`serie-1`...). */
  cor: string;
  /** Um por dia: o valor da linha (coordenada y). */
  valores: number[];
  acumulado: Dinheiro[];
  pendenteAcumulado: Dinheiro[];
  /** Um por dia: houve compra pendente (ponto vazado). */
  temPendente: boolean[];
  /**
   * Pontos esparsos, em ordem; o mesmo dia pode aparecer duas vezes (queda
   * vertical). Quando existem, desenham a linha no lugar de `valores`.
   */
  pontos?: PontoDaLinha[];
  /** Um por dia: a linha existe neste dia (fora dele não há marca nem painel). */
  existe?: boolean[];
  /** 0 a 1; padrão 1. */
  opacidade?: number;
  /** Texto de apoio no painel do dia (ex.: "vence 09/11"). */
  nota?: string;
  /** Onde o rótulo do fim fica e o valor que ele mostra; padrão: o último dia. */
  fim?: { i: number; valor: number; texto: string };
  /** Não recebe rótulo no fim. */
  semRotulo?: boolean;
}
