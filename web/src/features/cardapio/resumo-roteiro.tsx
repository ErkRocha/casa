import { Button } from "@/components/ui/controls";
import { mudarParams } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { diaEMesBR, maiuscula, nomeDoDia } from "./datas";
import type { VistaDaSemana } from "./vista";

/**
 * O roteiro resumido, abaixo da grade (`CardapioDesktop`): uma linha por
 * sessão e uma para "no dia". Cada linha abre o roteiro naquela sessão.
 */
export function ResumoRoteiro({
  v,
  onNovaSessao,
}: {
  v: VistaDaSemana;
  onNovaSessao: () => void;
}) {
  const roteiro = v.roteiro;
  const proxima = roteiro?.sessoes.find((s) => s.data >= v.hoje)?.sessao_id;

  return (
    <section
      aria-label="Roteiro de preparo"
      className="bg-superficie rounded-bloco flex flex-col gap-2 px-11 py-10"
    >
      <div className="flex items-baseline justify-between gap-4 pb-3">
        <h2 className="text-bloco font-forte m-0">Roteiro de preparo</h2>
        <button
          type="button"
          onClick={() => mudarParams({ roteiro: "1" })}
          className="text-destaque text-apoio cursor-pointer border-none bg-transparent p-0 font-semibold"
        >
          Abrir roteiro
        </button>
      </div>

      {!roteiro ? (
        <p role="status" className="text-apoio text-texto-2 m-0">
          Carregando o roteiro…
        </p>
      ) : (
        <>
          {roteiro.sessoes.map((s) => {
            const passou = s.data < v.hoje;
            const feitos = s.passos.filter((p) => p.feito).length;
            const nomes = s.passos.map((p) => p.receita.nome).join(", ");
            return (
              <button
                key={s.sessao_id}
                type="button"
                onClick={() => mudarParams({ roteiro: "1", sessao: String(s.sessao_id) })}
                className={cn(
                  "linha-acima text-texto grid min-h-26 w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-5 border-none bg-transparent py-4 text-left",
                  passou && "opacity-60",
                )}
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-corpo font-[650]">
                    {maiuscula(nomeDoDia(s.data))}, {diaEMesBR(s.data)}
                    {s.rotulo ? ` · ${s.rotulo}` : ""}
                  </span>
                  <span className="text-pequeno text-texto-2 leading-normal">
                    {s.passos.length === 0
                      ? "Nenhuma receita nesta sessão"
                      : `${s.passos.length} ${s.passos.length === 1 ? "passo" : "passos"}: ${nomes}`}
                  </span>
                </span>
                <span
                  className={cn(
                    "text-pequeno rounded-selo px-4 py-0.5 font-[650] whitespace-nowrap",
                    passou
                      ? "bg-superficie-2 text-texto-2"
                      : s.sessao_id === proxima
                        ? "bg-destaque-fundo text-destaque-hover"
                        : "bg-superficie-2 text-texto-apoio",
                  )}
                >
                  {passou
                    ? "já passou"
                    : `${feitos} de ${s.passos.length} feitos${s.sessao_id === proxima ? " · próxima" : ""}`}
                </span>
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => mudarParams({ roteiro: "1", sessao: "no_dia" })}
            className="linha-acima text-texto grid min-h-26 w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-5 border-none bg-transparent py-4 text-left"
          >
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-corpo font-[650]">No dia</span>
              <span className="text-pequeno text-texto-2 leading-normal">
                {roteiro.no_dia.length} {roteiro.no_dia.length === 1 ? "prato" : "pratos"} que se
                fazem na hora
              </span>
            </span>
          </button>
        </>
      )}

      <Button
        variant="filter"
        disabled={!v.quem}
        onClick={onNovaSessao}
        className="mt-2 self-start bg-destaque-fundo text-destaque-hover font-forte"
      >
        Adicionar sessão
      </Button>
    </section>
  );
}
