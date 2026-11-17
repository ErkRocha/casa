import type { AlvoDaRefeicao } from "./editar-refeicao";
import type { Preparo } from "./textos";
import type { Pessoa, Roteiro, Semana } from "./types";

/**
 * O que a semana (celular e computador) recebe da página: a semana já lida,
 * o roteiro (de onde sai "como fica pronto") e o que fazer quando alguém toca.
 */
export interface VistaDaSemana {
  semana: Semana;
  /** Hoje em São Paulo, `AAAA-MM-DD`. */
  hoje: string;
  /** O domingo da semana é anterior a hoje: vira histórico e não gera lista. */
  encerrada: boolean;
  pessoas: Pessoa[];
  quem: string | null;
  roteiro: Roteiro | undefined;
  preparo: Map<number, Preparo>;
  onEditar: (alvo: AlvoDaRefeicao) => void;
  onAbrirReceita: (id: number) => void;
  onCopiar: () => void;
}
