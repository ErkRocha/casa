/** Espelho de `compras/compras/schemas_cardapio.py` (D-30). Decimais chegam como texto. */

export type TipoRefeicao = "cafe_da_manha" | "lanche" | "almoco" | "janta";
export type UnidadeMedida =
  | "g"
  | "kg"
  | "ml"
  | "l"
  | "un"
  | "colher_sopa"
  | "colher_cha"
  | "xicara"
  | "a_gosto";
export type MedidaBase = "g" | "ml" | "un";

interface Linha {
  id: number;
  criado_em: string;
  atualizado_em: string;
  deleted_em: string | null;
}

// --- Pessoas -----------------------------------------------------------------

export interface Pessoa extends Linha {
  nome: string;
  porcao_padrao: string;
  identidade_id: number | null;
  login: string | null;
}

export interface PessoaNaRefeicao {
  pessoa_id: number;
  nome: string;
  /** A porção efetiva: o ajuste, ou a padrão da pessoa. */
  porcoes: string;
  ajustada: boolean;
}

// --- Semana ------------------------------------------------------------------

export interface ReceitaNaRefeicao {
  id: number;
  nome: string;
  rendimento_porcoes: string;
  tempo_preparo_min: number | null;
  apagada: boolean;
}

export interface Refeicao extends Linha {
  semana_id: number;
  dia: string;
  tipo: TipoRefeicao;
  receita: ReceitaNaRefeicao | null;
  observacao: string | null;
  ordem: number;
  pessoas: PessoaNaRefeicao[];
  porcoes: string;
  fator: string | null;
}

export interface DiaDaSemana {
  dia: string;
  refeicoes: Refeicao[];
}

export interface Sessao extends Linha {
  semana_id: number;
  data: string;
  rotulo: string | null;
}

export interface Semana extends Linha {
  inicio: string;
  observacao: string | null;
  passada: boolean;
  dias: DiaDaSemana[];
  sessoes: Sessao[];
}

export interface SemanaCopiada extends Semana {
  avisos: Array<{ refeicao_id: number; texto: string }>;
}

// --- Receitas ----------------------------------------------------------------

export interface ReceitaResumo extends Linha {
  nome: string;
  tipo: TipoRefeicao;
  rendimento_porcoes: string;
  tempo_preparo_min: number | null;
  pode_antecipar: boolean;
  dura_dias: number | null;
  pode_congelar: boolean;
  id_cliente: string | null;
  quantidades_revisadas: boolean;
  revisadas_por: string | null;
  revisadas_em: string | null;
}

export interface Ingrediente extends Linha {
  produto_id: number;
  produto_nome: string;
  quantidade: string | null;
  unidade: UnidadeMedida;
  observacao: string | null;
  ordem: number;
  /** Falso: falta `medida_base` ou `medida_por_unidade` do produto. */
  converte: boolean;
}

export interface ReceitaDetalhe extends ReceitaResumo {
  modo_preparo: string | null;
  ingredientes: Ingrediente[];
}

export interface ReceitasPagina {
  items: ReceitaResumo[];
  total: number;
  limite: number;
  offset: number;
}

/** O corpo de `POST /receitas` e `PUT /receitas/{id}`. */
export interface IngredienteEntrada {
  produto_id?: number;
  produto_nome?: string;
  quantidade?: string | null;
  unidade: UnidadeMedida;
  observacao?: string | null;
}

export interface ReceitaCorpo {
  nome: string;
  tipo: TipoRefeicao;
  rendimento_porcoes: string;
  tempo_preparo_min: number | null;
  modo_preparo: string | null;
  pode_antecipar: boolean;
  dura_dias: number | null;
  pode_congelar: boolean;
  ingredientes: IngredienteEntrada[];
}

// --- Roteiro -----------------------------------------------------------------

export interface ReceitaNoRoteiro {
  id: number;
  nome: string;
  tempo_preparo_min: number | null;
}

export interface DestinoPasso {
  refeicao_id: number;
  dia: string;
  tipo: TipoRefeicao;
  porcoes: string;
  onde: "geladeira" | "congelador";
  descongelar_em: string | null;
}

export interface Passo {
  receita: ReceitaNoRoteiro;
  porcoes: string;
  fator: string;
  porcoes_geladeira: string;
  porcoes_congelador: string;
  destinos: DestinoPasso[];
  avisos: string[];
  feito: { por: string; em: string } | null;
}

export interface SessaoNoRoteiro {
  sessao_id: number;
  data: string;
  rotulo: string | null;
  passos: Passo[];
}

export interface NoDia {
  refeicao_id: number;
  dia: string;
  tipo: TipoRefeicao;
  receita: ReceitaNoRoteiro;
}

export interface Roteiro {
  sessoes: SessaoNoRoteiro[];
  no_dia: NoDia[];
  avisos: Array<{ refeicao_id: number; texto: string }>;
}

/** Uma linha de `passos_feitos` (resposta do PUT/DELETE e do `/mudancas`). */
export interface PassoFeitoLinha extends Linha {
  sessao_id: number;
  receita_id: number;
  feito_por: string;
  feito_em: string;
  id_cliente: string | null;
}

// --- Lista pelo cardápio -------------------------------------------------------

export interface ListaCriado {
  produto: string;
  item_id: number | null;
  quantidade: string | null;
  unidade: string | null;
  de: string[];
}

export interface ListaAjustado {
  produto: string;
  item_id: number;
  antes: string | null;
  depois: string | null;
  unidade: string | null;
  origem_item: string;
  removido: boolean;
  pedido: string | null;
  de: string[];
}

export interface ListaSemMudanca {
  produto: string;
  item_id: number | null;
  pedido: string | null;
  unidade: string | null;
  de: string[];
}

export interface ListaConfira {
  produto: string;
  estado_despensa: string;
  pedido: string | null;
  unidade: string | null;
  texto: string;
  de: string[];
}

export interface ListaCardapio {
  criados: ListaCriado[];
  ajustados: ListaAjustado[];
  sem_mudanca: ListaSemMudanca[];
  confira: ListaConfira[];
  avisos: Array<{ produto: string | null; texto: string }>;
}
