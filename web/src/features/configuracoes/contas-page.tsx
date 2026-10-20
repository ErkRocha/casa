import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button, Input, Select, Selo } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Carregando, Falha, Vazio } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { usePessoas } from "@/features/cadastros/queries";
import type { TipoConta } from "@/features/cadastros/types";
import { diaDeMes } from "@/lib/format";
import { href } from "@/lib/rotas";
import { Campo, ErroDoFormulario } from "./formulario";
import { useContasECartoes, useCriarConta, useRenomear } from "./queries";
import {
  detalheDoItem,
  nomeComFinal,
  ROTULO_TIPO_CONTA,
  SELO_DA_SITUACAO,
  tipoDoItem,
} from "./textos";
import type { GrupoContas, ItemContaCartao } from "./types";

/**
 * Contas e cartões (`ContasDesktop`; D-22): por banco, cada cartão dentro da
 * conta que paga a fatura, com a situação da sincronização. Os cartões
 * virtuais aparecem no cartão principal: não têm forma própria (Fase 5b).
 */
export function ContasPage() {
  const contas = useContasECartoes();
  const [novaAberta, setNovaAberta] = useState(false);
  const [editando, setEditando] = useState<ItemContaCartao | null>(null);

  return (
    <div className="flex max-w-[1000px] flex-col gap-7 md:gap-8">
      <header className="flex flex-wrap items-center gap-6">
        <div className="flex flex-[1_1_auto] flex-col gap-2">
          <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">
            Contas e cartões
          </h1>
          <p className="text-corpo text-texto-2 m-0">
            Cada cartão aparece dentro da conta que paga a fatura dele.
          </p>
        </div>
        <Button variant="secondary" onClick={() => setNovaAberta(true)} className="text-corpo">
          Adicionar conta manual
        </Button>
      </header>

      {contas.isLoading ? (
        <Carregando rotulo="Carregando as contas" alturas={["h-80", "h-80"]} />
      ) : contas.isError || !contas.data ? (
        <Falha
          titulo="Não foi possível carregar as contas"
          erro={contas.error}
          onTentar={() => void contas.refetch()}
        />
      ) : contas.data.grupos.length === 0 ? (
        <Vazio
          titulo="Nenhuma conta ainda"
          texto="As contas aparecem aqui quando o banco é conectado (make pluggy-mapear no computador de casa) ou quando você adiciona uma conta manual."
        />
      ) : (
        contas.data.grupos.map((g) => (
          <Banco key={g.pluggy_item_id ?? "manuais"} grupo={g} onEditar={setEditando} />
        ))
      )}

      <p className="text-apoio text-texto-2 m-0">
        A sincronização de cada banco e o histórico ficam em{" "}
        <a href={href("sincronizacao")}>Sincronização</a>.
      </p>

      <NovaConta aberta={novaAberta} onFechar={() => setNovaAberta(false)} />
      <Renomear item={editando} onFechar={() => setEditando(null)} />
    </div>
  );
}

function Banco({ grupo, onEditar }: { grupo: GrupoContas; onEditar: (item: ItemContaCartao) => void }) {
  return (
    <Card className="flex flex-col gap-1 px-8 py-8 md:px-11 md:py-9">
      <div className="flex flex-wrap items-center justify-between gap-5 pb-4">
        <h2 className="m-0 text-[19px] font-bold">{grupo.titulo}</h2>
        <span className="text-pequeno text-texto-2">
          {grupo.pluggy_item_id
            ? grupo.desde
              ? `Conectado pelo Meu Pluggy desde ${diaDeMes(grupo.desde)} de ${grupo.desde.slice(0, 4)}`
              : "Conectado pelo Meu Pluggy"
            : "Lançadas à mão ou por PDF"}
        </span>
      </div>
      <ul className="m-0 flex list-none flex-col p-0">
        {grupo.itens.map((item) => (
          <Linha key={`${item.tipo}-${item.forma_pagamento_id ?? item.conta_id}`} item={item} onEditar={onEditar} />
        ))}
      </ul>
    </Card>
  );
}

