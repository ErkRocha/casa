import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

/**
 * As telas do painel como endereços reais (`#inicio`, `#lancamentos`...).
 *
 * Hash, e não history API: o painel é servido como arquivos estáticos pelo
 * nginx (D-19), e o hash não precisa de regra de fallback no servidor. Com
 * endereço, os itens de navegação são links de verdade — abrem em outra aba,
 * o "voltar" do navegador funciona e o leitor de tela anuncia como link.
 */

export type Rota =
  | "inicio"
  | "lancamentos"
  | "compras"
  | "despensa"
  | "cardapio"
  | "revisar"
  | "analises"
  | "relatorios"
  | "contas"
  | "categorias"
  | "sincronizacao"
  | "mais";

export const ROTA_PADRAO: Rota = "inicio";

const ROTAS = new Set<Rota>([
  "inicio",
  "lancamentos",
  "compras",
  "despensa",
  "cardapio",
  "revisar",
  "analises",
  "relatorios",
  "contas",
  "categorias",
  "sincronizacao",
  "mais",
]);

export const TITULO_DA_ROTA: Record<Rota, string> = {
  inicio: "Início",
  lancamentos: "Lançamentos",
  compras: "Lista de compras",
  despensa: "Despensa",
  cardapio: "Cardápio",
  revisar: "Revisar",
  analises: "Análises",
  relatorios: "Relatórios do mês",
  contas: "Contas e cartões",
  categorias: "Categorias",
  sincronizacao: "Sincronização",
  mais: "Mais",
};

export function href(rota: Rota): string {
  return `#${rota}`;
}

function lerRota(): Rota {
  const bruta = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0] ?? "";
  return ROTAS.has(bruta as Rota) ? (bruta as Rota) : ROTA_PADRAO;
}

/** A rota atual, acompanhando o `hashchange`. */
export function useRota(): Rota {
  const [rota, setRota] = useState<Rota>(lerRota);
  const anterior = useRef(rota);

  useEffect(() => {
    const aoMudar = () => {
      const nova = lerRota();
      setRota(nova);
      // Tela nova começa do topo, como uma página. Só os parâmetros que
      // mudam (semana, painel aberto) não tiram a pessoa de onde está.
      if (nova !== anterior.current) window.scrollTo({ top: 0 });
      anterior.current = nova;
    };
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  useEffect(() => {
    document.title = `${TITULO_DA_ROTA[rota]} · Controle de Casa`;
  }, [rota]);

  return rota;
}

function assinarHash(ouvir: () => void): () => void {
  window.addEventListener("hashchange", ouvir);
  return () => window.removeEventListener("hashchange", ouvir);
}

function textoDosParametros(): string {
  const i = window.location.hash.indexOf("?");
  return i < 0 ? "" : window.location.hash.slice(i + 1);
}

/**
 * Os parâmetros depois do "?" do endereço (`#cardapio?semana=2026-11-16`):
 * o estado que vale um link (semana aberta, painel aberto) mora aqui, e o
 * "voltar" do navegador fecha o painel.
 */
export function useParamsDaRota(): URLSearchParams {
  const texto = useSyncExternalStore(assinarHash, textoDosParametros, () => "");
  return useMemo(() => new URLSearchParams(texto), [texto]);
}

/**
 * Muda os parâmetros da rota atual: `null` tira o parâmetro. Por padrão
 * entra no histórico (o "voltar" desfaz); `substituir` troca a entrada atual,
 * para o que não merece um passo de volta (o dia escolhido).
 */
export function mudarParams(
  mudancas: Record<string, string | null>,
  opcoes: { substituir?: boolean } = {},
): void {
  const params = new URLSearchParams(textoDosParametros());
  for (const [chave, valor] of Object.entries(mudancas)) {
    if (valor === null) params.delete(chave);
    else params.set(chave, valor);
  }
  const texto = params.toString();
  const destino = `#${lerRota()}${texto ? `?${texto}` : ""}`;
  if (opcoes.substituir) {
    window.history.replaceState(null, "", destino);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = destino;
  }
}
