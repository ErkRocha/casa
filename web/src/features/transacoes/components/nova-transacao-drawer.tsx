import { useState } from "react";

import { Button, Input, Select } from "@/components/ui/controls";
import {
  useCategoriaOpcoes,
  useFormasPagamento,
  usePessoas,
} from "@/features/cadastros/queries";
import type { TipoTransacao } from "@/features/filters/types";
import type { TransacaoCreate } from "../types";

/**
 * Drawer de lançamento manual.
 *
 * O usuário digita o local livre; a API casa pelo nome normalizado ou cria,
 * em vez de exigir cadastro prévio. Sem `competencia`, vale o mês da data
 * (D-02) — o campo só aparece quando ele quer jogar para outra fatura.
 *
 * Itens da compra ficaram de fora: `itens_transacao` é v2 (fase 7).
 */
export function NovaTransacaoDrawer({
  aberto,
  onFechar,
  onSalvar,
  salvando,
  erro,
}: {
  aberto: boolean;
  onFechar: () => void;
  onSalvar: (payload: TransacaoCreate & { local_nome?: string }) => void;
  salvando: boolean;
  erro: string | null;
}) {
  const hoje = new Date().toISOString().slice(0, 10);

  const [data, setData] = useState(hoje);
  const [competencia, setCompetencia] = useState("");
  const [tipo, setTipo] = useState<TipoTransacao>("despesa");
  const [descricao, setDescricao] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [pessoa, setPessoa] = useState("conjunto");
  const [formaPagamentoId, setFormaPagamentoId] = useState("");
  const [local, setLocal] = useState("");
  const [valor, setValor] = useState("");

  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();
  const { data: formas = [] } = useFormasPagamento();

  if (!aberto) return null;

  const valorNumerico = Number(valor.replace(",", "."));
  const podeSalvar = descricao.trim() !== "" && valorNumerico > 0 && !salvando;

  function salvar() {
    onSalvar({
      data,
      competencia: competencia || null,
      tipo,
      valor: String(valorNumerico.toFixed(2)),
      descricao: descricao.trim(),
      categoria_id: tipo === "transferencia" || categoriaId === "" ? null : Number(categoriaId),
      pessoa_id: pessoa === "conjunto" ? null : Number(pessoa),
      forma_pagamento_id: formaPagamentoId === "" ? null : Number(formaPagamentoId),
      local_nome: local.trim() || undefined,
    });
  }

  return (
    <>
      <div className="fixed inset-0 z-30 bg-black/50" onClick={onFechar} />
      <aside
        role="dialog"
        aria-label="Nova transação"
        className="bg-surface border-border-faint fixed top-0 right-0 z-31 flex h-full w-190 flex-col gap-2 overflow-y-auto border-l p-10"
      >
        <h2 className="text-title-lg text-text-primary mb-6 font-bold">Nova transação</h2>

        <Campo label="Tipo">
          <Select
            className="w-full"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoTransacao)}
          >
            <option value="despesa">Despesa</option>
            <option value="receita">Receita</option>
          </Select>
        </Campo>

        <Campo label="Data">
          <Input
            className="w-full"
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
        </Campo>

        <Campo label="Competência (opcional)">
          <Input
            className="w-full"
            type="month"
            value={competencia ? competencia.slice(0, 7) : ""}
            onChange={(e) => setCompetencia(e.target.value ? `${e.target.value}-01` : "")}
          />
          <p className="text-caption text-text-tertiary mt-2">
            Vazio usa o mês da data. Preencha quando a compra cair na fatura de outro mês.
          </p>
        </Campo>

        <Campo label="Descrição">
          <Input
            className="w-full"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            placeholder="Ex: Compras do mês"
          />
        </Campo>

        <Campo label="Categoria">
          <Select
            className="w-full"
            value={categoriaId}
            onChange={(e) => setCategoriaId(e.target.value)}
          >
            <option value="">— sem categoria —</option>
            {categorias.map((opcao) => (
              <option key={opcao.id} value={opcao.id}>
                {opcao.label}
              </option>
            ))}
          </Select>
        </Campo>

        <Campo label="Pessoa">
          <Select className="w-full" value={pessoa} onChange={(e) => setPessoa(e.target.value)}>
            {pessoas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
            <option value="conjunto">Conjunto</option>
          </Select>
        </Campo>

        <Campo label="Forma de pagamento">
          <Select
            className="w-full"
            value={formaPagamentoId}
            onChange={(e) => setFormaPagamentoId(e.target.value)}
          >
            <option value="">— não informado —</option>
            {formas.map((f) => (
              <option key={f.id} value={f.id}>
                {f.apelido}
              </option>
            ))}
          </Select>
        </Campo>

        <Campo label="Local">
          <Input
            className="w-full"
            value={local}
            onChange={(e) => setLocal(e.target.value)}
            placeholder="Ex: Supermercado Extra"
          />
        </Campo>

        <Campo label="Valor (R$)">
          <Input
            className="tabular w-full"
            inputMode="decimal"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            placeholder="0,00"
          />
        </Campo>

        {erro ? (
          <p role="alert" className="text-body-sm text-expense mt-4">
            {erro}
          </p>
        ) : null}

        <div className="mt-9 flex justify-end gap-4">
          <Button variant="secondary" onClick={onFechar}>
            Cancelar
          </Button>
          <Button onClick={salvar} disabled={!podeSalvar}>
            {salvando ? "Salvando..." : "Salvar transação"}
          </Button>
        </div>
      </aside>
    </>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="mt-5 flex flex-col">
      <span className="text-caption text-text-tertiary tracking-label-wide mb-2 font-semibold uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}
