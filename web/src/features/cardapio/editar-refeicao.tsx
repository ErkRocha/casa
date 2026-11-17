import { useState } from "react";

import { Button } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { BuscaReceitas } from "./busca-receitas";
import { diaCompleto } from "./datas";
import { ChipsPessoas } from "./pratos";
import {
  useAdicionarRefeicao,
  useDefinirPessoas,
  useRemoverRefeicao,
  useTrocarReceita,
} from "./queries";
import { nomeDoPrato, numeroCurto, ROTULO_TIPO, type Preparo } from "./textos";
import type { Pessoa, Refeicao, Semana, TipoRefeicao } from "./types";

export interface AlvoDaRefeicao {
  dia: string;
  tipo: TipoRefeicao;
  /** Abre já na escolha do prato novo. */
  adicionar?: boolean;
}

type Vista =
  | { nome: "lista" }
  | { nome: "adicionar" }
  | { nome: "trocar"; refeicao: Refeicao }
  | { nome: "quem"; refeicao: Refeicao };

function mensagem(e: unknown): string {
  return e instanceof ApiError ? e.detail : "Não foi possível salvar. Tente de novo.";
}

/**
 * Os pratos de uma refeição de um dia: trocar o prato, adicionar, quem come e
 * quanto, remover. No celular abre pelo "Editar" da refeição; no computador,
 * pela célula da grade (CardapioDesktop: "célula clicável abre o prato para
 * trocar"). Uma janela só: as escolhas trocam o conteúdo, não empilham.
 */
export function EditarRefeicao({
  alvo,
  onFechar,
  semana,
  pessoas,
  quem,
  preparo,
  onAbrirReceita,
}: {
  alvo: AlvoDaRefeicao | null;
  onFechar: () => void;
  semana: Semana;
  pessoas: Pessoa[];
  quem: string | null;
  preparo: Map<number, Preparo>;
  onAbrirReceita: (id: number) => void;
}) {
  return (
    <Dialogo
      aberto={alvo !== null}
      onFechar={onFechar}
      titulo={alvo ? `${ROTULO_TIPO[alvo.tipo]} · ${diaCompleto(alvo.dia)}` : ""}
    >
      {alvo ? (
        <Conteudo
          key={`${alvo.dia}-${alvo.tipo}`}
          alvo={alvo}
          onFechar={onFechar}
          semana={semana}
          pessoas={pessoas}
          quem={quem}
          preparo={preparo}
          onAbrirReceita={onAbrirReceita}
        />
      ) : null}
    </Dialogo>
  );
}

