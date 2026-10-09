import { useState } from "react";

import { Checkbox, PessoaBadge, Select } from "@/components/ui/controls";
import { FormaPagamentoTag } from "@/features/cadastros/forma-pagamento-tag";
import { useCategoriaOpcoes, usePessoas } from "@/features/cadastros/queries";
import { corDoBalde, corSuaveDoBalde } from "@/features/filters/baldes";
import { formatBRLTexto, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Transacao, TransacaoUpdate } from "../types";

/**
 * Tabela densa de transações, com edição inline de categoria e pessoa.
 *
 * `<table>` de verdade em vez de grid de `div`: leitor de tela anuncia
 * cabeçalho por célula e a navegação por teclado funciona sem `role`
 * inventado. A densidade do protótipo vem do `table-fixed` + colgroup.
 *
 * A coluna de "itens da compra" do protótipo não está aqui: `itens_transacao`
 * é v2 (fase 7 do roadmap).
 */

type CampoEditando = { id: number; campo: "categoria" | "pessoa" } | null;

export function TransacoesTable({
  transacoes,
  selecionadas,
  onAlternarSelecao,
  onAlternarTodas,
  onAbrirDetalhe,
  onEditar,
}: {
  transacoes: Transacao[];
  selecionadas: Set<number>;
  onAlternarSelecao: (id: number) => void;
  onAlternarTodas: () => void;
  onAbrirDetalhe: (transacao: Transacao) => void;
  onEditar: (id: number, patch: TransacaoUpdate) => void;
}) {
  const [editando, setEditando] = useState<CampoEditando>(null);

  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();

  const todasMarcadas =
    transacoes.length > 0 && selecionadas.size === transacoes.length;

  return (
    // Padding no wrapper, não na `<table>`: padding em elemento de tabela não
    // se comporta como em bloco. Sem ele a coluna de valor encosta na borda
    // direita do card e o número parece cortado.
    <div className="px-6">
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col className="w-16" />
          <col className="w-46" />
          <col />
          <col className="w-95" />
          <col className="w-55" />
          <col className="w-55" />
          <col className="w-75" />
          <col className="w-65" />
        </colgroup>

        <thead>
          <tr className="border-border-faint border-b">
            <th className="px-3 py-4">
              <Checkbox
                checked={todasMarcadas}
                onChange={onAlternarTodas}
                aria-label="Selecionar todas as transações da página"
              />
            </th>
            <Th>Data</Th>
            <Th>Descrição</Th>
            <Th>Categoria</Th>
            <Th>Pagamento</Th>
            <Th>Pessoa</Th>
            <Th>Local</Th>
            <Th alinhamento="right">Valor</Th>
          </tr>
        </thead>

        <tbody>
          {transacoes.map((t) => {
            const selecionada = selecionadas.has(t.id);
            const receita = t.tipo === "receita";
            const transferencia = t.tipo === "transferencia";

            return (
              <tr
                key={t.id}
                onClick={() => onAbrirDetalhe(t)}
                className={cn(
                  "border-border-faint hover:bg-surface/50 cursor-pointer border-b",
                  selecionada && "bg-surface",
                )}
              >
                <td className="px-3 py-4" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selecionada}
                    onChange={() => onAlternarSelecao(t.id)}
                    aria-label={`Selecionar ${t.descricao}`}
                  />
                </td>

                <td className="tabular text-body-sm text-text-secondary py-4">
                  {formatDate(t.data)}
                </td>

                <td className="text-body text-text-primary truncate py-4 pr-4">
                  {t.descricao}
                  {t.parcela_num ? (
                    <span className="text-text-tertiary text-caption ml-2">
                      {t.parcela_num}/{t.parcela_total}
                    </span>
                  ) : null}
                </td>

                {/* Categoria — edição inline */}
                <td
                  className="text-body-sm py-4 pr-4"
                  onClick={(e) => e.stopPropagation()}
                >
                  {editando?.id === t.id && editando.campo === "categoria" ? (
                    <Select
                      autoFocus
                      className="border-accent w-full border"
                      value={t.categoria_id ?? ""}
                      onBlur={() => setEditando(null)}
                      onChange={(e) => {
                        onEditar(t.id, {
                          categoria_id:
                            e.target.value === ""
                              ? null
                              : Number(e.target.value),
                        });
                        setEditando(null);
                      }}
                    >
                      <option value="">— sem categoria —</option>
                      {categorias.map((opcao) => (
                        <option key={opcao.id} value={opcao.id}>
                          {opcao.label}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <span
                      onClick={() =>
                        transferencia
                          ? undefined
                          : setEditando({ id: t.id, campo: "categoria" })
                      }
                      className={cn(
                        "block truncate",
                        transferencia ? "text-text-tertiary" : "cursor-text",
                      )}
                      title={t.categoria_caminho ?? undefined}
                    >
                      {transferencia ? (
                        "—"
                      ) : t.categoria_pai_nome ? (
                        <>
                          <span className="text-text-primary font-medium">
                            {t.categoria_pai_nome}
                          </span>
                          <span className="text-text-tertiary">
                            {" "}
                            › {t.categoria_nome}
                          </span>
                        </>
                      ) : (
                        <span className="text-text-primary font-medium">
                          {t.categoria_nome ?? "— sem categoria —"}
                        </span>
                      )}
                    </span>
                  )}
                </td>

                <td className="py-4 pr-4">
                  <FormaPagamentoTag
                    tipo={t.forma_pagamento_tipo}
                    apelido={t.forma_pagamento_apelido}
                  />
                </td>

                {/* Pessoa — edição inline */}
                <td className="py-4 pr-4" onClick={(e) => e.stopPropagation()}>
                  {editando?.id === t.id && editando.campo === "pessoa" ? (
                    <Select
                      autoFocus
                      className="border-accent w-full border"
                      value={t.pessoa_id ?? "conjunto"}
                      onBlur={() => setEditando(null)}
                      onChange={(e) => {
                        // Conjunto é `pessoa_id` nulo, não uma pessoa (D-03).
                        onEditar(t.id, {
                          pessoa_id:
                            e.target.value === "conjunto"
                              ? null
                              : Number(e.target.value),
                        });
                        setEditando(null);
                      }}
                    >
                      {pessoas.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome}
                        </option>
                      ))}
                      <option value="conjunto">Conjunto</option>
                    </Select>
                  ) : (
                    <PessoaBadge
                      nome={t.pessoa_nome}
                      fundo={corSuaveDoBalde(
                        t.pessoa_id ?? "conjunto",
                        pessoas,
                      )}
                      cor={corDoBalde(t.pessoa_id ?? "conjunto", pessoas)}
                      onClick={() => setEditando({ id: t.id, campo: "pessoa" })}
                    />
                  )}
                </td>

                <td className="text-body-sm text-text-secondary truncate py-4 pr-4">
                  {t.local_nome ?? "—"}
                </td>

                <td
                  className={cn(
                    "tabular py-4 text-right font-bold",
                    transferencia
                      ? "text-text-tertiary"
                      : receita
                        ? "text-income"
                        : "text-expense",
                  )}
                >
                  {transferencia ? "↔ " : receita ? "↑ " : "↓ "}
                  {formatBRLTexto(t.valor)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  alinhamento = "left",
}: {
  children: React.ReactNode;
  alinhamento?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "text-label text-text-tertiary tracking-caps-wide py-4 font-semibold uppercase",
        alinhamento === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}
