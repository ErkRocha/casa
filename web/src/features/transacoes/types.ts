/** Espelho de `TransacaoRead` e afins da API (snake_case, como vem no JSON). */

import type { TipoPagamento } from "@/features/cadastros/types";
import type { BaldePessoa, TipoTransacao } from "@/features/filters/types";

/**
 * Dinheiro chega como string.
 *
 * `numeric(12,2)` serializado como número viraria float em JS e perderia
 * centavo em algum lugar. Formatamos a string; aritmética é do banco.
 */
export type Dinheiro = string;

export interface Transacao {
  id: number;
  data: string;
  competencia: string;
  valor: Dinheiro;
  tipo: TipoTransacao;
  descricao: string;
  /** Texto cru do extrato. Imutável — a API recusa alteração (regra 11). */
  descricao_original: string | null;
  observacao: string | null;
  parcela_num: number | null;
  parcela_total: number | null;
  desconto_total: Dinheiro;
  criado_em: string;
  atualizado_em: string | null;

  /** Nulo = gasto conjunto. `pessoa_nome` já vem com o rótulo "Conjunto". */
  pessoa_id: number | null;
  pessoa_nome: string;

  categoria_id: number | null;
  categoria_nome: string | null;
  categoria_pai_id: number | null;
  categoria_pai_nome: string | null;
  /** "Alimentação › Mercado", pronto para a tabela. */
  categoria_caminho: string | null;
  categoria_raiz_id: number | null;

  forma_pagamento_id: number | null;
  forma_pagamento_apelido: string | null;
  forma_pagamento_tipo: TipoPagamento | null;

  local_id: number | null;
  local_nome: string | null;

  conta_id: number | null;
  conta_origem_id: number | null;
  conta_destino_id: number | null;

  /**
   * De qual arquivo importado a linha nasceu. Nulo em lançamento digitado à
   * mão — o que é informação, não ausência: distingue o que dá para conferir
   * contra um comprovante do que não dá.
   */
  importacao_id: number | null;
  importacao_arquivo: string | null;
  importacao_em: string | null;
  /**
   * Há PDF para abrir. Falso tanto em lançamento manual quanto em importação
   * antiga sem arquivo guardado — quem separa os dois é `importacao_id`.
   */
  importacao_tem_arquivo: boolean | null;
}

export interface TotaisPeriodo {
  total_despesa: Dinheiro;
  total_receita: Dinheiro;
  /** Receita menos despesa. Negativo = gastou mais do que entrou. */
  resultado: Dinheiro;
  /** Chave é o id da pessoa em texto, ou `conjunto`. */
  por_balde: Record<string, Dinheiro>;
}

export interface TransacaoListagem {
  items: Transacao[];
  total: number;
  limit: number;
  offset: number;
  totais: TotaisPeriodo;
}

export interface TransacaoCreate {
  data: string;
  competencia?: string | null;
  valor: string;
  tipo: TipoTransacao;
  descricao: string;
  pessoa_id: number | null;
  categoria_id: number | null;
  forma_pagamento_id: number | null;
  observacao?: string | null;
}

export interface TransacaoUpdate {
  data?: string;
  competencia?: string;
  valor?: string;
  descricao?: string;
  pessoa_id?: number | null;
  categoria_id?: number | null;
  forma_pagamento_id?: number | null;
  observacao?: string | null;
}

export interface LoteAtribuir {
  ids: number[];
  categoria_id?: number | null;
  /** `"conjunto"` limpa o dono; um id atribui a uma pessoa. */
  pessoa?: BaldePessoa | null;
}

export interface LoteResponse {
  afetadas: number;
}
