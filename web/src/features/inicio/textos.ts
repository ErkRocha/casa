import type { RevisarResumo } from "@/features/revisar/types";
import { nomeDoMes, reaisAbs, sinal } from "@/lib/format";
import type { FaixaOrcamento, Inicio } from "./types";

/** Textos e cores do Início, fora dos componentes (hot reload, D-22). */

/** Cor da barra de orçamento pela faixa que a API calculou (README). */
export const COR_FAIXA: Record<FaixaOrcamento, string> = {
  ok: "bg-orcamento-ok",
  perto: "bg-orcamento-perto",
  estourado: "bg-orcamento-estourado",
};

function mesAnterior(competencia: string): string {
  const mes = Number(competencia.split("-")[1] ?? "1");
  return nomeDoMes(mes === 1 ? 12 : mes - 1);
}

/** "R$ 312 a menos que setembro no dia 16". */
export function textoComparacao(i: Inicio): string {
  const anterior = mesAnterior(i.competencia);
  const noDia = i.situacao === "corrente" ? ` no dia ${i.dia_referencia}` : "";
  if (sinal(i.gasto_mes_anterior) === 0) {
    return `${anterior.charAt(0).toUpperCase()}${anterior.slice(1)} não teve gasto${noDia ? ` até o dia ${i.dia_referencia}` : ""}`;
  }
  const s = sinal(i.diferenca_mes_anterior);
  if (s === 0) return `O mesmo que ${anterior}${noDia}`;
  const quanto = reaisAbs(i.diferenca_mes_anterior, { centavos: false });
  return `${quanto} ${s < 0 ? "a menos" : "a mais"} que ${anterior}${noDia}`;
}

function plural(n: number, um: string, varios: string): string {
  return `${n} ${n === 1 ? um : varios}`;
}

/** "2 possíveis duplicatas, 4 transferências". */
export function textoRevisar(resumo: RevisarResumo): string {
  const de = (chave: string) =>
    resumo.motivos.find((m) => m.motivo === chave)?.quantidade ?? 0;
  const partes: string[] = [];
  const duplicatas = de("possivel_duplicata");
  const transferencias = de("transferencia") + de("pagamento_fatura_cartao");
  const encargos = de("encargos");
  const semCategoria = de("sem_categoria");
  const outros = de("observacao") + de("outros");
  if (duplicatas) partes.push(plural(duplicatas, "possível duplicata", "possíveis duplicatas"));
  if (transferencias) partes.push(plural(transferencias, "transferência", "transferências"));
  if (encargos) partes.push(plural(encargos, "encargo de fatura", "encargos de fatura"));
  if (semCategoria) partes.push(`${semCategoria} sem categoria`);
  if (outros) partes.push(plural(outros, "outro", "outros"));
  return partes.join(", ");
}
