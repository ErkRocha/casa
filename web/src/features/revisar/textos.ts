import { diaDeMes, diaEMes } from "@/lib/format";
import type { ItemRevisar, Motivo, ResultadoRevisao, RevisarResumo } from "./types";

/** Textos da revisão, fora dos componentes (hot reload, D-22). */

export type Grupo =
  | "tudo"
  | "duplicatas"
  | "transferencias"
  | "encargos"
  | "observacao"
  | "sem_categoria"
  | "outros";

/** Cada aba e os motivos da API que ela junta, na ordem de leitura. */
export const GRUPOS: Array<{
  id: Exclude<Grupo, "tudo">;
  motivos: Motivo[];
  rotulo: string;
  rotuloCurto: string;
}> = [
  {
    id: "duplicatas",
    motivos: ["possivel_duplicata"],
    rotulo: "Possíveis duplicatas",
    rotuloCurto: "Duplicatas",
  },
  {
    id: "transferencias",
    motivos: ["transferencia", "pagamento_fatura_cartao"],
    rotulo: "Transferências",
    rotuloCurto: "Transferências",
  },
  { id: "encargos", motivos: ["encargos"], rotulo: "Encargos", rotuloCurto: "Encargos" },
  {
    id: "observacao",
    motivos: ["observacao"],
    rotulo: "Com observação",
    rotuloCurto: "Observação",
  },
  {
    id: "sem_categoria",
    motivos: ["sem_categoria"],
    rotulo: "Sem categoria",
    rotuloCurto: "Sem categoria",
  },
  { id: "outros", motivos: ["outros"], rotulo: "Outros", rotuloCurto: "Outros" },
];

export function quantidadeDoGrupo(resumo: RevisarResumo, motivos: Motivo[]): number {
  return resumo.motivos
    .filter((m) => motivos.includes(m.motivo))
    .reduce((soma, m) => soma + m.quantidade, 0);
}

/** "Nubank Gold •••• 7704" -> "Nubank Gold": a fatura tem o nome do cartão. */
export function nomeDoCartao(apelido: string): string {
  return apelido.replace(/[\s•*.]*\d{4}\s*$/, "").trim() || apelido;
}

/** "9 de setembro, cartão Nubank Gold" ("9 set, ..." no celular). */
export function deOndeVeio(item: ItemRevisar, curto = false): string {
  const quando = item.data ? (curto ? diaEMes(item.data) : diaDeMes(item.data)) : "sem data";
  const onde =
    item.forma_pagamento_tipo === "credito" && item.forma_pagamento_apelido
      ? `cartão ${nomeDoCartao(item.forma_pagamento_apelido)}`
      : item.conta_nome
        ? `conta ${item.conta_nome}`
        : (item.forma_pagamento_apelido ?? "");
  return onde ? `${quando}, ${onde}` : quando;
}

function plural(n: number, um: string, varios: string): string {
  return `${n} ${n === 1 ? um : varios}`;
}

/** "1 aprovado e 1 descartado." para a linha de status depois da decisão. */
export function textoDoResultado(r: ResultadoRevisao): string {
  const partes = [
    r.aprovados ? plural(r.aprovados, "lançado", "lançados") : null,
    r.descartados ? plural(r.descartados, "descartado", "descartados") : null,
    r.pendentes ? `${plural(r.pendentes, "segue", "seguem")} na revisão por outro motivo` : null,
  ].filter(Boolean);
  const feito = partes.length > 0 ? `${partes.join(", ")}.` : "";
  const erros = r.erros.map((e) => e.erro).join(" ");
  return [feito, erros].filter(Boolean).join(" ");
}
