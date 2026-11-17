import { useState } from "react";

import { Button } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Carregando, Falha } from "@/components/ui/estados";
import { ApiError } from "@/lib/api";
import { mudarParams } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { dataBR } from "./datas";
import { MedidaProduto } from "./medida-produto";
import { useConferirReceita, useDuplicarReceita, useReceita } from "./queries";
import { ReceitaForm } from "./receita-form";
import { numeroCurto, quantidadeDoIngrediente, ROTULO_TIPO } from "./textos";
import type { ReceitaDetalhe } from "./types";

/**
 * Receita (`CardapioReceitaCelular`): tela cheia no celular, painel lateral
 * no computador. `receita` é o id, ou "nova"; `editar` abre o formulário.
 * Tudo vem do endereço (`#cardapio?receita=6&editar=1`).
 */
export function ReceitaPainel({
  receita,
  editar,
  quem,
  usos,
}: {
  /** O parâmetro `receita` do endereço: um id, "nova", ou nulo (fechado). */
  receita: string | null;
  editar: boolean;
  quem: string | null;
  /** Quantas vezes a receita aparece na semana aberta, quando se sabe. */
  usos: (id: number) => number | null;
}) {
  const nova = receita === "nova";
  const id = receita && /^\d+$/.test(receita) ? Number(receita) : null;
  const dados = useReceita(id);
  const fechar = () => mudarParams({ receita: null, editar: null }, { substituir: true });

  const titulo = nova ? "Nova receita" : (dados.data?.nome ?? "Receita");

  return (
    <Dialogo aberto={receita !== null} onFechar={fechar} titulo={titulo} lateral larga>
      {receita === null ? null : nova ? (
        <ReceitaForm
          inicial={null}
          quem={quem}
          onCancelar={fechar}
          onSalva={(r) => mudarParams({ receita: String(r.id), editar: null }, { substituir: true })}
        />
      ) : id === null ? (
        <p className="text-apoio text-texto-2 m-0">Receita não encontrada.</p>
      ) : dados.isLoading ? (
        <Carregando rotulo="Carregando a receita" alturas={["h-40", "h-80"]} />
      ) : dados.isError || !dados.data ? (
        <Falha
          titulo="Não foi possível ler a receita"
          erro={dados.error}
          onTentar={() => void dados.refetch()}
        />
      ) : editar ? (
        <ReceitaForm
          inicial={dados.data}
          quem={quem}
          onCancelar={() => mudarParams({ editar: null }, { substituir: true })}
          onSalva={() => mudarParams({ editar: null }, { substituir: true })}
        />
      ) : (
        <ReceitaVista receita={dados.data} quem={quem} usos={usos(dados.data.id)} />
      )}
    </Dialogo>
  );
}

function Estatistica({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="bg-superficie-2 rounded-interno flex flex-col gap-1 px-6 py-5">
      <span className="text-pequeno text-texto-2">{rotulo}</span>
      <span className="text-enfase font-forte">{valor}</span>
    </div>
  );
}

/** Os passos do modo de preparo: um por linha, sem a numeração que veio escrita. */
function passosDoModo(modo: string | null): string[] {
  return (modo ?? "")
    .split(/\r?\n/)
    .map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter(Boolean);
}

