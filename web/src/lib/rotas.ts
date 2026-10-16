import { useEffect, useState } from "react";

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

  useEffect(() => {
    const aoMudar = () => {
      setRota(lerRota());
      // Tela nova começa do topo, como uma página.
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  useEffect(() => {
    document.title = `${TITULO_DA_ROTA[rota]} · Controle de Casa`;
  }, [rota]);

  return rota;
}
