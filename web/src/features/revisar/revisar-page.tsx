import { useState, type ReactNode } from "react";

import { Abas } from "@/components/ui/abas";
import { Carregando, Falha, Vazio } from "@/components/ui/estados";
import { useContas, useGruposDeCategoria } from "@/features/cadastros/queries";
import { useAjustarItem, useAprovarItens, useRejeitarItens } from "@/features/ingestao/queries";
import { ApiError } from "@/lib/api";
import { href } from "@/lib/rotas";
import { Duplicatas } from "./components/duplicatas";
import { OutrosItens } from "./components/outros-itens";
import { Transferencias } from "./components/transferencias";
import {
  useConfirmarTransferencias,
  useDuplicatas,
  useItensRevisar,
  useNaoETransferencia,
  useResolverDuplicata,
  useRevisarResumo,
  useTransferencias,
} from "./queries";
import { GRUPOS, quantidadeDoGrupo, textoDoResultado, type Grupo } from "./textos";
import type { Motivo, ResultadoRevisao } from "./types";

const ID_PAINEL = "revisar-painel";
const MOTIVOS_AVULSOS: Motivo[] = ["encargos", "observacao", "sem_categoria", "outros"];

/**
 * Revisar (`RevisarDesktop`, `RevisarCelular`; D-22): só o que a sync não
 * promoveu sozinha (D-21), por motivo. Duplicata e transferência têm decisão
 * própria; o resto se lança ou descarta como antes.
 */