function ReceitaVista({
  receita,
  quem,
  usos,
}: {
  receita: ReceitaDetalhe;
  quem: string | null;
  usos: number | null;
}) {
  const conferir = useConferirReceita(quem ?? "");
  const duplicar = useDuplicarReceita(quem ?? "");
  const [medindo, setMedindo] = useState<number | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const aoFalhar = (e: unknown) =>
    setAviso(e instanceof ApiError ? e.detail : "Não foi possível. Tente de novo.");
  const passos = passosDoModo(receita.modo_preparo);
  const porcoes = Number(receita.rendimento_porcoes);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-start justify-between gap-4">
        <span className="text-apoio text-texto-2">
          {ROTULO_TIPO[receita.tipo]}
          {usos ? ` · usada em ${usos} ${usos === 1 ? "prato" : "pratos"} nesta semana` : ""}
        </span>
        <Button
          variant="secondary"
          disabled={!quem}
          onClick={() => mudarParams({ editar: "1" }, { substituir: true })}
        >
          Editar
        </Button>
      </div>

      {receita.quantidades_revisadas ? (
        receita.revisadas_por && receita.revisadas_em ? (
          <p className="text-pequeno text-texto-2 m-0">
            Quantidades conferidas por {receita.revisadas_por} em {dataBR(receita.revisadas_em)}.
          </p>
        ) : null
      ) : (
        <div className="bg-atencao-fundo-2 text-atencao-texto rounded-cartao flex flex-col gap-4 px-7 py-6 shadow-[inset_0_0_0_1px_#F0D9A6]">
          <span className="text-apoio leading-normal">
            <strong>Quantidades estimadas.</strong> Esta receita veio da carga inicial; confira se a
            quantidade por porção é a que vocês usam.
          </span>
          <Button
            disabled={!quem || conferir.isPending}
            onClick={() => {
              setAviso(null);
              conferir.mutate(receita.id, { onError: aoFalhar });
            }}
            className="self-start"
          >
            {conferir.isPending ? "Salvando…" : "Conferi, está certa"}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Estatistica
          rotulo="Rende"
          valor={`${numeroCurto(receita.rendimento_porcoes)} ${porcoes === 1 ? "porção" : "porções"}`}
        />
        <Estatistica
          rotulo="Tempo"
          valor={receita.tempo_preparo_min ? `${receita.tempo_preparo_min} min` : "Não informado"}
        />
        <Estatistica
          rotulo="Pode antecipar"
          valor={
            receita.pode_antecipar
              ? `Sim, dura ${receita.dura_dias ?? "?"} ${receita.dura_dias === 1 ? "dia" : "dias"}`
              : "Não, faz na hora"
          }
        />
        <Estatistica rotulo="Congela" valor={receita.pode_congelar ? "Sim" : "Não"} />
      </div>

      <section aria-label="Ingredientes" className="flex flex-col">
        <div className="flex items-baseline justify-between gap-4 pb-3">
          <h3 className="text-bloco font-forte m-0">Ingredientes</h3>
          <span className="text-pequeno text-texto-2">
            para {numeroCurto(receita.rendimento_porcoes)} {porcoes === 1 ? "porção" : "porções"}
          </span>
        </div>
        {receita.ingredientes.length === 0 ? (
          <p className="text-apoio text-texto-2 m-0">Sem ingredientes cadastrados.</p>
        ) : (
          receita.ingredientes.map((i) => (
            <div key={i.id} className="linha-acima flex flex-col gap-3 py-4">
              <div className="flex items-start justify-between gap-5">
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-corpo font-semibold">{i.produto_nome}</span>
                  {i.observacao ? (
                    <span className="text-pequeno text-texto-2">{i.observacao}</span>
                  ) : null}
                  {i.converte ? null : (
                    <span className="text-pequeno text-atencao-selo font-semibold">
                      Sem medida cadastrada: vai à lista sem quantidade.
                    </span>
                  )}
                </span>
                <span className="text-corpo shrink-0 font-[650]">
                  {quantidadeDoIngrediente(i.quantidade, i.unidade)}
                </span>
              </div>
              {i.converte ? null : medindo === i.id ? (
                <MedidaProduto
                  produtoId={i.produto_id}
                  produtoNome={i.produto_nome}
                  quem={quem}
                  onSalva={() => setMedindo(null)}
                  onCancelar={() => setMedindo(null)}
                />
              ) : (
                <button
                  type="button"
                  disabled={!quem}
                  onClick={() => setMedindo(i.id)}
                  className={cn(
                    "text-destaque text-apoio min-h-22 cursor-pointer self-start border-none bg-transparent p-0 font-semibold",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                  )}
                >
                  Cadastrar a medida de {i.produto_nome}
                </button>
              )}
            </div>
          ))
        )}
      </section>

      {passos.length > 0 ? (
        <section aria-label="Modo de preparo" className="flex flex-col gap-4">
          <h3 className="text-bloco font-forte m-0">Modo de preparo</h3>
          {passos.length === 1 ? (
            <p className="text-corpo m-0 leading-relaxed">{passos[0]}</p>
          ) : (
            <ol className="text-corpo m-0 flex flex-col gap-3 pl-9 leading-relaxed">
              {passos.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ol>
          )}
        </section>
      ) : null}

      {aviso ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {aviso}
        </p>
      ) : null}

      <Button
        variant="secondary"
        disabled={!quem || duplicar.isPending}
        onClick={() => {
          setAviso(null);
          duplicar.mutate(receita.id, {
            onSuccess: (copia) =>
              mudarParams({ receita: String(copia.id), editar: "1" }, { substituir: true }),
            onError: aoFalhar,
          });
        }}
      >
        {duplicar.isPending ? "Duplicando…" : "Duplicar como variação"}
      </Button>
    </div>
  );
}
