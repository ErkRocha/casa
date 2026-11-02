import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Icone } from "@/components/ui/icone";
import { ApiError } from "@/lib/api";
import { useAdiado } from "@/lib/use-adiado";
import { cn } from "@/lib/utils";
import { novoIdCliente } from "./id-cliente";
import { useAdicionarItem, useAtualizarItem, useBuscaProdutos, useDespensa } from "./queries";
import { numeroCurto, quantidadeDoItem } from "./textos";
import type { Item, Produto } from "./types";

type Escolha = { tipo: "produto"; produto: Produto } | { tipo: "novo"; nome: string };

/**
 * Adicionar item (`ComprasAdicionarCelular`, D-25): painel que sobe de baixo
 * no celular e fica no centro no computador.
 *
 * Busca enquanto digita. Produto que já está na lista aparece como "Já na
 * lista" e o botão vira "Atualizar ... na lista": a lista tem um pendente por
 * produto. Dá para criar o produto na hora, com o que foi digitado.
 */
export function AdicionarPainel({
  aberto,
  onFechar,
  quem,
  pendentes,
  onAviso,
}: {
  aberto: boolean;
  onFechar: () => void;
  quem: string;
  /** Os pendentes da lista, por produto: "Já na lista" e o que atualizar. */
  pendentes: Map<number, Item>;
  onAviso: (texto: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();

  useEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    if (aberto && !dialogo.open) dialogo.showModal();
    if (!aberto && dialogo.open) dialogo.close();
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={idTitulo}
      onClose={onFechar}
      onClick={(evento) => {
        if (evento.target === ref.current) onFechar();
      }}
      className={cn(
        "bg-superficie text-texto m-0 max-h-[92vh] max-w-none border-none p-0",
        "backdrop:bg-[rgba(23,32,51,0.45)] shadow-[0_-8px_30px_rgba(23,32,51,0.2)]",
        // Celular: encostado embaixo, cantos de cima arredondados.
        "fixed inset-x-0 top-auto bottom-0 w-full rounded-t-[24px]",
        // Computador: no centro, como os outros diálogos.
        "md:rounded-bloco md:top-1/2 md:bottom-auto md:left-1/2 md:w-[440px] md:-translate-x-1/2 md:-translate-y-1/2",
      )}
    >
      {aberto ? (
        <Conteudo
          idTitulo={idTitulo}
          onFechar={onFechar}
          quem={quem}
          pendentes={pendentes}
          onAviso={onAviso}
        />
      ) : null}
    </dialog>
  );
}

function Conteudo({
  idTitulo,
  onFechar,
  quem,
  pendentes,
  onAviso,
}: {
  idTitulo: string;
  onFechar: () => void;
  quem: string;
  pendentes: Map<number, Item>;
  onAviso: (texto: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const [escolha, setEscolha] = useState<Escolha | null>(null);
  const [quantidade, setQuantidade] = useState(1);
  const [observacao, setObservacao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  // Um por abertura do painel: reenviar depois de uma falha de rede não
  // cria um segundo item (D-25, id_cliente).
  const [idCliente] = useState(novoIdCliente);

  const busca = useAdiado(texto, 200);
  const resultados = useBuscaProdutos(busca);
  const temEmCasa = useDespensa("tem");
  const emCasa = useMemo(
    () => new Set((temEmCasa.data ?? []).map((d) => d.produto_id)),
    [temEmCasa.data],
  );
  const adicionar = useAdicionarItem(quem);
  const atualizar = useAtualizarItem(quem);

  const lista = texto.trim() ? (resultados.data ?? []) : [];
  // Sem escolha explícita, vale o primeiro resultado (o desenho o destaca).
  // Sem nenhum resultado, vale criar o produto com o que foi digitado.
  const efetiva: Escolha | null =
    escolha ??
    (lista[0]
      ? { tipo: "produto", produto: lista[0] }
      : texto.trim() && busca === texto && !resultados.isFetching
        ? { tipo: "novo", nome: texto.trim() }
        : null);
  const pendente = efetiva?.tipo === "produto" ? pendentes.get(efetiva.produto.id) : undefined;
  const nomeEscolhido =
    efetiva?.tipo === "produto" ? efetiva.produto.nome : efetiva?.nome ?? "";
  const ocupado = adicionar.isPending || atualizar.isPending;

  function escolherProduto(produto: Produto) {
    setEscolha({ tipo: "produto", produto });
    const ja = pendentes.get(produto.id);
    const atual = ja?.quantidade ? Math.max(1, Math.round(Number(ja.quantidade))) : 1;
    setQuantidade(atual);
  }

  function aoFalhar(e: unknown) {
    setErro(e instanceof ApiError ? e.detail : "Não foi possível salvar. Tente de novo.");
  }

  function confirmar() {
    if (!efetiva) return;
    setErro(null);
    const obs = observacao.trim() || undefined;
    if (pendente) {
      atualizar.mutate(
        {
          id: pendente.id,
          quantidade: String(quantidade),
          ...(obs ? { observacao: obs } : {}),
        },
        {
          onSuccess: (item) => {
            onAviso(`${item.produto_nome} atualizado na lista.`);
            onFechar();
          },
          onError: aoFalhar,
        },
      );
      return;
    }
    adicionar.mutate(
      {
        id_cliente: idCliente,
        ...(efetiva.tipo === "produto"
          ? { produto_id: efetiva.produto.id }
          : { produto_nome: efetiva.nome }),
        quantidade: String(quantidade),
        observacao: obs ?? null,
      },
      {
        onSuccess: (item) => {
          onAviso(
            item.ja_estava
              ? `${item.produto_nome} já estava na lista (${item.adicionado_por} adicionou).`
              : `${item.produto_nome} entrou na lista.`,
          );
          onFechar();
        },
        onError: aoFalhar,
      },
    );
  }

  return (
    <form
      className="flex flex-col gap-7 px-8 pt-5 pb-[max(28px,env(safe-area-inset-bottom))]"
      onSubmit={(evento) => {
        evento.preventDefault();
        confirmar();
      }}
    >
      <div aria-hidden className="bg-contorno h-2.5 w-20 self-center rounded-[3px] md:hidden" />
      <div className="flex items-center justify-between">
        <h2 id={idTitulo} className="m-0 text-[19px] font-bold">
          Adicionar à lista
        </h2>
        <button
          type="button"
          aria-label="Fechar"
          onClick={onFechar}
          className="bg-superficie-2 text-texto rounded-interno flex size-22 cursor-pointer items-center justify-center border-none"
        >
          <Icone nome="fechar" tamanho={16} />
        </button>
      </div>

      <label className="bg-superficie-2 rounded-sub flex h-26 items-center gap-4 px-7 shadow-[inset_0_0_0_2px_var(--color-destaque)]">
        <span className="sr-only">Produto</span>
        <input
          autoFocus
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            setEscolha(null);
          }}
          placeholder="Leite, pão, detergente…"
          className="text-texto placeholder:text-texto-2 flex-1 border-none bg-transparent text-[17px] outline-none"
          autoComplete="off"
          enterKeyHint="done"
        />
      </label>

      {texto.trim() ? (
        <div role="listbox" aria-label="Produtos" className="flex flex-col">
          {lista.map((produto) => {
            const marcado = efetiva?.tipo === "produto" && efetiva.produto.id === produto.id;
            const ja = pendentes.get(produto.id);
            const nota = ja
              ? `Já na lista${quantidadeDoItem(ja) ? `: ${quantidadeDoItem(ja)}` : ""}`
              : emCasa.has(produto.id)
                ? "Tem em casa"
                : "";
            return (
              <button
                key={produto.id}
                type="button"
                role="option"
                aria-selected={marcado}
                onClick={() => escolherProduto(produto)}
                className={cn(
                  "text-texto rounded-interno flex min-h-26 cursor-pointer items-center justify-between gap-4 border-none px-6 text-left",
                  marcado ? "bg-destaque-fundo" : "bg-transparent",
                )}
              >
                <span className="flex flex-col gap-1">
                  <span className="text-enfase font-semibold">{produto.nome}</span>
                  <span className="text-pequeno text-texto-2">{produto.secao_nome}</span>
                </span>
                <span className="text-pequeno text-texto-2 shrink-0">{nota}</span>
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={efetiva?.tipo === "novo"}
            onClick={() => {
              setEscolha({ tipo: "novo", nome: texto.trim() });
              setQuantidade(1);
            }}
            className={cn(
              "text-destaque rounded-interno flex min-h-24 cursor-pointer items-center gap-4 border-none px-6 text-[15px] font-semibold",
              efetiva?.tipo === "novo" ? "bg-destaque-fundo" : "bg-transparent",
            )}
          >
            <Icone nome="adicionar" tamanho={16} />
            Criar "{texto.trim()}" como produto novo
          </button>
        </div>
      ) : null}

      <div className="flex items-center gap-6">
        <span id={`${idTitulo}-qtd`} className="flex-1 text-[15px] font-semibold">
          Quantidade
        </span>
        <div
          role="group"
          aria-labelledby={`${idTitulo}-qtd`}
          className="bg-superficie-2 rounded-interno flex items-center gap-2 p-2"
        >
          <button
            type="button"
            aria-label="Diminuir"
            disabled={quantidade <= 1}
            onClick={() => setQuantidade((q) => Math.max(1, q - 1))}
            className="bg-superficie text-texto flex size-22 cursor-pointer items-center justify-center rounded-[10px] border-none text-[20px] disabled:opacity-40"
          >
            −
          </button>
          <span aria-live="polite" className="min-w-24 text-center text-[18px] font-bold">
            {numeroCurto(String(quantidade))}
          </span>
          <button
            type="button"
            aria-label="Aumentar"
            onClick={() => setQuantidade((q) => Math.min(999, q + 1))}
            className="bg-superficie text-texto flex size-22 cursor-pointer items-center justify-center rounded-[10px] border-none text-[20px]"
          >
            +
          </button>
        </div>
      </div>

      <label className="flex flex-col gap-3">
        <span className="text-[15px] font-semibold">
          Observação <span className="text-texto-2 font-normal">(opcional)</span>
        </span>
        <input
          value={observacao}
          maxLength={300}
          onChange={(e) => setObservacao(e.target.value)}
          placeholder="Ex.: da marca que a gente gosta"
          className="bg-superficie-2 rounded-interno text-texto placeholder:text-texto-2 h-24 border-none px-7 text-[16px] outline-none"
        />
      </label>

      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={!efetiva || ocupado}
        className="bg-destaque hover:bg-destaque-hover rounded-sub h-27 cursor-pointer border-none text-[17px] font-[650] text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {!efetiva
          ? "Escolha ou digite um produto"
          : ocupado
            ? "Salvando…"
            : pendente
              ? `Atualizar ${nomeEscolhido.toLowerCase()} na lista`
              : `Adicionar ${nomeEscolhido.toLowerCase()}`}
      </button>
    </form>
  );
}
