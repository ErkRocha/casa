import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/controls";
import { ApiError, urlDaApi } from "@/lib/api";
import { formatBRLTexto, formatDate, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useReaplicarRegras } from "@/features/regras/queries";
import { RevisaoTable } from "./components/revisao-table";
import { UploadZone } from "./components/upload-zone";
import {
  useAprovarItens,
  useDesfazerImportacao,
  useImportacao,
  useImportacoes,
  useRejeitarItens,
} from "./queries";
import {
  ORIGEM_LABEL,
  STATUS_IMPORTACAO_LABEL,
  ehPdf,
  type ResultadoAprovacao,
  type ResultadoDesfazer,
} from "./types";

/**
 * Tela de importação e revisão — passo 4 da fase 5.
 *
 * O ponto inteiro dela é a D-07: o agente escreve no staging, e é aqui que o
 * humano decide o que vira dado real. A única exceção é o item limpo da sync
 * da Pluggy, que a própria sync promove (D-21) — e é daqui que se desfaz uma
 * importação inteira, se ela entrou errada.
 */
export function ImportacoesPage() {
  const [selecionadaId, setSelecionadaId] = useState<number | null>(null);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [resultado, setResultado] = useState<ResultadoAprovacao | null>(null);
  const [confirmandoDesfazer, setConfirmandoDesfazer] = useState(false);
  const [desfeita, setDesfeita] = useState<
    (ResultadoDesfazer & { arquivo: string }) | null
  >(null);

  const lista = useImportacoes();
  const detalhe = useImportacao(selecionadaId);
  const aprovar = useAprovarItens();
  const rejeitar = useRejeitarItens();
  const desfazer = useDesfazerImportacao();
  const reaplicar = useReaplicarRegras();

  const itens = detalhe.data?.itens ?? [];
  const pendentes = itens.filter((item) => item.status === "pendente");

  function limparSelecao() {
    setSelecionados(new Set());
  }

  function alternar(id: number) {
    setSelecionados((atual) => {
      const proxima = new Set(atual);
      if (proxima.has(id)) proxima.delete(id);
      else proxima.add(id);
      return proxima;
    });
  }

  function alternarTodos() {
    setSelecionados((atual) =>
      atual.size === pendentes.length ? new Set() : new Set(pendentes.map((i) => i.id)),
    );
  }

  if (selecionadaId === null) {
    return (
      <>
        <UploadZone onImportado={setSelecionadaId} />

        {desfeita ? (
          <div role="status" className="bg-surface mt-8 rounded-md px-8 py-5">
            <p className="text-body text-text-primary">
              Importação {desfeita.arquivo} desfeita: {desfeita.transacoes} transação(ões) e{" "}
              {desfeita.itens} item(ns) apagados. Tudo fica na auditoria.
            </p>
          </div>
        ) : null}

        <h2 className="text-caption text-text-tertiary tracking-caps-wide mt-14 mb-5 font-semibold uppercase">
          Importações
        </h2>

        {lista.isLoading ? (
          <div className="bg-surface-sunken animate-shimmer h-60 rounded-md" />
        ) : (lista.data ?? []).length === 0 ? (
          <p className="text-body text-text-tertiary">
            Nenhuma importação ainda. Suba o primeiro PDF acima.
          </p>
        ) : (
          <Card>
            {(lista.data ?? []).map((importacao) => (
              <button
                key={importacao.id}
                type="button"
                onClick={() => {
                  setSelecionadaId(importacao.id);
                  limparSelecao();
                  setResultado(null);
                  setConfirmandoDesfazer(false);
                  setDesfeita(null);
                }}
                className="border-border-faint hover:bg-surface flex w-full cursor-pointer items-center gap-6 border-b px-8 py-5 text-left last:border-b-0"
              >
                <span className="text-body text-text-primary flex-1 truncate font-medium">
                  {importacao.arquivo_nome}
                </span>
                <span className="text-body-sm text-text-tertiary w-50">
                  {ORIGEM_LABEL[importacao.origem ?? ""] ?? importacao.origem ?? "—"}
                </span>
                <span className="text-body-sm text-text-secondary tabular w-40 text-right">
                  {importacao.itens_aprovados}/{importacao.total_itens}
                </span>
                <span
                  className={cn(
                    "text-body-sm w-50 text-right",
                    importacao.status === "concluida"
                      ? "text-income"
                      : importacao.erro_mensagem
                        ? "text-expense"
                        : "text-text-secondary",
                  )}
                >
                  {STATUS_IMPORTACAO_LABEL[importacao.status]}
                </span>
              </button>
            ))}
          </Card>
        )}
      </>
    );
  }

  if (detalhe.isLoading || !detalhe.data) {
    return <div className="bg-surface-sunken animate-shimmer h-120 rounded-md" />;
  }

  const { importacao } = detalhe.data;

  /* A conferência é sobre o que o parser LEU, não sobre o que sobrou para
     aprovar. Somar só os pendentes fazia o banner virar "não fecha" assim que
     tudo era aprovado — pendente ia a zero e o alarme disparava justamente
     quando estava tudo certo. Item rejeitado sai da conta porque o usuário
     decidiu que ele não conta. */
  const soma = itens
    .filter(
      (i) =>
        (i.status === "pendente" || i.status === "aprovado") &&
        i.tipo_sugerido === "despesa",
    )
    .reduce((total, i) => total + toNumero(i.valor), 0);
  const declarado = toNumero(importacao.total_declarado);
  const confere = declarado > 0 && Math.abs(soma - declarado) < 0.005;
  const temRejeitado = itens.some((i) => i.status === "rejeitado");

  return (
    <>
      <div className="mb-8 flex items-center gap-5">
        <Button
          variant="ghost"
          onClick={() => {
            setSelecionadaId(null);
            limparSelecao();
          }}
          className="px-0"
        >
          ← Importações
        </Button>
        <span className="text-body text-text-primary font-semibold">
          {importacao.arquivo_nome}
        </span>
        <span className="text-body-sm text-text-tertiary">
          {ORIGEM_LABEL[importacao.origem ?? ""] ?? importacao.origem}
          {importacao.periodo_inicio && importacao.periodo_fim
            ? ` · ${formatDate(importacao.periodo_inicio)} a ${formatDate(importacao.periodo_fim)}`
            : ""}
        </span>
        {/* Só PDF se reabre. A sync da Pluggy guarda o JSON bruto como
            comprovante, mas ele não é documento para conferir na tela. */}
        {ehPdf(importacao) ? (
          <a
            href={urlDaApi(`/importacoes/${importacao.id}/arquivo`)}
            target="_blank"
            rel="noreferrer"
            className="text-body-sm text-accent ml-auto underline underline-offset-2"
          >
            Abrir o PDF
          </a>
        ) : null}
        {importacao.status !== "cancelada" ? (
          <Button
            variant="danger"
            onClick={() => setConfirmandoDesfazer(true)}
            className={cn("px-0", ehPdf(importacao) ? "" : "ml-auto")}
          >
            Desfazer importação
          </Button>
        ) : null}
      </div>

      {/* Confirmação em dois passos: desfazer apaga transações já lançadas,
          inclusive as editadas depois. Volta pela auditoria (D-06). */}
      {confirmandoDesfazer ? (
        <div
          role="alertdialog"
          aria-labelledby="desfazer-titulo"
          aria-describedby="desfazer-texto"
          className="bg-alert-soft mb-8 rounded-md px-8 py-5"
        >
          <p id="desfazer-titulo" className="text-body text-alert font-semibold">
            Desfazer esta importação?
          </p>
          <p id="desfazer-texto" className="text-body-sm text-text-secondary mt-2">
            Apaga as {importacao.itens_aprovados} transação(ões) lançadas por ela, inclusive as
            que você editou depois, e os {importacao.total_itens} itens da revisão, e marca a
            importação como cancelada. Tudo fica na auditoria e pode voltar.
            {importacao.origem === "pluggy"
              ? " A próxima sync traz de volta o que ainda estiver na janela dela."
              : ""}
          </p>
          <div className="mt-4 flex gap-4">
            <Button
              variant="danger"
              disabled={desfazer.isPending}
              onClick={() =>
                desfazer.mutate(importacao.id, {
                  onSuccess: (dados) => {
                    setDesfeita({ ...dados, arquivo: importacao.arquivo_nome });
                    setConfirmandoDesfazer(false);
                    setSelecionadaId(null);
                    limparSelecao();
                  },
                })
              }
              className="px-6 py-3"
            >
              {desfazer.isPending ? "Desfazendo..." : "Confirmar desfazer"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => setConfirmandoDesfazer(false)}
              className="px-6 py-3"
            >
              Cancelar
            </Button>
          </div>
          {desfazer.error instanceof ApiError ? (
            <p role="alert" className="text-body-sm text-expense mt-3">
              {desfazer.error.detail}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* A conferência contra o total do próprio documento. É o que permite
          aprovar sem reconferir linha a linha na mão. */}
      {declarado > 0 ? (
        <div
          className={cn(
            "mb-8 flex flex-wrap items-center gap-6 rounded-md px-8 py-5",
            confere ? "bg-income-soft" : "bg-alert-soft",
          )}
        >
          <span className={cn("text-body font-semibold", confere ? "text-income" : "text-alert")}>
            {confere
              ? "A extração fecha com o documento"
              : temRejeitado
                ? "A soma difere do documento (há itens rejeitados)"
                : "A extração NÃO fecha"}
          </span>
          <span className="text-body-sm text-text-secondary">
            lido <span className="tabular font-semibold">{formatBRLTexto(String(soma))}</span>
            {" · "}
            documento declara{" "}
            <span className="tabular font-semibold">
              {formatBRLTexto(importacao.total_declarado)}
            </span>
          </span>
        </div>
      ) : null}

      {importacao.erro_mensagem ? (
        <p role="alert" className="text-body-sm text-expense mb-8">
          {importacao.erro_mensagem}
        </p>
      ) : null}

      {resultado ? (
        <div className="bg-surface mb-8 rounded-md px-8 py-5">
          <p className="text-body text-text-primary">
            {resultado.promovidos} promovida(s)
            {resultado.duplicados > 0
              ? ` · ${resultado.duplicados} já existia(m) e foram marcadas como duplicadas`
              : ""}
            {resultado.erros.length > 0 ? ` · ${resultado.erros.length} recusada(s)` : ""}
          </p>
          {resultado.erros.slice(0, 3).map((erro) => (
            <p key={erro.item_id} className="text-body-sm text-text-tertiary mt-2">
              {erro.erro}
            </p>
          ))}
        </div>
      ) : null}

      <Card>
        {selecionados.size > 0 ? (
          <div className="bg-surface border-border-faint flex flex-wrap items-center gap-4 border-b px-8 py-5">
            <span className="text-body text-text-primary mr-2 font-semibold">
              {selecionados.size} selecionado(s)
            </span>
            <Button
              disabled={aprovar.isPending}
              onClick={() =>
                aprovar.mutate([...selecionados], {
                  onSuccess: (dados) => {
                    setResultado(dados);
                    limparSelecao();
                  },
                })
              }
              className="px-6 py-3"
            >
              {aprovar.isPending ? "Promovendo..." : "Aprovar e lançar"}
            </Button>
            <Button
              variant="danger"
              disabled={rejeitar.isPending}
              onClick={() =>
                rejeitar.mutate(
                  { ids: [...selecionados], motivo: "rejeitado na revisão" },
                  { onSuccess: limparSelecao },
                )
              }
              className="px-6 py-3"
            >
              Rejeitar
            </Button>
            <Button variant="ghost" onClick={limparSelecao} className="px-6 py-3">
              Cancelar
            </Button>
          </div>
        ) : null}

        <div className="border-border-faint text-caption-lg text-text-tertiary flex flex-wrap items-center gap-6 border-b px-8 py-4">
          <span>
            {itens.length} linha(s) · {pendentes.length} pendente(s)
          </span>
          {pendentes.length > 0 ? (
            <>
              {/* Depois de corrigir uma linha, isto resolve as outras iguais
                  sem tocar em cada uma (D-09). */}
              <Button
                variant="ghost"
                disabled={reaplicar.isPending}
                onClick={() => reaplicar.mutate(importacao.id)}
                className="px-0 py-0"
                title="Roda as regras de categorização de novo sobre os itens pendentes"
              >
                {reaplicar.isPending ? "Reaplicando..." : "Reaplicar regras"}
              </Button>
              {reaplicar.data ? (
                <span>
                  {reaplicar.data.alterados} de {reaplicar.data.avaliados} atualizados
                </span>
              ) : null}
              <Button variant="ghost" onClick={alternarTodos} className="ml-auto px-0 py-0">
                {selecionados.size === pendentes.length
                  ? "Limpar seleção"
                  : "Selecionar todos os pendentes"}
              </Button>
            </>
          ) : null}
        </div>

        <RevisaoTable
          itens={itens}
          selecionados={selecionados}
          onAlternar={alternar}
          onAlternarTodos={alternarTodos}
        />
      </Card>

      {aprovar.error instanceof ApiError ? (
        <p role="alert" className="text-body-sm text-expense mt-5">
          {aprovar.error.detail}
        </p>
      ) : null}
    </>
  );
}
