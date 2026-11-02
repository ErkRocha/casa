import { useSyncExternalStore } from "react";

/**
 * Quem está com o aparelho (D-25): vai no `X-Quem` de toda escrita.
 *
 * Sem identidade do Tailscale, o aparelho pergunta uma vez e guarda aqui.
 * O armazenamento pode faltar (aba privada, bloqueio): aí vale só nesta
 * visita, e a pergunta volta na próxima.
 */
const CHAVE = "controle-casa:quem";
const ouvintes = new Set<() => void>();
let naMemoria: string | null = null;

function ler(): string | null {
  try {
    return window.localStorage.getItem(CHAVE) ?? naMemoria;
  } catch {
    return naMemoria;
  }
}

export function definirQuem(nome: string | null): void {
  naMemoria = nome;
  try {
    if (nome) window.localStorage.setItem(CHAVE, nome);
    else window.localStorage.removeItem(CHAVE);
  } catch {
    // Sem armazenamento: fica só na memória desta aba.
  }
  ouvintes.forEach((ouvir) => ouvir());
}

function assinar(ouvir: () => void): () => void {
  ouvintes.add(ouvir);
  const aoMudarEmOutraAba = (evento: StorageEvent) => {
    if (evento.key === CHAVE) ouvir();
  };
  window.addEventListener("storage", aoMudarEmOutraAba);
  return () => {
    ouvintes.delete(ouvir);
    window.removeEventListener("storage", aoMudarEmOutraAba);
  };
}

/** O nome guardado no aparelho, ou nulo se ainda não perguntou. */
export function useQuemGuardado(): string | null {
  return useSyncExternalStore(assinar, ler, () => null);
}
