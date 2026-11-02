import { useState, type ReactNode } from "react";

import { Carregando, Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { ApiError } from "@/lib/api";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { AdicionarPainel } from "./adicionar-painel";
import { Despensa } from "./despensa";
import {
  useAdicionarItem,
  useLista,
  useMarcarComprado,
  useSincronizacaoCompras,
  type EstadoConexao,
} from "./queries";
import { useQuemGuardado } from "./quem";
import { QuemDialogo } from "./quem-dialogo";
import {
  detalheDoComprado,
  detalheDoPendente,
  porSecao,
  quantidadeDoItem,
} from "./textos";
import type { Item } from "./types";

/**
 * Lista de compras (`ComprasListaCelular`, D-25). No computador, a mesma
 * tela com largura de leitura, e a despensa ao lado quando cabe.
 */
export function ComprasPage() {
  return (
    <ComTela>
      {(quem, perguntar, conexao) => (
        <div className="mx-auto flex w-full max-w-[1120px] gap-12">
          <div className="mx-auto w-full max-w-[640px] min-w-0 xl:mx-0">
            <ListaDeCompras quem={quem} conexao={conexao} onTrocarQuem={perguntar} />
          </div>
          <aside aria-label="Despensa" className="hidden min-w-0 flex-1 xl:block">
            <Despensa quem={quem} lateral />
          </aside>
        </div>
      )}
    </ComTela>
  );
}

/** A despensa sozinha (celular, e computador estreito). */
export function DespensaPage() {
  return (
    <ComTela>
      {(quem) => (
        <div className="mx-auto w-full max-w-[640px]">
          <Despensa quem={quem} />
        </div>
      )}
    </ComTela>
  );
}

/**
 * O que as telas de compras dividem: o polling enquanto estão abertas e o
 * "quem é você?", perguntado uma vez por aparelho.
 */
function ComTela({
  children,
}: {
  children: (quem: string | null, perguntar: () => void, conexao: EstadoConexao) => ReactNode;
}) {
  const quem = useQuemGuardado();
  const [perguntando, setPerguntando] = useState(false);
  // Um polling só, enquanto uma tela de compras está aberta.
  const conexao = useSincronizacaoCompras();
  return (
    <>
      {children(quem, () => setPerguntando(true), conexao)}
      <QuemDialogo aberto={quem === null || perguntando} onFechar={() => setPerguntando(false)} />
    </>
  );
}

function ListaDeCompras({
  quem,
  conexao,
  onTrocarQuem,
}: {
  quem: string | null;
  conexao: EstadoConexao;
  onTrocarQuem: () => void;
}) {
  const lista = useLista();
  const marcar = useMarcarComprado(quem ?? "");
  const sugerir = useAdicionarItem(quem ?? "");
  const [adicionando, setAdicionando] = useState(false);
  const [carrinhoAberto, setCarrinhoAberto] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);

  const itens = lista.data?.itens ?? [];
  const pendentes = itens.filter((i) => i.situacao === "pendente");
  const carrinho = itens
    .filter((i) => i.situacao === "comprado")
    .sort((a, b) => (b.comprado_em ?? "").localeCompare(a.comprado_em ?? ""));
  const porProduto = new Map(pendentes.map((i) => [i.produto_id, i]));

  function alternar(item: Item) {
    if (!quem) return;
    setAviso(null);
    const comprado = item.situacao === "pendente";
    marcar.mutate(
      { item, comprado },
      {
        onError: (e) =>
          setAviso(
            `${item.produto_nome} voltou ao que era: ${
              e instanceof ApiError ? e.detail : "não foi possível falar com o servidor."
            }`,
          ),
      },
    );
  }

  if (lista.isLoading) {
    return <Carregando rotulo="Carregando a lista" alturas={["h-26", "h-80", "h-120"]} />;
  }
  if (lista.isError || !lista.data) {
    return (
      <Falha
        titulo="Não foi possível ler a lista"
        erro={lista.error}
        onTentar={() => void lista.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-5 px-1">
        <div className="flex flex-col gap-1">
          <h1 className="text-pagina-celular md:text-pagina m-0 font-bold tracking-[-0.4px]">
            Lista de compras
          </h1>
          <span className="text-apoio text-texto-2">
            {pendentes.length} para pegar, {carrinho.length} no carrinho
          </span>
        </div>
        <a
          href={href("despensa")}
          className="bg-superficie text-texto hover:text-texto rounded-interno text-apoio flex h-20 items-center gap-3 px-6 font-semibold no-underline xl:hidden"
        >
          <Icone nome="despensa" tamanho={16} />
          Despensa
        </a>
      </header>

      <button
        type="button"
        disabled={!quem}
        onClick={() => setAdicionando(true)}
        className="bg-superficie text-texto-2 rounded-cartao flex h-26 cursor-pointer items-center gap-5 border-none px-8 text-left text-[16px] shadow-[0_1px_2px_rgba(23,32,51,0.06)]"
      >
        <span className="text-destaque flex">
          <Icone nome="adicionar" tamanho={20} espessura={2.4} />
        </span>
        Adicionar item
      </button>

      <p role="status" className="text-apoio text-texto-2 m-0 px-1 empty:hidden">
        {aviso}
      </p>

      {lista.data.sugestoes.length > 0 ? (
        <section className="bg-atencao-fundo-2 rounded-cartao flex flex-col gap-5 px-7 py-6">
          <h2 className="text-apoio font-forte text-atencao-texto m-0">Acabando em casa</h2>
          <div className="flex flex-wrap gap-4">
            {lista.data.sugestoes.map((s) => (
              <button
                key={s.produto_id}
                type="button"
                disabled={!quem || sugerir.isPending}
                aria-label={`Pôr ${s.produto_nome} na lista`}
                onClick={() =>
                  sugerir.mutate(
                    { produto_id: s.produto_id },
                    {
                      onSuccess: (i) => setAviso(`${i.produto_nome} entrou na lista.`),
                      onError: (e) =>
                        setAviso(e instanceof ApiError ? e.detail : "Não foi possível adicionar."),
                    },
                  )
                }
                className="bg-superficie text-texto text-apoio flex h-18 cursor-pointer items-center gap-3 rounded-full border-none pr-6 pl-5 shadow-[inset_0_0_0_1px_var(--color-atencao-borda-2)]"
              >
                <Icone nome="adicionar" tamanho={14} espessura={2.4} />
                {s.produto_nome}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {pendentes.length === 0 ? (
        <p className="bg-superficie rounded-bloco text-apoio text-texto-2 m-0 px-7 py-9 text-center">
          Nada para pegar. Toque em "Adicionar item" para começar a lista.
        </p>
      ) : (
        porSecao(pendentes).map((grupo) => (
          <section
            key={grupo.id}
            aria-label={grupo.nome}
            className="bg-superficie rounded-bloco flex flex-col px-7 py-3"
          >
            <h2 className="text-apoio font-forte text-texto-2 m-0 px-1 pt-6 pb-3">{grupo.nome}</h2>
            {grupo.linhas.map((item) => (
              <LinhaItem key={item.id} item={item} desabilitado={!quem} onAlternar={alternar} />
            ))}
          </section>
        ))
      )}

      {carrinho.length > 0 ? (
        <section className="bg-superficie rounded-bloco flex flex-col px-7 py-3">
          <div className="flex items-center justify-between px-1 pt-6 pb-3">
            <h2 className="text-apoio font-forte text-texto-2 m-0">No carrinho ({carrinho.length})</h2>
            <button
              type="button"
              aria-expanded={carrinhoAberto}
              onClick={() => setCarrinhoAberto((v) => !v)}
              className="text-destaque text-apoio h-16 cursor-pointer border-none bg-transparent font-semibold"
            >
              {carrinhoAberto ? "Esconder" : "Mostrar"}
            </button>
          </div>
          {carrinhoAberto
            ? carrinho.map((item) => (
                <LinhaItem key={item.id} item={item} desabilitado={!quem} onAlternar={alternar} />
              ))
            : null}
        </section>
      ) : null}

      <p className="text-pequeno text-texto-2 m-0 text-center leading-normal">
        {conexao === "ok"
          ? "Sincronizado agora. Tudo que um marca aparece pro outro em segundos."
          : "Sem conexão com o servidor. Tentando de novo…"}
        {quem ? (
          <>
            {" "}
            Você é {quem}.{" "}
            <button
              type="button"
              onClick={onTrocarQuem}
              className="text-destaque cursor-pointer border-none bg-transparent p-0 font-semibold"
            >
              Trocar
            </button>
          </>
        ) : null}
      </p>

      {quem ? (
        <AdicionarPainel
          aberto={adicionando}
          onFechar={() => setAdicionando(false)}
          quem={quem}
          pendentes={porProduto}
          onAviso={setAviso}
        />
      ) : null}
    </div>
  );
}

/** Uma linha da lista: caixa de 28px com alvo de toque de 56px. */
function LinhaItem({
  item,
  desabilitado,
  onAlternar,
}: {
  item: Item;
  desabilitado: boolean;
  onAlternar: (item: Item) => void;
}) {
  const comprado = item.situacao === "comprado";
  const quantidade = quantidadeDoItem(item);
  return (
    <label
      className={cn(
        "linha-acima flex cursor-pointer items-center gap-7 px-1 py-3",
        comprado ? "min-h-26" : "min-h-28",
        desabilitado && "cursor-not-allowed",
      )}
    >
      <input
        type="checkbox"
        className="peer sr-only"
        checked={comprado}
        disabled={desabilitado}
        onChange={() => onAlternar(item)}
      />
      <span
        aria-hidden
        className={cn(
          "rounded-campo flex size-14 shrink-0 items-center justify-center",
          "peer-focus-visible:outline-destaque peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2",
          comprado
            ? "bg-receita text-white"
            : "bg-superficie shadow-[inset_0_0_0_2px_var(--color-caixa)]",
        )}
      >
        {comprado ? <Icone nome="revisar" tamanho={16} espessura={3} /> : null}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span
          className={cn(
            comprado
              ? "text-texto-inativo text-enfase line-through"
              : "text-[17px] font-[550]",
          )}
        >
          {item.produto_nome}
        </span>
        <span className={cn("text-pequeno", comprado ? "text-texto-inativo" : "text-texto-2")}>
          {comprado ? detalheDoComprado(item) : detalheDoPendente(item)}
        </span>
      </span>
      {!comprado && quantidade ? (
        <span className="text-texto-apoio text-[15px] font-[650]">{quantidade}</span>
      ) : null}
    </label>
  );
}
