import type { PassoFeitoLinha } from "@/features/cardapio/types";

/** Espelho de `compras/compras/schemas.py` (D-25). Decimais chegam como texto. */

export type Situacao = "pendente" | "comprado";
export type EstadoDespensa = "tem" | "acabando" | "acabou";
export type OrigemItem = "manual" | "despensa" | "voz" | "cardapio";

interface Linha {
  id: number;
  criado_em: string;
  atualizado_em: string;
  deleted_em: string | null;
}

export interface Item extends Linha {
  produto_id: number;
  produto_nome: string;
  secao_id: number;
  secao_nome: string;
  secao_ordem: number;
  quantidade: string | null;
  unidade: string | null;
  observacao: string | null;
  situacao: Situacao;
  origem: OrigemItem;
  adicionado_por: string;
  comprado_por: string | null;
  comprado_em: string | null;
  id_cliente: string | null;
}

export interface ItemResposta extends Item {
  /** Outro já tinha posto o mesmo produto: nada foi criado nem somado. */
  ja_estava: boolean;
}

export interface LinhaDespensa extends Linha {
  produto_id: number;
  produto_nome: string;
  secao_id: number;
  secao_nome: string;
  secao_ordem: number;
  estado: EstadoDespensa;
  estado_por: string;
  estado_em: string;
}

export interface Produto extends Linha {
  nome: string;
  secao_id: number;
  secao_nome: string;
  unidade_padrao: string | null;
  id_cliente: string | null;
  /** Em que o produto é medido (cardápio, D-30); nulo = sem conversão. */
  medida_base: "g" | "ml" | "un" | null;
  /** Quanto de `medida_base` tem uma unidade do produto. */
  medida_por_unidade: string | null;
}

export interface Secao extends Linha {
  nome: string;
  ordem: number;
}

export interface Lista {
  cursor: string;
  itens: Item[];
  /** "Acabando em casa" que ainda não está na lista. */
  sugestoes: LinhaDespensa[];
}

export interface Mudancas {
  cursor: string;
  /** Cursor velho demais: buscar a lista e a despensa inteiras. */
  recarregar: boolean;
  itens: Item[];
  despensa: LinhaDespensa[];
  produtos: Produto[];
  secoes: Secao[];
  /** Passos do roteiro do cardápio marcados ou desfeitos (D-30); `deleted_em` = desfeito. */
  passos_feitos?: PassoFeitoLinha[];
}

export interface RespostaDespensa {
  despensa: LinhaDespensa;
  item_criado: Item | null;
}

/** `GET /eu`: quem o serviço vê nesta requisição. */
export interface Eu {
  quem: string | null;
  /** "tailscale": o nome vem da tailnet e o aparelho não pergunta nada. */
  origem: "tailscale" | "aparelho" | null;
  login: string | null;
  cadastrado: boolean;
}
