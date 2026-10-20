import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button, Selo } from "@/components/ui/controls";
import { Carregando, Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { UploadZone } from "@/features/ingestao/components/upload-zone";
import { useDesfazerImportacao } from "@/features/ingestao/queries";
import { useRevisarResumo } from "@/features/revisar/queries";
import { useEstadoSincronizacao } from "@/features/sincronizacao/queries";
import { ApiError } from "@/lib/api";
import { mesPorExtenso, quandoRelativo } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { useContasECartoes, useHistorico } from "./queries";
import { nomeComFinal, origemDaImportacao, SELO_DO_GRUPO, SELO_DO_HISTORICO } from "./textos";
import type { GrupoContas, LinhaHistorico } from "./types";

const DIAS_DO_HISTORICO = 30;
/** Mais que isto sem atualizar, o resumo deixa de dizer "tudo em dia". */
const HORAS_EM_DIA = 36;

/**
 * Sincronização (`SincronizacaoDesktop`; D-22): o estado da última
 * atualização, as conexões com os bancos e o histórico com "Desfazer".
 *
 * Não há "Atualizar agora": a sync roda pelo `make sync` no computador de
 * casa e não há como dispará-la pela API sem prender a requisição. E não há
 * agendamento ainda, então a tela diz que a atualização é manual em vez de
 * prometer uma próxima execução (roadmap, seção do redesenho).
 */
export function SincronizacaoPage() {
  const estado = useEstadoSincronizacao();
  const historico = useHistorico(DIAS_DO_HISTORICO);
  const contas = useContasECartoes();
  const revisar = useRevisarResumo();
  const [status, setStatus] = useState<string | null>(null);

  return (
    <div className="flex max-w-[1060px] flex-col gap-7 md:gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">
          Sincronização
        </h1>
        <p className="text-corpo text-texto-2 m-0">
          Como os dados dos bancos chegam aqui, e o histórico de cada atualização.
        </p>
      </header>

      {estado.isLoading || historico.isLoading ? (
        <Carregando rotulo="Carregando a sincronização" alturas={["h-50", "h-80", "h-120"]} />
      ) : estado.isError || !estado.data ? (
        <Falha
          titulo="Não foi possível ler o estado da sincronização"
          erro={estado.error}
          onTentar={() => void estado.refetch()}
        />
      ) : (
        <>
          <Resumo
            ultima={estado.data.ultima_atualizacao}
            automatica={estado.data.automatica}
            ultimaSync={(historico.data ?? []).find((l) => l.origem === "pluggy") ?? null}
            paraRevisar={revisar.data?.total ?? 0}
          />
          <Conexoes grupos={(contas.data?.grupos ?? []).filter((g) => g.pluggy_item_id !== null)} />
          <p role="status" className="text-apoio text-texto-apoio m-0 empty:hidden">
            {status}
          </p>
          {historico.isError ? (
            <Falha
              titulo="Não foi possível ler o histórico"
              erro={historico.error}
              onTentar={() => void historico.refetch()}
            />
          ) : (
            <Historico linhas={historico.data ?? []} onStatus={setStatus} />
          )}
        </>
      )}

      <Card className="flex flex-col gap-6 px-8 py-9 md:px-11">
        <div className="flex flex-col gap-1">
          <h2 className="text-bloco-celular md:text-bloco font-forte m-0">Importar um PDF</h2>
          <span className="text-apoio text-texto-2">
            Para o que o banco não envia, como um cartão pausado. Os itens vão para a revisão.
          </span>
        </div>
        <UploadZone
          onImportado={() => setStatus("PDF importado. Os itens estão em Revisar.")}
        />
      </Card>
    </div>
  );
}

function Resumo({
  ultima,
  automatica,
  ultimaSync,
  paraRevisar,
}: {
  ultima: string | null;
  automatica: boolean;
  ultimaSync: LinhaHistorico | null;
  paraRevisar: number;
}) {
  const horas = ultima ? (Date.now() - new Date(ultima).getTime()) / 3_600_000 : null;
  const emDia = horas !== null && horas <= HORAS_EM_DIA;
  const titulo =
    ultima === null
      ? "Ainda não houve atualização"
      : emDia
        ? "Tudo em dia"
        : `Sem atualização desde ${quandoRelativo(ultima)}`;

  return (
    <Card className="flex flex-wrap items-center gap-8 px-8 py-9 md:gap-10 md:px-11 md:py-10">
      <span
        aria-hidden
        className={cn(
          "rounded-sub flex size-24 shrink-0 items-center justify-center",
          emDia ? "bg-receita-fundo text-receita-texto" : "bg-atencao-fundo text-atencao-texto",
        )}
      >
        <Icone nome="sincronizacao" tamanho={22} />
      </span>
      <span className="flex flex-[1_1_260px] flex-col gap-1">
        <span className="text-bloco font-forte">{titulo}</span>
        <span className="text-apoio text-texto-2 leading-normal">
          {ultima ? `Última atualização ${quandoRelativo(ultima)}. ` : ""}
          {automatica
            ? "As próximas rodam sozinhas."
            : "A atualização é manual: rode make sync no computador de casa."}
        </span>
      </span>
      <span className="text-apoio grid grid-cols-2 gap-10">
        <Numero rotulo="Entraram na última" valor={ultimaSync ? String(ultimaSync.entraram) : "—"} />
        <a href={href("revisar")} className="text-texto flex flex-col gap-1 no-underline">
          <span className="text-texto-2">Para revisar</span>
          <span className={cn("text-bloco font-bold", paraRevisar > 0 && "text-atencao-texto")}>
            {paraRevisar}
          </span>
        </a>
      </span>
      <code className="bg-superficie-2 text-apoio rounded-campo px-6 py-4 select-all">make sync</code>
    </Card>
  );
}

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <span className="flex flex-col gap-1">
      <span className="text-texto-2">{rotulo}</span>
      <span className="text-bloco font-bold">{valor}</span>
    </span>
  );
}

