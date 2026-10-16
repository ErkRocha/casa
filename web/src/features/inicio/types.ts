/** Espelho de `app/schemas/inicio.py`. Dinheiro chega como texto. */

export type Dinheiro = string;

export type FaixaOrcamento = "ok" | "perto" | "estourado";
export type SituacaoMes = "corrente" | "passado" | "futuro";

export interface PontoAcumulado {
  dia: number;
  acumulado: Dinheiro;
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
  pessoas: LinhaPessoaInicio[];
  categorias: LinhaCategoriaInicio[];
  avisos: Array<AvisoOrcamento | AvisoReajuste>;
}
