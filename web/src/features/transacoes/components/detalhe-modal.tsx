import { Button, PessoaBadge } from "@/components/ui/controls";
import { usePessoas } from "@/features/cadastros/queries";
import { corDoBalde, corSuaveDoBalde } from "@/features/filters/baldes";
import { formatBRLTexto, formatCompetencia, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Transacao } from "../types";

/** Detalhe de uma transação, com a exclusão (soft delete) à mão. */
export function DetalheModal({
  transacao,
  onFechar,
  onExcluir,
  excluindo,
}: {
  transacao: Transacao | null;
  onFechar: () => void;
  onExcluir: (id: number) => void;
  excluindo: boolean;
}) {
  const { data: pessoas = [] } = usePessoas();
  if (!transacao) return null;

  const receita = transacao.tipo === "receita";
  const transferencia = transacao.tipo === "transferencia";

  return (
    <>
      <div className="fixed inset-0 z-30 bg-black/50" onClick={onFechar} />
      <div
        role="dialog"
        aria-label={transacao.descricao}
        className="bg-surface shadow-modal fixed top-1/2 left-1/2 z-31 max-h-[80vh] w-220 -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl p-11"
      >
        <h2 className="text-title-lg text-text-primary mb-6 font-bold">{transacao.descricao}</h2>

        <dl className="text-body-lg grid grid-cols-[110px_1fr] gap-y-4">
          <Chave>Data</Chave>
          <Valor>{formatDate(transacao.data)}</Valor>

          <Chave>Competência</Chave>
          <Valor>{formatCompetencia(transacao.competencia)}</Valor>

          <Chave>Categoria</Chave>
          <Valor>{transacao.categoria_caminho ?? "— sem categoria —"}</Valor>

          <Chave>Pessoa</Chave>
          <Valor>
            <PessoaBadge
              nome={transacao.pessoa_nome}
              fundo={corSuaveDoBalde(transacao.pessoa_id ?? "conjunto", pessoas)}
              cor={corDoBalde(transacao.pessoa_id ?? "conjunto", pessoas)}
            />
          </Valor>

          <Chave>Pagamento</Chave>
          <Valor>{transacao.forma_pagamento_apelido ?? "—"}</Valor>

          <Chave>Local</Chave>
          <Valor>{transacao.local_nome ?? "—"}</Valor>

          {transacao.parcela_num ? (
            <>
              <Chave>Parcela</Chave>
              <Valor>
                {transacao.parcela_num} de {transacao.parcela_total}
              </Valor>
            </>
          ) : null}

          <Chave>Valor</Chave>
          <dd
            className={cn(
              "tabular text-title-sm font-bold",
              transferencia ? "text-text-tertiary" : receita ? "text-income" : "text-expense",
            )}
          >
            {transferencia ? "↔ " : receita ? "↑ " : "↓ "}
            {formatBRLTexto(transacao.valor)}
          </dd>

          {transacao.observacao ? (
            <>
              <Chave>Observação</Chave>
              <Valor>{transacao.observacao}</Valor>
            </>
          ) : null}
        </dl>

        {/* Texto cru do extrato — imutável (regra 11). Mostrado para conferir
            contra a fatura, nunca editável. */}
        {transacao.descricao_original ? (
          <div className="border-border-faint mt-8 border-t pt-6">
            <div className="text-label text-text-tertiary tracking-caps mb-2 font-semibold uppercase">
              Texto original do extrato
            </div>
            <p className="text-body-sm text-text-secondary font-mono">
              {transacao.descricao_original}
            </p>
          </div>
        ) : null}

        {/* Origem: fecha o rastro até o documento. Só aparece em lançamento
            importado — em transação digitada à mão não há o que mostrar, e um
            "Origem: —" seria ruído. */}
        {transacao.importacao_id ? (
          <div className="border-border-faint mt-8 border-t pt-6">
            <div className="text-label text-text-tertiary tracking-caps mb-2 font-semibold uppercase">
              Origem
            </div>
            <p className="text-body-sm text-text-secondary">
              Importado de{" "}
              <span className="text-text-primary font-medium">
                {transacao.importacao_arquivo ?? "arquivo sem nome"}
              </span>
              {transacao.importacao_em
                ? ` em ${new Date(transacao.importacao_em).toLocaleDateString("pt-BR")}`
                : null}
              .
            </p>
            {/* A view não traz o tipo do arquivo; a sync da Pluggy grava o
                comprovante como `.json`, e JSON não é "PDF original". */}
            {transacao.importacao_arquivo?.toLowerCase().endsWith(".json") ? (
              <p className="text-caption text-text-tertiary mt-2">
                Sincronizado pela Pluggy: não há PDF para abrir.
              </p>
            ) : transacao.importacao_tem_arquivo ? (
              <a
                href={`${import.meta.env.VITE_API_URL ?? ""}/importacoes/${transacao.importacao_id}/arquivo`}
                target="_blank"
                rel="noreferrer"
                className="text-body-sm text-accent mt-2 inline-block underline underline-offset-2"
              >
                Abrir o PDF original
              </a>
            ) : (
              // Importação anterior à migration 0004: o vínculo existe, o
              // arquivo não foi guardado. Dizer isso é melhor que oferecer um
              // link que daria 404.
              <p className="text-caption text-text-tertiary mt-2">
                O arquivo desta importação não foi guardado.
              </p>
            )}
          </div>
        ) : null}

        <div className="mt-9 flex justify-end gap-4">
          <Button
            variant="danger"
            disabled={excluindo}
            onClick={() => onExcluir(transacao.id)}
          >
            {excluindo ? "Excluindo..." : "Excluir transação"}
          </Button>
          <Button onClick={onFechar}>Fechar</Button>
        </div>
      </div>
    </>
  );
}

function Chave({ children }: { children: React.ReactNode }) {
  return (
    <dt className="text-caption text-text-tertiary tracking-label self-center uppercase">
      {children}
    </dt>
  );
}

function Valor({ children }: { children: React.ReactNode }) {
  return <dd className="text-text-primary">{children}</dd>;
}
