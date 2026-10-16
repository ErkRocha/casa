import { Icone } from "@/components/ui/icone";
import { useRevisarResumo } from "@/features/revisar/queries";
import { href, type Rota } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { ITENS_CELULAR, rotaAtivaNoCelular } from "./navegacao";

/**
 * Barra inferior do celular (`InicioCelular` e afins, D-22): Início,
 * Lançamentos, Revisar (com contador), Análises e "Mais", que leva às telas
 * de configuração. Some a partir de 768px.
 */
export function BarraInferior({ rota }: { rota: Rota }) {
  const revisar = useRevisarResumo();
  const pendentes = revisar.data?.total ?? 0;
  const ativa = rotaAtivaNoCelular(rota);

  return (
    <nav
      aria-label="Navegação principal"
      className={cn(
        // Cinco itens em 390px: sem folga lateral, "Lançamentos" encosta no
        // vizinho. O alvo de toque continua com 52px de altura.
        "bg-superficie fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 px-1 pt-3",
        "pb-[max(20px,env(safe-area-inset-bottom))] shadow-[0_-1px_0_var(--color-linha)] md:hidden",
      )}
    >
      {ITENS_CELULAR.map((item) => {
        const atual = item.rota === ativa;
        const contador = item.rota === "revisar" && pendentes > 0 ? pendentes : null;
        return (
          <a
            key={item.rota}
            href={href(item.rota)}
            aria-current={atual ? "page" : undefined}
            className={cn(
              "text-selo flex min-h-26 min-w-0 flex-col items-center justify-center gap-1.5",
              "whitespace-nowrap no-underline",
              atual
                ? "text-destaque font-forte hover:text-destaque"
                : "text-texto-2 hover:text-texto font-medium",
            )}
          >
            <span className="relative flex">
              <Icone nome={item.icone} tamanho={22} />
              {contador !== null ? (
                <span className="bg-atencao-selo absolute -top-2.5 -right-6 rounded-full px-3 py-px text-[10px] font-bold text-white">
                  {contador}
                  <span className="sr-only"> para revisar</span>
                </span>
              ) : null}
            </span>
            {item.rotulo}
          </a>
        );
      })}
    </nav>
  );
}
