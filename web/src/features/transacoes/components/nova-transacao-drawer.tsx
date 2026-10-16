import { useState, type ReactNode } from "react";

import { Button, Input, Select } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { rotuloDaForma } from "@/features/cadastros/forma-pagamento";
import {
  useContas,
  useFormasPagamento,
  useGruposDeCategoria,
  usePessoas,
} from "@/features/cadastros/queries";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import type { TipoTransacao } from "@/features/filters/types";
import { sinal, valorDigitado } from "@/lib/format";
import type { TransacaoCreate } from "../types";

/**
 * Lançamento à mão: painel à direita no computador, tela cheia no celular.
 *
 * O local é digitado livre; a API casa pelo nome normalizado ou cria. Sem
 * mês informado vale o mês da data (D-02). O valor vai como texto, lido
 * sem `float` (regra 1).
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
  return (
    <Dialogo aberto={aberto} onFechar={onFechar} titulo="Novo lançamento" lateral>
      <Formulario onSalvar={onSalvar} onFechar={onFechar} salvando={salvando} erro={erro} />
    </Dialogo>
  );
}

function Formulario({
  onFechar,
  onSalvar,
  salvando,
  erro,
}: {
  onFechar: () => void;
  onSalvar: (payload: TransacaoCreate & { local_nome?: string }) => void;
  salvando: boolean;
  erro: string | null;
}) {
  const hoje = new Date();
  const hojeIso = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}-${String(hoje.getDate()).padStart(2, "0")}`;

  const [data, setData] = useState(hojeIso);
  const [competencia, setCompetencia] = useState("");
  const [tipo, setTipo] = useState<TipoTransacao>("despesa");
  const [descricao, setDescricao] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [pessoa, setPessoa] = useState("conjunto");
  const [formaPagamentoId, setFormaPagamentoId] = useState("");
  const [local, setLocal] = useState("");
  const [valor, setValor] = useState("");

  const { data: grupos } = useGruposDeCategoria();
  const { data: pessoas = [] } = usePessoas();
  const { data: formas = [] } = useFormasPagamento();
  const { data: contas = [] } = useContas();
  const nomeDaConta = new Map(contas.map((c) => [c.id, c.nome]));

  const valorLido = valorDigitado(valor);
  const valorValido = valorLido !== null && sinal(valorLido) === 1;
  const podeSalvar = descricao.trim() !== "" && valorValido && !salvando;

  function salvar() {
    if (!valorLido) return;
    onSalvar({
      data,
      competencia: competencia || null,
      tipo,
      valor: valorLido,
      descricao: descricao.trim(),
      categoria_id: categoriaId === "" ? null : Number(categoriaId),
      pessoa_id: pessoa === "conjunto" ? null : Number(pessoa),
      forma_pagamento_id: formaPagamentoId === "" ? null : Number(formaPagamentoId),
      local_nome: local.trim() || undefined,
    });
  }

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(evento) => {
        evento.preventDefault();
        if (podeSalvar) salvar();
      }}
    >
      <Campo rotulo="Tipo">
        <Select
          className="w-full"
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoTransacao);
            setCategoriaId("");
          }}
        >
          <option value="despesa">Despesa</option>
          <option value="receita">Receita</option>
        </Select>
      </Campo>

      <Campo rotulo="Descrição">
        <Input
          className="w-full"
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Ex.: Compras do mês"
          required
        />
      </Campo>

      <Campo rotulo="Valor" ajuda={valor && !valorValido ? "Escreva como 186,40." : undefined}>
        <Input
          className="w-full"
          inputMode="decimal"
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          placeholder="0,00"
          aria-invalid={valor !== "" && !valorValido}
          required
        />
      </Campo>

      <Campo rotulo="Data">
        <Input
          className="w-full"
          type="date"
          value={data}
          onChange={(e) => setData(e.target.value)}
        />
      </Campo>

      <Campo
        rotulo="Mês da fatura (opcional)"
        ajuda="Vazio usa o mês da data. Preencha quando a compra cair na fatura de outro mês."
      >
        <Input
          className="w-full"
          type="month"
          value={competencia ? competencia.slice(0, 7) : ""}
          onChange={(e) => setCompetencia(e.target.value ? `${e.target.value}-01` : "")}
        />
      </Campo>

      <Campo rotulo="Categoria">
        <Select
          className="w-full"
          value={categoriaId}
          onChange={(e) => setCategoriaId(e.target.value)}
        >
          <option value="">Sem categoria</option>
          {grupos
            .filter((g) => g.tipo === tipo)
            .map((grupo) => (
              <optgroup key={grupo.raizId} label={grupo.raizNome}>
                {grupo.opcoes.map((opcao) => (
                  <option key={opcao.id} value={opcao.id}>
                    {opcao.nome}
                  </option>
                ))}
              </optgroup>
            ))}
        </Select>
      </Campo>

      <Campo rotulo="Quem">
        <Select className="w-full" value={pessoa} onChange={(e) => setPessoa(e.target.value)}>
          {pessoas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
          <option value="conjunto">{ROTULO_JUNTOS}</option>
        </Select>
      </Campo>

      <Campo rotulo="Pagamento">
        <Select
          className="w-full"
          value={formaPagamentoId}
          onChange={(e) => setFormaPagamentoId(e.target.value)}
        >
          <option value="">Não informado</option>
          {formas.map((f) => (
            <option key={f.id} value={f.id}>
              {rotuloDaForma(f.tipo, f.apelido, f.conta_id ? nomeDaConta.get(f.conta_id) : null)}
            </option>
          ))}
        </Select>
      </Campo>

      <Campo rotulo="Local (opcional)">
        <Input
          className="w-full"
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          placeholder="Ex.: Supermercado Centro"
        />
      </Campo>

      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}

      <div className="flex flex-wrap justify-end gap-4 pt-2">
        <Button variant="secondary" onClick={onFechar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!podeSalvar}>
          {salvando ? "Salvando..." : "Salvar lançamento"}
        </Button>
      </div>
    </form>
  );
}

function Campo({
  rotulo,
  ajuda,
  children,
}: {
  rotulo: string;
  ajuda?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-3">
      <span className="text-apoio font-semibold">{rotulo}</span>
      {children}
      {ajuda ? <span className="text-pequeno text-texto-2">{ajuda}</span> : null}
    </label>
  );
}
