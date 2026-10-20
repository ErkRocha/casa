import type { TipoConta, TipoPagamento } from "@/features/cadastros/types";
import { nomeDoCartao } from "@/features/revisar/textos";
import type { GrupoContas, ItemContaCartao, LinhaHistorico, SituacaoConta } from "./types";

/** Textos das telas de configuração, fora dos componentes (D-22). */

export const ROTULO_TIPO_CONTA: Record<TipoConta, string> = {
  corrente: "Conta corrente",
  poupanca: "Poupança",
  carteira: "Carteira",
  investimento: "Investimento",
  cartao: "Cartão",
};

const PLURAL_FORMA: Record<TipoPagamento, string> = {
  credito: "crédito",
  debito: "débito",
  pix: "Pix",
  dinheiro: "dinheiro",
  boleto: "boletos",
  transferencia: "transferências",
};

/** "Pix, débito e boletos". */
export function listaEmPortugues(itens: string[]): string {
  if (itens.length <= 1) return itens[0] ?? "";
  return `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}`;
}

/** "Nubank Gold •••• 7704" -> "Nubank Gold final 7704". */
export function nomeComFinal(apelido: string): string {
  return apelido.replace(/[\s•*.]*(\d{4})\s*$/, " final $1").trim();
}

export function tipoDoItem(item: ItemContaCartao): string {
  if (item.tipo === "cartao") return "Cartão de crédito";
  const tipo = item.tipo_conta ? ROTULO_TIPO_CONTA[item.tipo_conta] : "Conta";
  return item.titular ? `${tipo}, titular ${item.titular}` : `${tipo}, conjunta`;
}

/** A linha do meio: o que passa pela conta, quem paga a fatura do cartão. */
export function detalheDoItem(item: ItemContaCartao): string {
  if (item.situacao === "pausado") {
    return "A sincronização está pausada. Lance os gastos à mão por enquanto.";
  }
  if (item.situacao === "sem_movimento") return "Nenhuma movimentação nos últimos 12 meses";
  if (item.tipo === "cartao") {
    const paga = item.paga_por ? `Fatura paga pela conta ${item.paga_por}` : "Cartão de crédito";
    return item.cartoes_virtuais.length > 0
      ? `${paga}. Inclui os cartões virtuais ${listaEmPortugues(item.cartoes_virtuais)}`
      : paga;
  }
  // "Pix, débito, boletos e pagamento das faturas do Nubank Gold".
  const partes = item.formas.map((f) => PLURAL_FORMA[f]);
  if (item.cartoes.length > 0) {
    partes.push(`pagamento das faturas do ${listaEmPortugues(item.cartoes.map(nomeDoCartao))}`);
  }
  const texto = listaEmPortugues(partes);
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "Sem forma de pagamento cadastrada";
}

export const SELO_DA_SITUACAO: Record<
  SituacaoConta,
  { rotulo: string; tom: "receita" | "atencao" | "neutro" | "inativo" }
> = {
  sincronizando: { rotulo: "Sincronizando", tom: "receita" },
  pausado: { rotulo: "Pausado", tom: "atencao" },
  sem_movimento: { rotulo: "Sem movimento", tom: "neutro" },
  manual: { rotulo: "Manual", tom: "inativo" },
};

export const SELO_DO_GRUPO: Record<
  GrupoContas["situacao"],
  { rotulo: string; tom: "receita" | "atencao" | "neutro" | "inativo" }
> = {
  funcionando: { rotulo: "Funcionando", tom: "receita" },
  parcial: { rotulo: "Parcial", tom: "atencao" },
  pausada: { rotulo: "Pausada", tom: "atencao" },
  manual: { rotulo: "Manual", tom: "inativo" },
};

/** "Bancos (Meu Pluggy)", "PDF fatura Nubank". */
export function origemDaImportacao(linha: LinhaHistorico): string {
  if (linha.origem === "pluggy") return "Bancos (Meu Pluggy)";
  if (linha.parser_usado === "nubank_fatura" || linha.origem === "nubank_fatura") {
    return "PDF fatura Nubank";
  }
  if (linha.parser_usado === "nubank_extrato" || linha.origem === "nubank_extrato") {
    return "PDF extrato Nubank";
  }
  return linha.arquivo_nome;
}

export const SELO_DO_HISTORICO: Record<
  LinhaHistorico["situacao"],
  { rotulo: string; tom: "receita" | "atencao" | "neutro" }
> = {
  concluida: { rotulo: "Concluída", tom: "receita" },
  com_pendencias: { rotulo: "Com pendências", tom: "atencao" },
  nada_novo: { rotulo: "Nada novo", tom: "neutro" },
  desfeita: { rotulo: "Desfeita", tom: "neutro" },
};
