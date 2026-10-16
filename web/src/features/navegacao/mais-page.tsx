import { Card } from "@/components/ui/card";
import { Icone } from "@/components/ui/icone";
import { ITENS_MAIS } from "@/components/layout/navegacao";
import { useEstadoSincronizacao } from "@/features/sincronizacao/queries";
import { quandoRelativo } from "@/lib/format";
import { href } from "@/lib/rotas";

/**
 * "Mais", no celular (D-22): as telas que não cabem na barra inferior. O
 * desenho deixou a forma em aberto "sem criar padrão visual novo" — então é
 * uma lista no mesmo bloco das outras telas, com as mesmas linhas.
 */
export function MaisPage() {
  const estado = useEstadoSincronizacao();
  return (
    <div className="flex max-w-[640px] flex-col gap-7">
      <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">Mais</h1>
      <Card className="px-9 py-3">
        <ul className="m-0 list-none p-0">
          {ITENS_MAIS.map((item, indice) => (
            <li key={item.rota} className={indice ? "linha-acima" : undefined}>
              <a
                href={href(item.rota)}
                className="text-texto hover:text-texto flex min-h-26 items-center gap-7 no-underline"
              >
                <span className="bg-superficie-2 text-texto-apoio rounded-botao flex size-20 shrink-0 items-center justify-center">
                  <Icone nome={item.icone} />
                </span>
                <span className="text-enfase flex-1 font-semibold">{item.rotulo}</span>
                <Icone nome="direita" className="text-texto-2" />
              </a>
            </li>
          ))}
        </ul>
      </Card>
      {estado.data?.ultima_atualizacao ? (
        <p className="text-pequeno text-texto-2 m-0 px-1">
          Bancos atualizados {quandoRelativo(estado.data.ultima_atualizacao)}
        </p>
      ) : null}
    </div>
  );
}
