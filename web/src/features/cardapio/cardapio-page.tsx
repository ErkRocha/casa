import { useState } from "react";

import { Carregando, Falha } from "@/components/ui/estados";
import { CabecalhoCompras } from "@/features/compras/abas-compras";
import { ComTela } from "@/features/compras/compras-page";
import { useLista } from "@/features/compras/queries";
import { mudarParams, useParamsDaRota } from "@/lib/rotas";
import { AvisosRoteiro } from "./avisos-roteiro";
import { CopiarSemana } from "./copiar-semana";
import { diasDaSemana, hojeSP, segundaDe, semanaEncerrada, somarDias } from "./datas";
import { EditarRefeicao, type AlvoDaRefeicao } from "./editar-refeicao";
import { usePessoasDoCardapio, useRoteiro, useSemana } from "./queries";
import { ReceitaPainel } from "./receita-painel";
import { ReceitasPainel } from "./receitas-painel";
import { SemanaCelular } from "./semana-celular";
import { SemanaVazia } from "./semana-vazia";
import { SeletorSemana } from "./seletor-semana";
import { preparoPorRefeicao } from "./textos";
import type { SemanaCopiada } from "./types";
import type { VistaDaSemana } from "./vista";

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Aba Cardápio de Compras (D-30). O que vale um link mora no endereço:
 * `#cardapio?semana=2026-11-16&dia=2026-11-17`.
 */
export function CardapioPage() {
  return <ComTela>{(quem) => <Cardapio quem={quem} />}</ComTela>;
}

function Cardapio({ quem }: { quem: string | null }) {
  // Quem mantém o cursor do polling de /mudancas é a lista: a aba Cardápio
  // a mantém carregada para o "feito" do roteiro chegar mesmo sem a Lista aberta.
  useLista();

  const params = useParamsDaRota();
  const hoje = hojeSP();
  const semanaAtual = segundaDe(hoje);
  const pedida = params.get("semana");
  const inicio = pedida && ISO.test(pedida) ? segundaDe(pedida) : semanaAtual;

  const semana = useSemana(inicio);
  const pessoas = usePessoasDoCardapio();
  const roteiro = useRoteiro(semana.data?.id);
  const [editando, setEditando] = useState<AlvoDaRefeicao | null>(null);
  const [copiando, setCopiando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const irParaSemana = (destino: string) =>
    mudarParams(
      { semana: destino === semanaAtual ? null : destino, dia: null },
      { substituir: true },
    );

  const aoCopiar = (nova: SemanaCopiada | null) => {
    setAviso(
      nova
        ? ["Semana copiada.", ...nova.avisos.map((a) => a.texto)].join(" ")
        : "Semana criada.",
    );
    if (nova) irParaSemana(nova.inicio);
  };

  const dados = semana.data;
  const dias = diasDaSemana(inicio);
  const pedido = params.get("dia");
  const dia =
    pedido && dias.includes(pedido) ? pedido : dias.includes(hoje) ? hoje : (dias[0] ?? inicio);

  const v: VistaDaSemana | null =
    dados && pessoas.data
      ? {
          semana: dados,
          hoje,
          encerrada: semanaEncerrada(inicio, hoje),
          pessoas: pessoas.data,
          quem,
          roteiro: roteiro.data,
          preparo: preparoPorRefeicao(roteiro.data),
          onEditar: setEditando,
          onAbrirReceita: (id) => mudarParams({ receita: String(id) }),
          onCopiar: () => setCopiando(true),
        }
      : null;

  const usos = (id: number) =>
    dados
      ? dados.dias.reduce((n, d) => n + d.refeicoes.filter((r) => r.receita?.id === id).length, 0)
      : null;

  const pratos = dados ? dados.dias.reduce((n, d) => n + d.refeicoes.length, 0) : 0;
  const nomes = (pessoas.data ?? []).map((p) => p.nome).join(" e ");

  return (
    <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-6">
      <CabecalhoCompras atual="cardapio" />
      <SeletorSemana
        inicio={inicio}
        naSemanaAtual={inicio === semanaAtual}
        resumo={dados ? `${pratos} pratos${nomes ? ` · ${nomes}` : ""}` : "sem cardápio"}
        onIr={(n) => irParaSemana(somarDias(inicio, 7 * n))}
        onHoje={() => irParaSemana(semanaAtual)}
      />

      <p role="status" className="text-apoio text-texto-2 m-0 px-1 empty:hidden">
        {aviso}
      </p>

      {semana.isLoading || (dados && pessoas.isLoading) ? (
        <Carregando rotulo="Carregando o cardápio" alturas={["h-28", "h-60", "h-60"]} />
      ) : semana.isError || pessoas.isError ? (
        <Falha
          titulo="Não foi possível ler o cardápio"
          erro={semana.error ?? pessoas.error}
          onTentar={() => {
            void semana.refetch();
            void pessoas.refetch();
          }}
        />
      ) : !dados ? (
        <SemanaVazia inicio={inicio} quem={quem} onCriada={aoCopiar} />
      ) : v ? (
        <>
          <AvisosRoteiro avisos={roteiro.data?.avisos ?? []} />
          <SemanaCelular
            v={v}
            dia={dia}
            onEscolherDia={(d) => mudarParams({ dia: d }, { substituir: true })}
          >
            <section className="bg-superficie rounded-bloco flex flex-col gap-4 p-8">
              <h2 className="text-bloco-celular font-forte m-0">A semana inteira</h2>
              <button
                type="button"
                disabled={!quem}
                onClick={v.onCopiar}
                className="text-destaque text-apoio min-h-22 cursor-pointer rounded-interno border-none bg-transparent font-semibold disabled:cursor-not-allowed disabled:opacity-50"
              >
                Copiar esta semana para a próxima
              </button>
              <button
                type="button"
                onClick={() => mudarParams({ receitas: "1" })}
                className="text-destaque text-apoio min-h-22 cursor-pointer rounded-interno border-none bg-transparent font-semibold"
              >
                Receitas
              </button>
            </section>
          </SemanaCelular>
          <EditarRefeicao
            alvo={editando}
            onFechar={() => setEditando(null)}
            semana={v.semana}
            pessoas={v.pessoas}
            quem={quem}
            preparo={v.preparo}
            onAbrirReceita={v.onAbrirReceita}
          />
          <CopiarSemana
            aberto={copiando}
            onFechar={() => setCopiando(false)}
            semana={v.semana}
            quem={quem}
            onCopiada={aoCopiar}
          />
        </>
      ) : null}

      <ReceitasPainel aberto={params.get("receitas") !== null} quem={quem} />
      <ReceitaPainel
        receita={params.get("receita")}
        editar={params.get("editar") === "1"}
        quem={quem}
        usos={usos}
      />
    </div>
  );
}