function Conteudo({
  alvo,
  onFechar,
  semana,
  pessoas,
  quem,
  preparo,
  onAbrirReceita,
}: {
  alvo: AlvoDaRefeicao;
  onFechar: () => void;
  semana: Semana;
  pessoas: Pessoa[];
  quem: string | null;
  preparo: Map<number, Preparo>;
  onAbrirReceita: (id: number) => void;
}) {
  const [vista, setVista] = useState<Vista>(alvo.adicionar ? { nome: "adicionar" } : { nome: "lista" });
  const [erro, setErro] = useState<string | null>(null);
  const [removendo, setRemovendo] = useState<number | null>(null);

  const adicionar = useAdicionarRefeicao(quem ?? "");
  const trocar = useTrocarReceita(quem ?? "");
  const remover = useRemoverRefeicao(quem ?? "");
  const definir = useDefinirPessoas(quem ?? "");

  // Sempre a cópia mais nova da semana: depois de uma escrita ela relê.
  const refeicoes = (semana.dias.find((d) => d.dia === alvo.dia)?.refeicoes ?? []).filter(
    (r) => r.tipo === alvo.tipo,
  );
  const ocupado = adicionar.isPending || trocar.isPending || remover.isPending || definir.isPending;
  const voltar = () => {
    setErro(null);
    setVista({ nome: "lista" });
  };

  if (vista.nome === "adicionar" || vista.nome === "trocar") {
    const troca = vista.nome === "trocar" ? vista.refeicao : null;
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-enfase font-forte m-0">
            {troca ? `Trocar ${nomeDoPrato(troca)}` : "Adicionar prato"}
          </h3>
          <Button variant="ghost" onClick={voltar}>
            Voltar
          </Button>
        </div>
        <BuscaReceitas
          atual={troca?.receita?.id ?? null}
          onEscolher={(receita) => {
            if (!quem || ocupado) return;
            setErro(null);
            const aoSalvar = { onSuccess: voltar, onError: (e: unknown) => setErro(mensagem(e)) };
            if (troca) {
              trocar.mutate({ refeicaoId: troca.id, receitaId: receita.id }, aoSalvar);
            } else {
              adicionar.mutate(
                { semanaId: semana.id, dia: alvo.dia, tipo: alvo.tipo, receita_id: receita.id },
                aoSalvar,
              );
            }
          }}
        />
        {erro ? (
          <p role="alert" className="text-apoio text-perigo m-0">
            {erro}
          </p>
        ) : null}
      </div>
    );
  }

  if (vista.nome === "quem") {
    return (
      <QuemCome
        refeicao={vista.refeicao}
        pessoas={pessoas}
        ocupado={ocupado}
        erro={erro}
        onVoltar={voltar}
        onSalvar={(lista) => {
          if (!quem) return;
          setErro(null);
          definir.mutate(
            { refeicaoId: vista.refeicao.id, pessoas: lista },
            { onSuccess: voltar, onError: (e) => setErro(mensagem(e)) },
          );
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {!quem ? (
        <p className="text-apoio text-texto-2 m-0">Diga quem você é para editar o cardápio.</p>
      ) : null}
      {refeicoes.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">Nada planejado nesta refeição.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-5 p-0">
          {refeicoes.map((r) => {
            const p = preparo.get(r.id);
            return (
              <li key={r.id} className="bg-superficie-2 rounded-interno flex flex-col gap-4 p-6">
                <div className="flex flex-col gap-2">
                  <span className="text-enfase font-semibold">{nomeDoPrato(r)}</span>
                  {p ? (
                    <span className={cn("text-pequeno", p.aviso ? "text-atencao-texto" : "text-texto-2")}>
                      {p.texto}
                    </span>
                  ) : null}
                  <ChipsPessoas refeicao={r} pessoas={pessoas} />
                </div>
                {removendo === r.id ? (
                  <div className="flex flex-wrap items-center gap-4">
                    <span className="text-apoio">Remover este prato?</span>
                    <Button
                      variant="danger"
                      disabled={ocupado}
                      onClick={() => {
                        setErro(null);
                        remover.mutate(r.id, {
                          onSuccess: () => setRemovendo(null),
                          onError: (e) => setErro(mensagem(e)),
                        });
                      }}
                    >
                      Remover
                    </Button>
                    <Button variant="ghost" onClick={() => setRemovendo(null)}>
                      Cancelar
                    </Button>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-3">
                    {r.receita && !r.receita.apagada ? (
                      <Button
                        variant="secondary"
                        onClick={() => {
                          onFechar();
                          onAbrirReceita(r.receita!.id);
                        }}
                      >
                        Ver receita
                      </Button>
                    ) : null}
                    <Button
                      variant="secondary"
                      disabled={!quem}
                      onClick={() => setVista({ nome: "trocar", refeicao: r })}
                    >
                      Trocar prato
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={!quem}
                      onClick={() => setVista({ nome: "quem", refeicao: r })}
                    >
                      Quem come
                    </Button>
                    <Button variant="danger" disabled={!quem} onClick={() => setRemovendo(r.id)}>
                      Remover
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      <Button disabled={!quem} onClick={() => setVista({ nome: "adicionar" })}>
        Adicionar prato
      </Button>
    </div>
  );
}

/** Quem come e quanto: porção em passos de meia, e "Padrão" volta ao perfil. */
function QuemCome({
  refeicao,
  pessoas,
  ocupado,
  erro,
  onVoltar,
  onSalvar,
}: {
  refeicao: Refeicao;
  pessoas: Pessoa[];
  ocupado: boolean;
  erro: string | null;
  onVoltar: () => void;
  onSalvar: (lista: Array<{ pessoa_id: number; porcoes: string | null }>) => void;
}) {
  type Linha = { come: boolean; porcoes: number | null };
  const [linhas, setLinhas] = useState<Record<number, Linha>>(() =>
    Object.fromEntries(
      pessoas.map((p) => {
        const na = refeicao.pessoas.find((x) => x.pessoa_id === p.id);
        return [p.id, { come: !!na, porcoes: na?.ajustada ? Number(na.porcoes) : null }];
      }),
    ),
  );

  function mudar(pessoa: Pessoa, parcial: Partial<Linha>) {
    setLinhas((atual) => ({ ...atual, [pessoa.id]: { ...(atual[pessoa.id] as Linha), ...parcial } }));
  }

  function passo(pessoa: Pessoa, delta: number) {
    const linha = linhas[pessoa.id];
    if (!linha) return;
    const atual = linha.porcoes ?? Number(pessoa.porcao_padrao);
    const novo = Math.min(20, Math.max(0.5, atual + delta));
    mudar(pessoa, { porcoes: novo === Number(pessoa.porcao_padrao) ? null : novo });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-enfase font-forte m-0">Quem come {nomeDoPrato(refeicao)}</h3>
        <Button variant="ghost" onClick={onVoltar}>
          Voltar
        </Button>
      </div>
      <p className="text-apoio text-texto-2 m-0 leading-normal">
        A porção de cada um vem do perfil. Mude aqui só para esta refeição.
      </p>
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {pessoas.map((p) => {
          const linha = linhas[p.id] ?? { come: false, porcoes: null };
          const valor = linha.porcoes ?? Number(p.porcao_padrao);
          return (
            <li
              key={p.id}
              className="bg-superficie-2 rounded-interno flex flex-wrap items-center justify-between gap-4 p-6"
            >
              <label className="flex min-h-22 cursor-pointer items-center gap-5">
                <input
                  type="checkbox"
                  className="accent-destaque size-10"
                  checked={linha.come}
                  onChange={(e) => mudar(p, { come: e.target.checked })}
                />
                <span className="text-enfase font-semibold">{p.nome}</span>
              </label>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  aria-label={`Diminuir a porção de ${p.nome}`}
                  disabled={!linha.come || valor <= 0.5}
                  onClick={() => passo(p, -0.5)}
                  className="bg-superficie text-texto flex size-22 cursor-pointer items-center justify-center rounded-[10px] border-none text-[20px] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  −
                </button>
                <span aria-live="polite" className="min-w-20 text-center text-[17px] font-bold">
                  {numeroCurto(String(valor))}
                </span>
                <button
                  type="button"
                  aria-label={`Aumentar a porção de ${p.nome}`}
                  disabled={!linha.come || valor >= 20}
                  onClick={() => passo(p, 0.5)}
                  className="bg-superficie text-texto flex size-22 cursor-pointer items-center justify-center rounded-[10px] border-none text-[20px] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  +
                </button>
              </div>
              <span className="text-pequeno text-texto-2 w-full">
                {linha.porcoes === null ? (
                  `Porção padrão: ${numeroCurto(p.porcao_padrao)}`
                ) : (
                  <>
                    Ajustada (padrão: {numeroCurto(p.porcao_padrao)}){" "}
                    <button
                      type="button"
                      onClick={() => mudar(p, { porcoes: null })}
                      className="text-destaque cursor-pointer border-none bg-transparent p-0 font-semibold"
                    >
                      Voltar ao padrão
                    </button>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      <Button
        disabled={ocupado}
        onClick={() =>
          onSalvar(
            pessoas
              .filter((p) => linhas[p.id]?.come)
              .map((p) => ({
                pessoa_id: p.id,
                porcoes: linhas[p.id]?.porcoes === null ? null : String(linhas[p.id]?.porcoes),
              })),
          )
        }
      >
        {ocupado ? "Salvando…" : "Salvar"}
      </Button>
    </div>
  );
}
