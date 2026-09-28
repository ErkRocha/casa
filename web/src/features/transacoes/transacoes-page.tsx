import { useState } from "react";

import { Button } from "@/components/ui/controls";
import { Card } from "@/components/ui/card";
import { useFiltros } from "@/features/filters/filter-context";
import { temFiltroAtivo } from "@/features/filters/types";
import { ApiError } from "@/lib/api";
import { BatchBar } from "./components/batch-bar";
import { DetalheModal } from "./components/detalhe-modal";
import { NovaTransacaoDrawer } from "./components/nova-transacao-drawer";
import { TabelaCarregando, TabelaErro, TabelaVazia } from "./components/table-states";
import { TotalsBar } from "./components/totals-bar";
import { TransacoesTable } from "./components/transacoes-table";
import {
  useAtribuirEmLote,
  useAtualizarTransacao,
  useCriarTransacao,
  useExcluirEmLote,
  useRemoverTransacao,
  useTransacoes,
} from "./queries";
import type { Transacao } from "./types";

const POR_PAGINA = 50;

/**
 * Tela de transações — fase 3 do roadmap.
 *
 * A partir daqui o sistema já é útil sem nenhum agente: dá para lançar e
 * corrigir gasto na mão.
 */
export function TransacoesPage({
  drawerAberto,
  onFecharDrawer,
  onAbrirDrawer,
}: {
  drawerAberto: boolean;
  onFecharDrawer: () => void;
  onAbrirDrawer: () => void;
}) {
  const { filtros, limparTudo } = useFiltros();
  const [offset, setOffset] = useState(0);
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [detalhe, setDetalhe] = useState<Transacao | null>(null);

  const listagem = useTransacoes(filtros, offset, POR_PAGINA);
  const criar = useCriarTransacao();
  const atualizar = useAtualizarTransacao();
  const remover = useRemoverTransacao();
  const atribuirLote = useAtribuirEmLote();
  const excluirLote = useExcluirEmLote();

  const transacoes = listagem.data?.items ?? [];

  function alternarSelecao(id: number) {
    setSelecionadas((atual) => {
      const proxima = new Set(atual);
      if (proxima.has(id)) proxima.delete(id);
      else proxima.add(id);
      return proxima;
    });
  }

  function alternarTodas() {
    setSelecionadas((atual) =>
      atual.size === transacoes.length ? new Set() : new Set(transacoes.map((t) => t.id)),
    );
  }

  function limparSelecao() {
    setSelecionadas(new Set());
  }

  const ocupadoEmLote = atribuirLote.isPending || excluirLote.isPending;

  return (
    <>
      <Card>
        {selecionadas.size > 0 ? (
          <BatchBar
            quantidade={selecionadas.size}
            ocupado={ocupadoEmLote}
            onCancelar={limparSelecao}
            onAplicar={({ categoriaId, pessoa }) =>
              atribuirLote.mutate(
                {
                  ids: [...selecionadas],
                  categoria_id: categoriaId,
                  pessoa,
                },
                { onSuccess: limparSelecao },
              )
            }
            onExcluir={() =>
              excluirLote.mutate([...selecionadas], { onSuccess: limparSelecao })
            }
          />
        ) : null}

        <div className="border-border-faint text-caption-lg text-text-tertiary flex items-center justify-between border-b px-8 py-4">
          <span>
            {listagem.isLoading
              ? "Carregando..."
              : `${listagem.data?.total ?? 0} transaç${(listagem.data?.total ?? 0) === 1 ? "ão" : "ões"}`}
          </span>
          {listagem.isFetching && !listagem.isLoading ? <span>atualizando...</span> : null}
        </div>

        {listagem.isLoading ? (
          <TabelaCarregando />
        ) : listagem.isError ? (
          <TabelaErro
            mensagem={
              listagem.error instanceof ApiError
                ? listagem.error.detail
                : "Erro inesperado ao consultar o banco."
            }
            onTentar={() => void listagem.refetch()}
          />
        ) : transacoes.length === 0 ? (
          <TabelaVazia
            temFiltro={temFiltroAtivo(filtros)}
            onLimparFiltros={limparTudo}
            onNova={onAbrirDrawer}
          />
        ) : (
          <>
            <TransacoesTable
              transacoes={transacoes}
              selecionadas={selecionadas}
              onAlternarSelecao={alternarSelecao}
              onAlternarTodas={alternarTodas}
              onAbrirDetalhe={setDetalhe}
              onEditar={(id, patch) => atualizar.mutate({ id, patch })}
            />

            {listagem.data ? <TotalsBar totais={listagem.data.totais} /> : null}
          </>
        )}
      </Card>

      {listagem.data && listagem.data.total > POR_PAGINA ? (
        <Paginacao
          offset={offset}
          total={listagem.data.total}
          onMudar={(novo) => {
            setOffset(novo);
            limparSelecao();
          }}
        />
      ) : null}

      <NovaTransacaoDrawer
        aberto={drawerAberto}
        salvando={criar.isPending}
        erro={criar.error instanceof ApiError ? criar.error.detail : null}
        onFechar={() => {
          criar.reset();
          onFecharDrawer();
        }}
        onSalvar={(payload) =>
          criar.mutate(payload, {
            onSuccess: () => {
              criar.reset();
              onFecharDrawer();
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
    </>
  );
}

function Paginacao({
  offset,
  total,
  onMudar,
}: {
  offset: number;
  total: number;
  onMudar: (offset: number) => void;
}) {
  const primeira = offset + 1;
  const ultima = Math.min(offset + POR_PAGINA, total);

  return (
    <div className="mt-8 flex items-center justify-between">
      <span className="text-body-sm text-text-tertiary tabular">
        {primeira}–{ultima} de {total}
      </span>
      <div className="flex gap-4">
        <Button
          variant="secondary"
          disabled={offset === 0}
          onClick={() => onMudar(Math.max(0, offset - POR_PAGINA))}
        >
          Anterior
        </Button>
        <Button
          variant="secondary"
          disabled={ultima >= total}
          onClick={() => onMudar(offset + POR_PAGINA)}
        >
          Próxima
        </Button>
      </div>
    </div>
  );
}
