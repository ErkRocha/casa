import { useMemo, useState } from "react";

import { Segmentado } from "@/components/ui/segmentado";
import { Carregando, Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { ApiError } from "@/lib/api";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { useDefinirDespensa, useDespensa, useLista, useProdutos, useSecoes } from "./queries";
import { haQuantoTempo, porSecao } from "./textos";
import type { EstadoDespensa, LinhaDespensa } from "./types";

type Filtro = "todos" | "acabando" | "acabou";

const ESTADOS: Array<{ id: EstadoDespensa; rotulo: string; marcado: string }> = [
  { id: "tem", rotulo: "Tem", marcado: "bg-receita-fundo text-receita-texto" },
  { id: "acabando", rotulo: "Acabando", marcado: "bg-atencao-fundo text-atencao-texto" },
  { id: "acabou", rotulo: "Acabou", marcado: "bg-perigo-fundo text-perigo" },
];

interface Linha {
  produto_id: number;
  produto_nome: string;
  secao_id: number;
  secao_nome: string;
  despensa: LinhaDespensa | null;
}

/**
 * Despensa (`ComprasDespensaCelular`, D-25): três estados por produto.
 * "Acabou" põe na lista na hora; "Acabando" só sugere.
 *
 * Em "Tudo" aparecem todos os produtos: o que ainda não é acompanhado fica
 * sem estado, e tocar num estado passa a acompanhá-lo.
 */
export function Despensa({ quem, lateral = false }: { quem: string | null; lateral?: boolean }) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const todos = useDespensa(null);
  const acabando = useDespensa("acabando");
  const acabou = useDespensa("acabou");
  const produtos = useProdutos();
  const secoes = useSecoes();
  const lista = useLista();
  const definir = useDefinirDespensa(quem ?? "");
  const [aviso, setAviso] = useState<string | null>(null);
  const [mudando, setMudando] = useState<number | null>(null);

  const pendentes = useMemo(
    () =>
      new Set(
        (lista.data?.itens ?? []).filter((i) => i.situacao === "pendente").map((i) => i.produto_id),
      ),
    [lista.data],
  );

  const linhas: Linha[] = useMemo(() => {
    if (filtro !== "todos") {
      const fonte = (filtro === "acabando" ? acabando.data : acabou.data) ?? [];
      return fonte.map((d) => ({ ...d, despensa: d }));
    }
    const porProduto = new Map((todos.data ?? []).map((d) => [d.produto_id, d]));
    const ordem = new Map((secoes.data ?? []).map((s) => [s.id, s.ordem]));
    // A API devolve os produtos por relevância; aqui é o percurso das seções.
    return [...(produtos.data ?? [])]
      .sort(
        (a, b) =>
          (ordem.get(a.secao_id) ?? 0) - (ordem.get(b.secao_id) ?? 0) ||
          a.nome.localeCompare(b.nome, "pt-BR"),
      )
      .map((p) => ({
        produto_id: p.id,
        produto_nome: p.nome,
        secao_id: p.secao_id,
        secao_nome: p.secao_nome,
        despensa: porProduto.get(p.id) ?? null,
      }));
  }, [filtro, todos.data, acabando.data, acabou.data, produtos.data, secoes.data]);

  const carregando = todos.isLoading || produtos.isLoading || secoes.isLoading;
  const falhou = todos.isError || produtos.isError;

  function notaDe(linha: Linha): string {
    const d = linha.despensa;
    if (!d) return "";
    const naLista = pendentes.has(linha.produto_id);
    if (d.estado === "acabou") return naLista ? "na lista" : "acabou";
    if (d.estado === "acabando") return naLista ? "na lista" : "sugerido na lista";
    return `atualizado ${haQuantoTempo(d.estado_em)}`;
  }

  function mudar(linha: Linha, estado: EstadoDespensa) {
    if (!quem || linha.despensa?.estado === estado) return;
    setAviso(null);
    setMudando(linha.produto_id);
    definir.mutate(
      { produtoId: linha.produto_id, estado },
      {
        onSuccess: (r) => {
          if (r.item_criado) setAviso(`${linha.produto_nome} entrou na lista.`);
        },
        onError: (e) =>
          setAviso(e instanceof ApiError ? e.detail : "Não foi possível mudar. Tente de novo."),
        onSettled: () => setMudando(null),
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {lateral ? (
        <h2 className="text-bloco font-forte m-0 px-1">Despensa</h2>
      ) : (
        <header className="flex items-center gap-4 px-1">
          <a
            href={href("compras")}
            aria-label="Voltar para a lista"
            className="bg-superficie text-texto rounded-interno flex size-22 items-center justify-center"
          >
            <Icone nome="esquerda" />
          </a>
          <div className="flex flex-col gap-1">
            <h1 className="m-0 text-[22px] font-bold tracking-[-0.3px]">Despensa</h1>
            <span className="text-apoio text-texto-2">O que tem em casa</span>
          </div>
        </header>
      )}

      <p className="text-apoio text-texto-2 m-0 px-1 leading-normal">
        Toque no estado de cada produto. "Acabou" coloca na lista na hora; "Acabando" só sugere.
      </p>

      <Segmentado<Filtro>
        rotulo="Filtrar"
        cheio
        atual={filtro}
        onMudar={setFiltro}
        opcoes={[
          { id: "todos", rotulo: `Tudo (${produtos.data?.length ?? 0})` },
          { id: "acabando", rotulo: `Acabando (${acabando.data?.length ?? 0})` },
          { id: "acabou", rotulo: `Acabou (${acabou.data?.length ?? 0})` },
        ]}
      />

      <p role="status" className="text-apoio text-texto-2 m-0 px-1 empty:hidden">
        {aviso}
      </p>

      {carregando ? (
        <Carregando rotulo="Carregando a despensa" alturas={["h-80", "h-60"]} />
      ) : falhou ? (
        <Falha
          titulo="Não foi possível ler a despensa"
          erro={todos.error ?? produtos.error}
          onTentar={() => {
            void todos.refetch();
            void produtos.refetch();
          }}
        />
      ) : linhas.length === 0 ? (
        <p className="bg-superficie rounded-bloco text-apoio text-texto-2 m-0 px-7 py-9">
          {filtro === "todos" ? "Nenhum produto cadastrado ainda." : "Nada aqui agora."}
        </p>
      ) : (
        porSecao(linhas).map((grupo) => (
          <section
            key={grupo.id}
            aria-label={grupo.nome}
            className="bg-superficie rounded-bloco flex flex-col px-7 pt-3 pb-5"
          >
            <h3 className="text-apoio font-forte text-texto-2 m-0 px-1 pt-6 pb-3">{grupo.nome}</h3>
            {grupo.linhas.map((linha) => (
              <div key={linha.produto_id} className="linha-acima flex flex-col gap-4 px-1 py-5">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="text-enfase font-semibold">{linha.produto_nome}</span>
                  <span className="text-selo text-texto-2">{notaDe(linha)}</span>
                </div>
                <div
                  role="radiogroup"
                  aria-label={`Estado de ${linha.produto_nome}`}
                  className="grid grid-cols-3 gap-3"
                >
                  {ESTADOS.map((e) => {
                    const atual = linha.despensa?.estado === e.id;
                    return (
                      <button
                        key={e.id}
                        type="button"
                        role="radio"
                        aria-checked={atual}
                        disabled={!quem || mudando === linha.produto_id}
                        onClick={() => mudar(linha, e.id)}
                        className={cn(
                          "text-apoio h-20 cursor-pointer rounded-[10px] border-none font-semibold",
                          "disabled:cursor-wait",
                          atual ? e.marcado : "bg-superficie-2 text-texto-apoio",
                        )}
                      >
                        {e.rotulo}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </section>
        ))
      )}
    </div>
  );
}