function Conexoes({ grupos }: { grupos: GrupoContas[] }) {
  return (
    <Card className="flex flex-col gap-1 px-8 py-9 md:px-11">
      <h2 className="text-bloco-celular md:text-bloco font-forte m-0 pb-4">Conexões</h2>
      {grupos.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">
          Nenhum banco conectado. A conexão é feita no computador de casa, com make pluggy-mapear.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {grupos.map((g) => {
            const selo = SELO_DO_GRUPO[g.situacao];
            return (
              <li
                key={g.pluggy_item_id}
                className="linha-acima grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-7 gap-y-2 py-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_130px]"
              >
                <span className="text-enfase font-semibold">{g.titulo}</span>
                <span className="text-apoio text-texto-apoio col-span-2 row-start-2 leading-[1.45] md:col-span-1 md:row-start-auto">
                  {detalheDaConexao(g)}
                </span>
                <span className="col-start-2 row-start-1 justify-self-end md:col-start-auto md:row-start-auto">
                  <Selo tom={selo.tom}>{selo.rotulo}</Selo>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function detalheDaConexao(g: GrupoContas): string {
  const nomes = g.itens.map((i) => (i.tipo === "cartao" ? nomeComFinal(i.nome) : i.nome));
  const desde = g.desde ? `, histórico desde ${mesPorExtenso(g.desde).toLowerCase()}` : "";
  const pausados = g.itens.filter((i) => i.situacao === "pausado");
  const pausa =
    pausados.length > 0
      ? ` Pausado: ${pausados.map((i) => (i.tipo === "cartao" ? nomeComFinal(i.nome) : i.nome)).join(", ")}.`
      : "";
  return `${nomes.join(", ")}${desde}.${pausa}`;
}

function Historico({ linhas, onStatus }: { linhas: LinhaHistorico[]; onStatus: (t: string) => void }) {
  const desfazer = useDesfazerImportacao();

  return (
    <Card className="flex flex-col px-8 py-9 md:px-11">
      <div className="flex items-baseline justify-between gap-5 pb-4">
        <h2 className="text-bloco-celular md:text-bloco font-forte m-0">Histórico de atualizações</h2>
        <span className="text-apoio text-texto-2">últimos {DIAS_DO_HISTORICO} dias</span>
      </div>
      {linhas.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">Nenhuma atualização nos últimos {DIAS_DO_HISTORICO} dias.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] table-fixed border-collapse">
            <colgroup>
              <col className="w-[150px]" />
              <col />
              <col className="w-[100px]" />
              <col className="w-[100px]" />
              <col className="w-[140px]" />
              <col className="w-[110px]" />
            </colgroup>
            <thead>
              <tr className="linha-abaixo text-pequeno text-texto-2 text-left">
                <th className="py-4 font-semibold">Quando</th>
                <th className="py-4 font-semibold">Origem</th>
                <th className="py-4 pr-6 text-right font-semibold">Entraram</th>
                <th className="py-4 pr-6 text-right font-semibold">Revisar</th>
                <th className="py-4 font-semibold">Situação</th>
                <th className="py-4">
                  <span className="sr-only">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => {
                const selo = SELO_DO_HISTORICO[l.situacao];
                const quando = quandoRelativo(l.criado_em);
                return (
                  <tr key={l.importacao_id} className="linha-abaixo-suave text-corpo">
                    <td className="text-texto-apoio py-6">{quando.charAt(0).toUpperCase() + quando.slice(1)}</td>
                    <td className="truncate py-6 pr-6" title={l.arquivo_nome}>
                      {origemDaImportacao(l)}
                    </td>
                    <td className="py-6 pr-6 text-right font-semibold">{l.entraram}</td>
                    <td className="py-6 pr-6 text-right font-semibold">{l.revisar}</td>
                    <td className="py-6">
                      <Selo tom={selo.tom}>{selo.rotulo}</Selo>
                    </td>
                    <td className="py-4 text-right">
                      {l.pode_desfazer ? (
                        <Button
                          variant="danger"
                          disabled={desfazer.isPending}
                          aria-label={`Desfazer a atualização de ${quando}`}
                          onClick={() => {
                            if (
                              window.confirm(
                                "Desfazer esta atualização? Tudo o que ela trouxe sai dos lançamentos e da revisão.",
                              )
                            ) {
                              desfazer.mutate(l.importacao_id, {
                                onSuccess: (r) =>
                                  onStatus(
                                    `Desfeita: ${r.transacoes} lançamento${r.transacoes === 1 ? "" : "s"} e ${r.itens} ite${r.itens === 1 ? "m" : "ns"} saíram.`,
                                  ),
                                onError: (e) =>
                                  onStatus(e instanceof ApiError ? e.detail : "Não foi possível desfazer."),
                              });
                            }
                          }}
                        >
                          Desfazer
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-apoio text-texto-2 m-0 mt-6 leading-normal">
        Desfazer remove tudo o que aquela atualização trouxe. Se o período ainda estiver dentro dos
        12 meses que o banco envia, a próxima atualização traz de volta.
      </p>
    </Card>
  );
}
