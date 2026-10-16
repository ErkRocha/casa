import type { ReactNode } from "react";

/**
 * Ícones de linha das pranchetas (`docs/design/telas`), copiados traço a
 * traço. Sempre decorativos (`aria-hidden`): quem dá nome ao controle é o
 * texto ao lado ou o `aria-label` do botão.
 */

const TRACOS = {
  inicio: (
    <>
      <path d="M3 11l9-7 9 7" />
      <path d="M5 10v10h14V10" />
    </>
  ),
  lancamentos: (
    <>
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="M3 6h.01M3 12h.01M3 18h.01" />
    </>
  ),
  revisar: <path d="M20 6L9 17l-5-5" />,
  analises: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  relatorios: (
    <>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M9 12h7M9 16h7" />
    </>
  ),
  contas: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 10h18" />
    </>
  ),
  categorias: <path d="M4 6h16M7 12h10M10 18h4" />,
  sincronizacao: (
    <>
      <path d="M20 12a8 8 0 1 1-2.3-5.6" />
      <path d="M20 4v5h-5" />
    </>
  ),
  mais: (
    <>
      <path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth={3} />
    </>
  ),
  esquerda: <path d="M15 18l-6-6 6-6" />,
  direita: <path d="M9 18l6-6-6-6" />,
  baixo: <path d="M6 9l6 6 6-6" />,
  busca: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
  adicionar: <path d="M12 5v14M5 12h14" />,
  fechar: <path d="M6 6l12 12M18 6L6 18" />,
  lixeira: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  filtros: <path d="M4 6h16M7 12h10M10 18h4" />,
} satisfies Record<string, ReactNode>;

export type NomeIcone = keyof typeof TRACOS;

export function Icone({
  nome,
  tamanho = 18,
  espessura = 2,
  className,
}: {
  nome: NomeIcone;
  tamanho?: number;
  espessura?: number;
  className?: string;
}) {
  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={espessura}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {TRACOS[nome]}
    </svg>
  );
}