export function RevisarPage() {
  const [aba, setAba] = useState<Grupo>("tudo");
  const [status, setStatus] = useState<string | null>(null);

  const resumo = useRevisarResumo();
  const itens = useItensRevisar();
  const duplicatas = useDuplicatas();
  const transferencias = useTransferencias();
  const { data: contas = [] } = useContas();
  const { data: grupos } = useGruposDeCategoria();

  const resolver = useResolverDuplicata();
  const confirmar = useConfirmarTransferencias();
  const naoE = useNaoETransferencia();
  const ajustar = useAjustarItem();
  const aprovar = useAprovarItens();
  const rejeitar = useRejeitarItens();
  const ocupado =
    resolver.isPending ||
    confirmar.isPending ||
    naoE.isPending ||
    aprovar.isPending ||
    rejeitar.isPending;

  function mostrar(r: ResultadoRevisao) {
    setStatus(textoDoResultado(r) || "Feito.");
  }
  function falhou(e: unknown) {
    setStatus(e instanceof ApiError ? e.detail : "Não foi possível salvar a decisão.");
  }

  const total = resumo.data?.total ?? 0;
  const abas: Array<{ id: Grupo; rotulo: ReactNode }> = [
    { id: "tudo", rotulo: `Tudo (${total})` },
    ...GRUPOS.flatMap((g) => {
      const n = resumo.data ? quantidadeDoGrupo(resumo.data, g.motivos) : 0;
      if (n === 0) return [];
      // "Duplicatas (2)" no celular, "Possíveis duplicatas (2)" no computador.
      const rotulo =
        g.rotulo === g.rotuloCurto ? (
          `${g.rotulo} (${n})`
        ) : (
          <>
            <span className="md:hidden">{`${g.rotuloCurto} (${n})`}</span>
            <span className="hidden md:inline">{`${g.rotulo} (${n})`}</span>
          </>
        );
      return [{ id: g.id as Grupo, rotulo }];
    }),
  ];
  // A aba escolhida pode sumir quando o último item dela é resolvido.
  const atual = abas.some((a) => a.id === aba) ? aba : "tudo";
  const mostra = (grupo: Grupo) => atual === "tudo" || atual === grupo;

  const carregando =
    resumo.isLoading || itens.isLoading || duplicatas.isLoading || transferencias.isLoading;
  const erro = resumo.error ?? itens.error ?? duplicatas.error ?? transferencias.error;

  return (
    <div className="flex max-w-[980px] flex-col gap-7 md:gap-9">
      <header className="flex flex-col gap-3">
        <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">
          Revisar
        </h1>
        {total > 0 ? (
          <p className="text-corpo md:text-enfase text-texto-2 m-0 max-w-[640px] leading-normal">
            <span className="md:hidden">
              O resto já entrou sozinho.{" "}
              {total === 1 ? "Só este precisa de você." : `Só estes ${total} precisam de você.`}
            </span>
            <span className="hidden md:inline">
              O que veio limpo do banco já entrou sozinho. Aqui{" "}
              {total === 1
                ? "fica só o caso em que o sistema precisa da sua decisão."
                : `ficam só os ${total} casos em que o sistema precisa da sua decisão.`}
            </span>
          </p>
        ) : null}
      </header>

      {carregando ? (
        <Carregando rotulo="Carregando a revisão" alturas={["h-22", "h-120", "h-120"]} />
      ) : erro ? (
        <Falha
          titulo="Não foi possível carregar a revisão"
          erro={erro}
          onTentar={() => {
            void resumo.refetch();
            void itens.refetch();
            void duplicatas.refetch();
            void transferencias.refetch();
          }}
        />
      ) : total === 0 ? (
        <Vazio
          titulo="Nada para revisar"
          texto="Tudo o que veio dos bancos já entrou nos lançamentos. Quando a sincronização trouxer algo que precise de decisão, aparece aqui."
        >
          <a href={href("lancamentos")} className="text-apoio font-semibold">
            Ver os lançamentos
          </a>
        </Vazio>
      ) : (
        <>
          <Abas
            rotulo="Filtrar por motivo"
            abas={abas}
            atual={atual}
            onMudar={setAba}
            idPainel={ID_PAINEL}
          />

          <p role="status" className="text-apoio text-texto-apoio m-0 empty:hidden">
            {status}
          </p>

          <div id={ID_PAINEL} role="tabpanel" className="flex flex-col gap-7 md:gap-9">
            {mostra("duplicatas") && (duplicatas.data ?? []).length > 0 ? (
              <Duplicatas
                grupos={duplicatas.data ?? []}
                ocupado={ocupado}
                onResolver={(manter_ids, descartar_ids) =>
                  resolver.mutate(
                    { manter_ids, descartar_ids },
                    { onSuccess: mostrar, onError: falhou },
                  )
                }
              />
            ) : null}

            {mostra("transferencias") && (transferencias.data ?? []).length > 0 ? (
              <Transferencias
                lista={transferencias.data ?? []}
                contas={contas}
                ocupado={ocupado}
                onConfirmar={(pedidos) =>
                  confirmar.mutate(pedidos, { onSuccess: mostrar, onError: falhou })
                }
                onNaoE={(id, tipo) =>
                  naoE.mutate(
                    { id, tipo },
                    {
                      onSuccess: (item) =>
                        setStatus(
                          `"${item.descricao}" agora é ${item.tipo_sugerido === "receita" ? "receita" : "despesa"} e segue na revisão.`,
                        ),
                      onError: falhou,
                    },
                  )
                }
              />
            ) : null}

            {MOTIVOS_AVULSOS.map((motivo) => {
              const doMotivo = (itens.data ?? []).filter((i) => i.motivo === motivo);
              if (doMotivo.length === 0 || !mostra(motivo as Grupo)) return null;
              return (
                <OutrosItens
                  key={motivo}
                  motivo={motivo}
                  itens={doMotivo}
                  grupos={grupos}
                  ocupado={ocupado}
                  onCategoria={(item, categoriaId) =>
                    ajustar.mutate(
                      { id: item.id, patch: { categoria_sugerida_id: categoriaId } },
                      {
                        onSuccess: () =>
                          setStatus(
                            categoriaId === null
                              ? `Categoria tirada de "${item.descricao}".`
                              : `Categoria de "${item.descricao}" salva. As próximas iguais já vêm com ela.`,
                          ),
                        onError: falhou,
                      },
                    )
                  }
                  onAprovar={(ids) =>
                    aprovar.mutate(ids, {
                      onSuccess: (r) =>
                        mostrar({
                          aprovados: r.promovidos,
                          descartados: 0,
                          pendentes: 0,
                          erros: [
                            ...r.erros,
                            ...(r.duplicados
                              ? [
                                  {
                                    item_id: 0,
                                    erro:
                                      r.duplicados === 1
                                        ? "Um já existia nos lançamentos."
                                        : `${r.duplicados} já existiam nos lançamentos.`,
                                  },
                                ]
                              : []),
                          ],
                        }),
                      onError: falhou,
                    })
                  }
                  onDescartar={(ids) =>
                    rejeitar.mutate(
                      { ids, motivo: "Descartado na revisão." },
                      {
                        onSuccess: (r) =>
                          mostrar({ aprovados: 0, descartados: r.afetadas, pendentes: 0, erros: [] }),
                        onError: falhou,
                      },
                    )
                  }
                />
              );
            })}
          </div>

          <p className="text-apoio text-texto-2 m-0">
            Errou numa decisão? Em <a href={href("sincronizacao")}>Sincronização</a> você pode
            desfazer uma importação inteira.
          </p>
        </>
      )}
    </div>
  );
}
