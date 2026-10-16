import { Icone } from "@/components/ui/icone";
import { useRevisarResumo } from "@/features/revisar/queries";
import { useEstadoSincronizacao } from "@/features/sincronizacao/queries";
import { quandoRelativo } from "@/lib/format";
import { href, type Rota } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { GRUPOS_COMPUTADOR } from "./navegacao";

/**
 * Barra lateral do computador (`InicioDesktop` e afins, D-22).
 *
 * A partir de 1024px fica sempre aberta. Entre 768 e 1023px é recolhível:
 * fechada mostra só os ícones, e o nome de cada tela continua lá para o
 * leitor de tela. Abaixo de 768px ela sai, e entra a barra inferior.
 */
export function BarraLateral({
  rota,
  recolhida,
  onAlternar,
}: {
  rota: Rota;
  recolhida: boolean;
  onAlternar: () => void;
}) {
  const revisar = useRevisarResumo();
  const estado = useEstadoSincronizacao();
  const pendentes = revisar.data?.total ?? 0;
  // O rótulo some só entre 768 e 1023px; a partir de 1024px a barra é sempre
  // aberta, recolhida ou não.
  const someNoRecolhido = recolhida ? "sr-only lg:not-sr-only" : "";

  return (
    <aside
      aria-label="Menu"
      className={cn(
        "bg-superficie sticky top-0 hidden h-screen shrink-0 flex-col gap-13 overflow-y-auto",
        "px-7 py-13 shadow-[1px_0_0_var(--color-linha)] md:flex",
        recolhida ? "w-38 lg:w-124" : "w-124",
      )}
    >
      <div className={cn("flex items-center gap-5 px-4", recolhida && "justify-center lg:justify-start")}>
        <span className="bg-destaque rounded-[9px] flex size-16 shrink-0 items-center justify-center text-white">
          <Icone nome="inicio" />
        </span>
        <span className={cn("text-[17px] font-bold", someNoRecolhido)}>Controle de Casa</span>
      </div>

      <button
        type="button"
        onClick={onAlternar}
        aria-expanded={!recolhida}
        aria-label={recolhida ? "Abrir o menu" : "Recolher o menu"}
        title={recolhida ? "Abrir o menu" : "Recolher o menu"}
        className={cn(
          "text-texto-2 hover:bg-superficie-2 flex min-h-22 cursor-pointer items-center gap-6",
          "rounded-botao border-none bg-transparent px-6 lg:hidden",
          recolhida && "justify-center px-0",
        )}
      >
        <Icone nome={recolhida ? "direita" : "esquerda"} />
        <span className={cn("text-apoio", recolhida && "sr-only")}>Recolher</span>
      </button>

      <nav aria-label="Navegação principal" className="flex flex-col gap-10">
        {GRUPOS_COMPUTADOR.map((grupo, indice) => (
          <ul key={indice} className="m-0 flex list-none flex-col gap-1 p-0">
            {grupo.map((item) => {
              const atual = item.rota === rota;
              const contador = item.rota === "revisar" && pendentes > 0 ? pendentes : null;
              return (
                <li key={item.rota}>
                  <a
                    href={href(item.rota)}
                    aria-current={atual ? "page" : undefined}
                    title={recolhida ? item.rotulo : undefined}
                    className={cn(
                      "rounded-botao relative flex min-h-22 items-center gap-6 px-6 no-underline",
                      "text-corpo",
                      atual
                        ? "bg-destaque-fundo text-destaque-hover font-forte hover:text-destaque-hover"
                        : "text-texto-apoio hover:bg-superficie-2 hover:text-texto font-medium",
                      recolhida && "justify-center px-0 lg:justify-start lg:px-6",
                    )}
                  >
                    <Icone nome={item.icone} />
                    <span className={cn("flex-1", someNoRecolhido)}>{item.rotulo}</span>
                    {contador !== null ? (
                      <span
                        className={cn(
                          "bg-atencao-selo text-selo rounded-full px-4 py-0.5 font-bold text-white",
                          recolhida && "absolute -top-1 right-0 lg:static",
                        )}
                      >
                        {contador}
                        <span className="sr-only"> para revisar</span>
                      </span>
                    ) : null}
                  </a>
                </li>
              );
            })}
          </ul>
        ))}
      </nav>

      {/* `sr-only` no span, não no parágrafo: o `not-sr-only` zera margem e
          padding, e levaria junto o `mt-auto` que prende o texto no rodapé. */}
      <p className="text-pequeno text-texto-2 mt-auto mb-0 px-6 leading-normal">
        <span className={someNoRecolhido}>
          {estado.data?.ultima_atualizacao
            ? `Bancos atualizados ${quandoRelativo(estado.data.ultima_atualizacao)}`
            : estado.data
              ? "Bancos ainda não sincronizados"
              : null}
        </span>
      </p>
    </aside>
  );
}
