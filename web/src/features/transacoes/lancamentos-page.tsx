import { useMemo, useState } from "react";

import { Button } from "@/components/ui/controls";
import { Carregando, Falha, Vazio } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { SeletorMes } from "@/components/ui/seletor-mes";
import { useGruposDeCategoria, usePessoas } from "@/features/cadastros/queries";
import { ApiError } from "@/lib/api";
import { competenciaDe, mesPorExtenso } from "@/lib/format";
import { href } from "@/lib/rotas";
import { useAdiado } from "@/lib/use-adiado";
import { BatchBar } from "./components/batch-bar";
import { DetalheModal } from "./components/detalhe-modal";
import { FiltrosLancamentos } from "./components/filtros-lancamentos";
import { ListaPorDia } from "./components/lista-por-dia";
import { NovaTransacaoDrawer } from "./components/nova-transacao-drawer";
import { TotaisDoFiltro } from "./components/totals-bar";
import { filtrosDoMes, temRecorte, type FiltrosLancamentos as Filtros } from "./filtros";
import {
  useAtribuirEmLote,
  useAtualizarTransacao,
  useCriarTransacao,
  useDiasLancamentos,
  useExcluirEmLote,
  useLancamentos,
  useRemoverTransacao,
} from "./queries";
import type { Transacao } from "./types";

/**
 * Lançamentos (`LancamentosDesktop`, `LancamentosCelular`; D-22): o mês
 * agrupado por dia, com filtros, a categoria editável na linha e ação em
 * lote. Toda soma vem do banco, com o mesmo filtro da listagem (D-14).
 */
