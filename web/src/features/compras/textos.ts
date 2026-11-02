import type { Item } from "./types";

/** "12.000" -> "12"; "1.500" -> "1,5". */
export function numeroCurto(valor: string): string {
  const n = Number(valor);
  if (!Number.isFinite(n)) return valor;
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

/** A quantidade como o casal lê: "12", "300 g", "1 cacho". Sem quantidade, nada. */
export function quantidadeDoItem(item: Pick<Item, "quantidade" | "unidade">): string {
  if (!item.quantidade) return "";
  const n = numeroCurto(item.quantidade);
  const unidade = item.unidade?.trim();
  return unidade && unidade.toLowerCase() !== "un" ? `${n} ${unidade}` : n;
}

/** "agora", "há 4 min", "há 2 h", "há 12 dias". */
export function haQuantoTempo(iso: string, agora: Date = new Date()): string {
  const minutos = Math.max(0, Math.round((agora.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutos < 1) return "agora";
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `há ${horas} h`;
  const dias = Math.round(horas / 24);
  return `há ${dias} ${dias === 1 ? "dia" : "dias"}`;
}

/** A linha de baixo de um item pendente: quem pôs, ou "Voltou da despensa". */
export function detalheDoPendente(item: Item): string {
  const base = item.origem === "despensa" ? "Voltou da despensa" : `${item.adicionado_por} adicionou`;
  return item.observacao ? `${base}, "${item.observacao}"` : base;
}

/** A linha de baixo de um item no carrinho: quem pegou e quando. */
export function detalheDoComprado(item: Item): string {
  if (!item.comprado_por || !item.comprado_em) return "";
  const quando = haQuantoTempo(item.comprado_em);
  return `${item.comprado_por} pegou ${quando}`;
}

/** Agrupa mantendo a ordem que veio da API (já pelo percurso das seções). */
export function porSecao<T extends { secao_id: number; secao_nome: string }>(
  linhas: T[],
): Array<{ id: number; nome: string; linhas: T[] }> {
  const grupos: Array<{ id: number; nome: string; linhas: T[] }> = [];
  for (const linha of linhas) {
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.id === linha.secao_id) ultimo.linhas.push(linha);
    else grupos.push({ id: linha.secao_id, nome: linha.secao_nome, linhas: [linha] });
  }
  return grupos;
}
