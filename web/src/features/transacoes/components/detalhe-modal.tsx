import type { ReactNode } from "react";

import { Button } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { FormaPagamentoTag } from "@/features/cadastros/forma-pagamento-tag";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import { urlDaApi } from "@/lib/api";
import { diaDeMes, mesPorExtenso, reaisDoLancamento } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Transacao } from "../types";

/** Detalhe de um lançamento, com a exclusão (soft delete) à mão. */
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
  return (
    <Dialogo aberto={transacao !== null} onFechar={onFechar} titulo={transacao?.descricao ?? ""}>
      {transacao ? (
        <Conteudo
          transacao={transacao}
          excluindo={excluindo}
          onExcluir={onExcluir}
          onFechar={onFechar}
        />
      ) : null}
    </Dialogo>
  );
}

function Conteudo({
  transacao,
  excluindo,
  onExcluir,
  onFechar,
}: {
  transacao: Transacao;
  excluindo: boolean;
  onExcluir: (id: number) => void;
  onFechar: () => void;
}) {
  const ano = transacao.data.slice(0, 4);
  return (
    <>
      <p
        className={cn(
          "text-valor m-0 pb-6 font-bold",
          transacao.tipo === "receita" && "text-receita",
          transacao.tipo === "transferencia" && "text-texto-2",
        )}
      >
        {reaisDoLancamento(transacao.valor, transacao.tipo)}
      </p>

      <dl className="text-corpo m-0 grid grid-cols-[120px_1fr] gap-x-6 gap-y-5">
        <Chave>Data</Chave>
        <Valor>
          {diaDeMes(transacao.data)} de {ano}
        </Valor>

        <Chave>Mês</Chave>
        <Valor>{mesPorExtenso(transacao.competencia)}</Valor>

        <Chave>Categoria</Chave>
        <Valor>
          {transacao.tipo === "transferencia"
            ? "Transferência, sem categoria"
            : (transacao.categoria_caminho ?? "Sem categoria")}
        </Valor>

        <Chave>Quem</Chave>
        <Valor>{transacao.pessoa_id === null ? ROTULO_JUNTOS : transacao.pessoa_nome}</Valor>

        <Chave>Pagamento</Chave>
        <Valor>
          <FormaPagamentoTag
            tipo={transacao.forma_pagamento_tipo}
            apelido={transacao.forma_pagamento_apelido}
            contaNome={transacao.forma_pagamento_conta_nome}
          />
        </Valor>

        {transacao.local_nome ? (
          <>
            <Chave>Local</Chave>
            <Valor>{transacao.local_nome}</Valor>
          </>
        ) : null}

        {transacao.parcela_num ? (
          <>
            <Chave>Parcela</Chave>
            <Valor>
              {transacao.parcela_num} de {transacao.parcela_total}
            </Valor>
          </>
        ) : null}

        {transacao.observacao ? (
          <>
            <Chave>Observação</Chave>
            <Valor>{transacao.observacao}</Valor>
          </>
        ) : null}
      </dl>

      {/* Texto cru do extrato — imutável (regra 11). Para conferir contra o
          documento, nunca editável. */}
      {transacao.descricao_original ? (
        <Secao titulo="Texto original do banco">
          <p className="text-apoio text-texto-apoio m-0 break-words">
            {transacao.descricao_original}
          </p>
        </Secao>
      ) : null}

      {/* Origem: o rastro até o documento. Só em lançamento importado. */}
      {transacao.importacao_id ? (
        <Secao titulo="Origem">
          <p className="text-apoio text-texto-2 m-0">
            Importado de{" "}
            <span className="text-texto font-medio">
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
            <p className="text-pequeno text-texto-2 m-0 mt-2">
              Veio da sincronização com o banco: não há PDF para abrir.
            </p>
          ) : transacao.importacao_tem_arquivo ? (
            <a
              href={urlDaApi(`/importacoes/${transacao.importacao_id}/arquivo`)}
              target="_blank"
              rel="noreferrer"
              className="text-apoio mt-2 inline-block font-semibold"
            >
              Abrir o PDF original
            </a>
          ) : (
            // Importação anterior à migration 0004: o vínculo existe, o
            // arquivo não foi guardado.
            <p className="text-pequeno text-texto-2 m-0 mt-2">
              O arquivo desta importação não foi guardado.
            </p>
          )}
        </Secao>
      ) : null}

      <div className="mt-10 flex flex-wrap justify-end gap-4">
        <Button variant="danger" disabled={excluindo} onClick={() => onExcluir(transacao.id)}>
          {excluindo ? "Excluindo..." : "Excluir lançamento"}
        </Button>
        <Button variant="secondary" onClick={onFechar}>
          Fechar
        </Button>
      </div>
    </>
  );
}

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="linha-acima mt-8 pt-6">
      <h3 className="text-apoio font-forte m-0 mb-2">{titulo}</h3>
      {children}
    </div>
  );
}

function Chave({ children }: { children: ReactNode }) {
  return <dt className="text-apoio text-texto-2">{children}</dt>;
}

function Valor({ children }: { children: ReactNode }) {
  return <dd className="text-texto m-0">{children}</dd>;
}