export function LancamentosPage() {
  const [filtros, setFiltros] = useState<Filtros>(() => filtrosDoMes(competenciaDe(new Date())));
  const [texto, setTexto] = useState("");
  const textoAdiado = useAdiado(texto, 300);
  const recorte = useMemo(() => ({ ...filtros, texto: textoAdiado }), [filtros, textoAdiado]);

  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [detalhe, setDetalhe] = useState<Transacao | null>(null);
  const [novoAberto, setNovoAberto] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const lista = useLancamentos(recorte);
  const dias = useDiasLancamentos(recorte);
  const { data: pessoas = [] } = usePessoas();
  const { data: grupos } = useGruposDeCategoria();

  const criar = useCriarTransacao();
  const atualizar = useAtualizarTransacao();
  const remover = useRemoverTransacao();
  const atribuirLote = useAtribuirEmLote();
  const excluirLote = useExcluirEmLote();

  const paginas = lista.data?.pages ?? [];
  const transacoes = paginas.flatMap((p) => p.items);
  const primeira = paginas[0];
  const totaisPorDia = new Map((dias.data ?? []).map((d) => [d.data, d]));

  function mudarFiltros(patch: Partial<Filtros>) {
    setFiltros((atual) => ({ ...atual, ...patch }));
    setSelecionadas(new Set());
  }

  function limparRecorte() {
    setFiltros(filtrosDoMes(filtros.competencia));
    setTexto("");
    setSelecionadas(new Set());
  }

  function alternar(id: number) {
    setSelecionadas((atual) => {
      const proxima = new Set(atual);
      if (proxima.has(id)) proxima.delete(id);
      else proxima.add(id);
      return proxima;
    });
  }

  function alternarTodas() {
    setSelecionadas((atual) =>
      transacoes.every((t) => atual.has(t.id)) ? new Set() : new Set(transacoes.map((t) => t.id)),
    );
  }

  function avisar(mensagem: string) {
    setAviso(mensagem);
    window.setTimeout(() => setAviso((atual) => (atual === mensagem ? null : atual)), 5000);
  }

  function erroDe(e: unknown): string {
    return e instanceof ApiError ? e.detail : "Não foi possível salvar.";
  }

  return (
    <div className="flex max-w-[1100px] flex-col gap-6 md:gap-8">
      <header className="flex flex-wrap items-center gap-5">
        <h1 className="text-pagina-celular md:text-pagina m-0 flex-1 font-bold tracking-[-0.4px]">
          Lançamentos
        </h1>
        <SeletorMes
          competencia={filtros.competencia}
          onMudar={(competencia) => mudarFiltros({ competencia })}
        />
        <Button onClick={() => setNovoAberto(true)} className="hidden md:inline-flex">
          <Icone nome="adicionar" tamanho={16} espessura={2.4} />
          Novo lançamento
        </Button>
      </header>

      <FiltrosLancamentos
        filtros={filtros}
        texto={texto}
        onTexto={(valor) => {
          setTexto(valor);
          setSelecionadas(new Set());
        }}
        onMudar={mudarFiltros}
        pessoas={pessoas}
        semCategoria={primeira?.totais.sem_categoria ?? 0}
      />

      <p role="status" className="text-apoio text-texto-2 m-0 min-h-0 empty:hidden">
        {aviso}
      </p>

      {lista.isLoading ? (
        <Carregando rotulo="Carregando os lançamentos" alturas={["h-40", "h-160"]} />
      ) : lista.isError || !primeira ? (
        <Falha
          titulo="Não foi possível carregar os lançamentos"
          erro={lista.error}
          onTentar={() => void lista.refetch()}
        />
      ) : (
        <>
          <TotaisDoFiltro totais={primeira.totais} quantidade={primeira.total} />

          {transacoes.length === 0 ? (
            temRecorte(recorte) ? (
              <Vazio
                titulo="Nada com esses filtros"
                texto={`Nenhum lançamento de ${mesPorExtenso(filtros.competencia).toLowerCase()} bate com a busca e os filtros escolhidos.`}
              >
                <Button onClick={limparRecorte}>Limpar filtros</Button>
              </Vazio>
            ) : (
              <Vazio
                titulo={`Nenhum lançamento em ${mesPorExtenso(filtros.competencia).toLowerCase()}`}
                texto="Se este mês deveria ter dados, confira se a sincronização com os bancos está em dia. Também dá para lançar à mão."
              >
                <Button onClick={() => setNovoAberto(true)}>Novo lançamento</Button>
                <a href={href("sincronizacao")} className="text-apoio font-semibold">
                  Ver a sincronização
                </a>
              </Vazio>
            )
          ) : (
            <ListaPorDia
              transacoes={transacoes}
              totais={totaisPorDia}
              grupos={grupos}
              selecionadas={selecionadas}
              onAlternar={alternar}
              onAlternarTodas={alternarTodas}
              onAbrir={setDetalhe}
              onCategoria={(t, categoriaId) =>
                atualizar.mutate(
                  { id: t.id, patch: { categoria_id: categoriaId } },
                  {
                    onSuccess: () =>
                      avisar(
                        categoriaId === null
                          ? `Categoria tirada de "${t.descricao}".`
                          : `Categoria de "${t.descricao}" salva. As próximas iguais já vêm com ela.`,
                      ),
                    onError: (e) => avisar(erroDe(e)),
                  },
                )
              }
            />
          )}

          {lista.hasNextPage ? (
            <div className="flex justify-center">
              <Button
                variant="secondary"
                disabled={lista.isFetchingNextPage}
                onClick={() => void lista.fetchNextPage()}
              >
                {lista.isFetchingNextPage
                  ? "Carregando..."
                  : `Carregar mais (${transacoes.length} de ${primeira.total})`}
              </Button>
            </div>
          ) : null}
        </>
      )}

      {/* Celular: o botão flutuante da prancheta, acima da barra inferior. */}
      <button
        type="button"
        aria-label="Novo lançamento"
        onClick={() => setNovoAberto(true)}
        className="bg-destaque fixed right-9 bottom-50 z-20 flex size-29 cursor-pointer items-center justify-center rounded-[18px] border-none text-white shadow-[0_8px_20px_rgba(31,79,191,0.35)] md:hidden"
      >
        <Icone nome="adicionar" tamanho={22} espessura={2.4} />
      </button>

      {selecionadas.size > 0 ? (
        <BatchBar
          quantidade={selecionadas.size}
          ocupado={atribuirLote.isPending || excluirLote.isPending}
          onCancelar={() => setSelecionadas(new Set())}
          onAplicar={({ categoriaId, pessoa }) =>
            atribuirLote.mutate(
              {
                ids: [...selecionadas],
                ...(categoriaId !== null ? { categoria_id: categoriaId } : {}),
                ...(pessoa !== null ? { pessoa } : {}),
              },
              {
                onSuccess: (r) => {
                  setSelecionadas(new Set());
                  avisar(`${r.afetadas} lançamento${r.afetadas === 1 ? "" : "s"} atualizado${r.afetadas === 1 ? "" : "s"}.`);
                },
                onError: (e) => avisar(erroDe(e)),
              },
            )
          }
          onExcluir={() =>
            excluirLote.mutate([...selecionadas], {
              onSuccess: (r) => {
                setSelecionadas(new Set());
                avisar(`${r.afetadas} lançamento${r.afetadas === 1 ? "" : "s"} excluído${r.afetadas === 1 ? "" : "s"}.`);
              },
              onError: (e) => avisar(erroDe(e)),
            })
          }
        />
      ) : null}

      <NovaTransacaoDrawer
        aberto={novoAberto}
        salvando={criar.isPending}
        erro={criar.error instanceof ApiError ? criar.error.detail : null}
        onFechar={() => {
          criar.reset();
          setNovoAberto(false);
        }}
        onSalvar={(payload) =>
          criar.mutate(payload, {
            onSuccess: () => {
              criar.reset();
              setNovoAberto(false);
              avisar("Lançamento salvo.");
            },
          })
        }
      />

      <DetalheModal
        transacao={detalhe}
        excluindo={remover.isPending}
        onFechar={() => setDetalhe(null)}
        onExcluir={(id) => remover.mutate(id, { onSuccess: () => setDetalhe(null) })}
      />
    </div>
  );
}
