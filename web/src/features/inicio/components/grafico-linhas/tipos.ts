import type { Dinheiro } from "../../types";

/**
 * Uma linha pronta para desenhar. Os valores acumulados chegam do banco; aqui
 * viram número só para virar coordenada (`valores`). Os textos de dinheiro
 * (`acumulado`, `pendenteAcumulado`) seguem como a API mandou.
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
}
