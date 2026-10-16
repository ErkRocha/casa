import type { TipoPagamento } from "./types";

/**
 * A forma de pagamento como as pranchetas escrevem (D-22): "Cartão Nubank
 * 7704", "Débito Sicredi", "Pix Nubank", "Boleto".
 *
 * O banco vem do nome da conta da forma — o cartão é forma da conta que paga
 * a fatura, e é ali que está o nome do banco. Sem a conta (forma antiga, sem
 * conta), vale o apelido como está, que já costuma dizer o tipo.
 *
 * `curto` é o rótulo do celular, sem o "Cartão" ("Nubank 7704").
 */
export function rotuloDaForma(
  tipo: TipoPagamento | null | undefined,
  apelido: string | null | undefined,
  contaNome?: string | null,
  opcoes: { curto?: boolean } = {},
): string {
  const nome = (apelido ?? "").trim();
  if (!tipo) return nome || "Sem forma de pagamento";
  if (tipo === "boleto") return "Boleto";
  if (tipo === "dinheiro") return "Dinheiro";

  const banco = contaNome?.trim();
  if (tipo === "credito") {
    const final = /(\d{4})\s*$/.exec(nome)?.[1];
    const base = banco || nome.replace(/[\s•*.]*\d{4}\s*$/, "").trim() || "de crédito";
    const corpo = final ? `${base} ${final}` : base;
    return opcoes.curto ? corpo : `Cartão ${corpo}`;
  }
  if (!banco) return nome || ROTULO_TIPO[tipo];
  return `${ROTULO_TIPO[tipo]} ${banco}`;
}

const ROTULO_TIPO: Record<TipoPagamento, string> = {
  credito: "Cartão",
  debito: "Débito",
  pix: "Pix",
  transferencia: "Transferência",
  boleto: "Boleto",
  dinheiro: "Dinheiro",
};
