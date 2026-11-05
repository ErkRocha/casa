/** Espelho de `app/schemas/inicio.py`. Dinheiro chega como texto. */

export type Dinheiro = string;

export type FaixaOrcamento = "ok" | "perto" | "estourado";
export type SituacaoMes = "corrente" | "passado" | "futuro";

export type OrigemDatas = "pluggy_fatura" | "pluggy_conta" | "cadastro";

export interface PontoAcumulado {
  dia: number;
  /** O que já saiu da conta até o dia. */
  acumulado: Dinheiro;
  /** `acumulado` mais faturas a pagar e despesas futuras até o dia. */
  com_a_pagar: Dinheiro;
}

export interface FaturaMes {
  forma_pagamento_id: number;
  cartao: string;
  valor: Dinheiro;
  dia: number;
  situacao: "paga" | "a_pagar";
  vencimento: string;
  pago_em: string | null;
  origem_vencimento: OrigemDatas;
}

export interface PontoEvolucao {
  data: string;
  acumulado: Dinheiro;
}

export interface FaturaAberta {
  forma_pagamento_id: number;
  cartao: string;
  valor: Dinheiro;
  desde: string;
  fecha: string;
  vence: string | null;
  origem_datas: OrigemDatas;
  evolucao: PontoEvolucao[];
}

export interface OrcamentoInicio {
  total: Dinheiro;
  percentual_usado: number;
  faixa: FaixaOrcamento;
}

export interface PrevisaoInicio {
  valor: Dinheiro;
  comprometido: Dinheiro;
  diferenca_orcamento: Dinheiro | null;
}

export interface LinhaPessoaInicio {
  /** Id da pessoa (como texto) ou `conjunto`. */
  balde: string;
  nome: string;
  valor: Dinheiro;
  percentual: number;
}

export interface LinhaCategoriaInicio {
  categoria_id: number | null;
  nome: string;
  valor: Dinheiro;
  percentual: number;
  largura: number;
}

export interface AvisoOrcamento {
  tipo: "orcamento";
  categoria: string;
  percentual: Dinheiro;
  realizado: Dinheiro;
  meta: Dinheiro;
  situacao: "atencao" | "estourado";
  dias_restantes: number | null;
}

export interface AvisoReajuste {
  tipo: "reajuste";
  descricao: string;
  valor_anterior: Dinheiro;
  valor_atual: Dinheiro;
}

export interface Inicio {
  competencia: string;
  situacao: SituacaoMes;
  dias_no_mes: number;
  dia_referencia: number;
  tem_dados: boolean;
  gasto: Dinheiro;
  gasto_mes_anterior: Dinheiro;
  diferenca_mes_anterior: Dinheiro;
  receitas: Dinheiro;
  sobra: Dinheiro;
  orcamento: OrcamentoInicio | null;
  previsao: PrevisaoInicio | null;
  serie: PontoAcumulado[];
  faturas: FaturaMes[];
  faturas_abertas: FaturaAberta[];
  pessoas: LinhaPessoaInicio[];
  categorias: LinhaCategoriaInicio[];
  avisos: Array<AvisoOrcamento | AvisoReajuste>;
}