function Linha({ item, onEditar }: { item: ItemContaCartao; onEditar: (item: ItemContaCartao) => void }) {
  const selo = SELO_DA_SITUACAO[item.situacao];
  const nome = item.tipo === "cartao" ? nomeComFinal(item.nome) : item.nome;
  return (
    <li className="linha-acima grid grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-x-7 gap-y-3 py-7 md:grid-cols-[40px_minmax(0,1.4fr)_minmax(0,1.4fr)_150px_90px]">
      <span className="bg-superficie-2 text-texto-apoio rounded-botao flex size-20 items-center justify-center">
        <Icone nome="contas" />
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-enfase font-semibold">{nome}</span>
        <span className="text-pequeno text-texto-2">{tipoDoItem(item)}</span>
      </span>
      <span className="text-apoio text-texto-apoio col-span-2 col-start-2 row-start-2 leading-[1.45] md:col-span-1 md:col-start-auto md:row-start-auto">
        {detalheDoItem(item)}
      </span>
      <span className="col-start-3 row-start-1 justify-self-end md:col-start-auto md:row-start-auto md:justify-self-start">
        <Selo tom={selo.tom}>{selo.rotulo}</Selo>
      </span>
      <Button
        variant="filter"
        onClick={() => onEditar(item)}
        aria-label={`Editar ${nome}`}
        className="col-start-3 row-start-3 justify-self-end font-semibold md:col-start-auto md:row-start-auto"
      >
        Editar
      </Button>
    </li>
  );
}

function NovaConta({ aberta, onFechar }: { aberta: boolean; onFechar: () => void }) {
  return (
    <Dialogo aberto={aberta} onFechar={onFechar} titulo="Conta manual">
      <FormularioConta onFechar={onFechar} />
    </Dialogo>
  );
}

function FormularioConta({ onFechar }: { onFechar: () => void }) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<TipoConta>("corrente");
  const [titular, setTitular] = useState("");
  const { data: pessoas = [] } = usePessoas();
  const criar = useCriarConta();

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        criar.mutate(
          { nome: nome.trim(), tipo, titular_id: titular ? Number(titular) : null },
          { onSuccess: onFechar },
        );
      }}
    >
      <p className="text-apoio text-texto-2 m-0">
        Para uma conta que o banco não sincroniza: os lançamentos dela entram à mão ou por PDF.
      </p>
      <Campo rotulo="Nome">
        <Input value={nome} onChange={(e) => setNome(e.target.value)} required className="w-full" />
      </Campo>
      <Campo rotulo="Tipo">
        <Select value={tipo} onChange={(e) => setTipo(e.target.value as TipoConta)} className="w-full">
          {(Object.keys(ROTULO_TIPO_CONTA) as TipoConta[]).map((t) => (
            <option key={t} value={t}>
              {ROTULO_TIPO_CONTA[t]}
            </option>
          ))}
        </Select>
      </Campo>
      <Campo rotulo="Titular">
        <Select value={titular} onChange={(e) => setTitular(e.target.value)} className="w-full">
          <option value="">Conjunta</option>
          {pessoas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </Select>
      </Campo>
      {criar.error ? <ErroDoFormulario erro={criar.error} /> : null}
      <div className="flex justify-end gap-4">
        <Button variant="secondary" onClick={onFechar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!nome.trim() || criar.isPending}>
          {criar.isPending ? "Salvando..." : "Adicionar"}
        </Button>
      </div>
    </form>
  );
}

function Renomear({ item, onFechar }: { item: ItemContaCartao | null; onFechar: () => void }) {
  return (
    <Dialogo
      aberto={item !== null}
      onFechar={onFechar}
      titulo={item?.tipo === "cartao" ? "Editar cartão" : "Editar conta"}
    >
      {item ? <FormularioNome key={`${item.tipo}-${item.forma_pagamento_id ?? item.conta_id}`} item={item} onFechar={onFechar} /> : null}
    </Dialogo>
  );
}

function FormularioNome({ item, onFechar }: { item: ItemContaCartao; onFechar: () => void }) {
  const [nome, setNome] = useState(item.nome);
  const renomear = useRenomear();
  const cartao = item.tipo === "cartao";
  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        renomear.mutate(
          {
            tipo: item.tipo,
            id: cartao ? (item.forma_pagamento_id ?? 0) : item.conta_id,
            nome: nome.trim(),
          },
          { onSuccess: onFechar },
        );
      }}
    >
      <Campo rotulo={cartao ? "Nome do cartão" : "Nome da conta"}>
        <Input value={nome} onChange={(e) => setNome(e.target.value)} required className="w-full" />
      </Campo>
      {cartao ? (
        <p className="text-pequeno text-texto-2 m-0">
          Mantenha os 4 últimos dígitos no fim: é por eles que a importação acha o cartão.
        </p>
      ) : null}
      {renomear.error ? <ErroDoFormulario erro={renomear.error} /> : null}
      <div className="flex justify-end gap-4">
        <Button variant="secondary" onClick={onFechar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={!nome.trim() || renomear.isPending}>
          {renomear.isPending ? "Salvando..." : "Salvar"}
        </Button>
      </div>
    </form>
  );
}
