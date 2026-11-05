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
  /** Lançadas e pendentes (D-28). */
  valor: Dinheiro;
  /** Parte de `valor` ainda pendente no banco. */
  pendente: Dinheiro;
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

export interface DiaJanela {
  data: string;
  /** Compras no cartão lançadas, pela data da compra. */
  cartao: Dinheiro;
  /** Compras no cartão ainda pendentes no banco (só exibição, D-28). */
  cartao_pendente: Dinheiro;
  /** Pix, débito, boleto e outras despesas fora do cartão. */
  conta: Dinheiro;
  total: Dinheiro;
  /** Dia depois de hoje (faixa "a pagar"); os valores são zero. */
  a_pagar: boolean;
}

/** Pagamento de fatura que saiu da conta: uma marca, nunca somada às barras. */
export interface PagamentoJanela {
  data: string;
  valor: Dinheiro;
  cartao: string | null;
  forma_pagamento_id: number | null;
}

export interface VencimentoJanela {
  data: string;
  forma_pagamento_id: number;
  cartao: string;
  /** Compras lançadas da fatura. */
  valor: Dinheiro;
  /** Compras pendentes esperadas na fatura (além de `valor`). */
  pendente: Dinheiro;
  origem_vencimento: OrigemDatas;
}

/** Últimos 30 dias até hoje (D-28); não depende do mês escolhido. */
export interface Janela {
  inicio: string;
  hoje: string;
  fim: string;
  dias: DiaJanela[];
  pagamentos: PagamentoJanela[];
  vencimentos: VencimentoJanela[];
  total: Dinheiro;
  cartao: Dinheiro;
  cartao_pendente: Dinheiro;
  conta: Dinheiro;
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
  /** Gasto do mês pela data da compra, só lançado, até `dia_referencia`. */
  gasto_compra: Dinheiro;
  gasto_compra_mes_anterior: Dinheiro;
  diferenca_compra_mes_anterior: Dinheiro;
  /** O que já saiu da conta no mês até `dia_referencia` (D-27). */
  saiu_da_conta: Dinheiro;
  /** Faturas com vencimento no mês ainda não pagas. */
  a_pagar_mes: Dinheiro;
  janela: Janela;
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
