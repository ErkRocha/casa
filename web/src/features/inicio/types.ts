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

/** Espelho de `app/schemas/graficos_inicio.py`. */
export type TipoSerie = "cartao" | "pix" | "debito" | "boleto" | "outros" | "soma";

export interface PontoGasto {
  data: string;
  /** Gasto desde o início da janela, com as pendentes; nunca desce. */
  acumulado: Dinheiro;
  pendente_acumulado: Dinheiro;
  /** Houve compra pendente neste dia. */
  tem_pendente: boolean;
}

export interface SerieGasto {
  /** `cartao:<id>`, `pix`, `debito`, `boleto`, `outros` ou `soma`. */
  chave: string;
  rotulo: string;
  tipo: TipoSerie;
  forma_pagamento_id: number | null;
  /** Nome do token de cor: `serie-1`..`serie-4`, `serie-pix`... */
  cor: string;
  visivel: boolean;
  total: Dinheiro;
  pendente: Dinheiro;
  pontos: PontoGasto[];
}

export interface PessoaConectada {
  id: number;
  nome: string;
}

/** Gasto acumulado dos últimos 30 dias até hoje, uma linha por forma de pagar. */
export interface GastosJanela {
  inicio: string;
  hoje: string;
  series: SerieGasto[];
  soma: SerieGasto | null;
  total: Dinheiro;
  pendente: Dinheiro;
  pessoas_conectadas: PessoaConectada[];
  pessoa_id: number | null;
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

/** Espelho de `CicloFatura` em `app/schemas/graficos_inicio.py` (gráfico das faturas). */
export type OrigemData = "pluggy_fatura" | "pluggy_conta" | "cadastro" | "derivada";

export interface PontoCiclo {
  data: string;
  /** Compras do ciclo até o dia; no dia do pagamento há dois pontos (antes e zero). */
  valor: Dinheiro;
  /** Dia depois de hoje: o que ainda vai acontecer. */
  tracejado: boolean;
}

export interface CicloFatura {
  /** `ciclo:<forma_pagamento_id>:<AAAA-MM-DD do fechamento>`. */
  chave: string;
  forma_pagamento_id: number;
  cartao: string;
  /** Token de cor do cartão (o mesmo do gráfico de gastos). */
  cor: string;
  /** Primeiro dia do mês do vencimento. */
  mes_fatura: string;
  abertura: string;
  fechamento: string;
  vencimento: string;
  pago_em: string | null;
  valor: Dinheiro;
  pendente: Dinheiro;
  /** Ciclo de maior fechamento do cartão; os outros são anteriores. */
  atual: boolean;
  situacao: "aberta" | "fechada" | "paga";
  origem_abertura: OrigemData;
  origem_fechamento: OrigemData;
  origem_vencimento: OrigemData;
  origem_pagamento: "identificado" | null;
  pontos: PontoCiclo[];
}

/** Os ciclos de fatura dos últimos 30 dias até o último vencimento dos próximos 15. */
export interface FaturasCiclos {
  inicio: string;
  hoje: string;
  fim: string;
  ciclos: CicloFatura[];
}
