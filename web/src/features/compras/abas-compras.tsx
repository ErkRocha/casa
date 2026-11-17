import { href, type Rota } from "@/lib/rotas";
import { cn } from "@/lib/utils";

type AbaCompras = "compras" | "cardapio" | "despensa";

const ABAS: Array<{ rota: AbaCompras & Rota; rotulo: string }> = [
  { rota: "compras", rotulo: "Lista" },
  { rota: "cardapio", rotulo: "Cardápio" },
  { rota: "despensa", rotulo: "Despensa" },
];

/**
 * Cabeçalho de Compras (`CardapioSemanaCelular`, D-30): o título e as três
 * abas, Lista, Cardápio e Despensa, cada uma com a sua rota. Quem escolhe a
 * aba é o endereço; as abas são links.
 */
export function CabecalhoCompras({ atual }: { atual: AbaCompras }) {
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-5 px-1">
      <h1 className="text-pagina-celular md:text-pagina m-0 flex-1 font-bold tracking-[-0.4px]">
        Compras
      </h1>
      <nav
        aria-label="Compras"
        className="bg-superficie rounded-interno grid w-full grid-cols-3 gap-0.5 p-2 md:w-auto"
      >
        {ABAS.map((aba) => {
          const ativa = aba.rota === atual;
          return (
            <a
              key={aba.rota}
              href={href(aba.rota)}
              aria-current={ativa ? "page" : undefined}
              className={cn(
                "text-apoio flex min-h-22 items-center justify-center rounded-[9px] px-8 no-underline",
                ativa
                  ? "bg-texto font-semibold text-white hover:text-white"
                  : "text-texto-apoio hover:text-texto font-medium",
              )}
            >
              {aba.rotulo}
            </a>
          );
        })}
      </nav>
    </header>
  );
}
