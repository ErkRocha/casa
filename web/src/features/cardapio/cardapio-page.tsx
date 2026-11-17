import { ComTela } from "@/features/compras/compras-page";
import { CabecalhoCompras } from "@/features/compras/abas-compras";

/** Aba Cardápio de Compras (D-30). */
export function CardapioPage() {
  return (
    <ComTela>
      {() => (
        <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-6">
          <CabecalhoCompras atual="cardapio" />
        </div>
      )}
    </ComTela>
  );
}
