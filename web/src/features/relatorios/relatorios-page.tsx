import { useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { Pilula, Selo } from "@/components/ui/controls";
import { Carregando, Falha } from "@/components/ui/estados";
import { Icone } from "@/components/ui/icone";
import { competenciaDe, diaDeMes, mesCurto, mesPorExtenso, nomeDoMes, reais, somarMeses } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { DossiePainel } from "./components/dossie-painel";
import { MarkdownSeguro } from "./components/markdown-seguro";
import { useRelatorio, useRelatorios } from "./queries";
import type { RelatorioDetalhe, RelatorioResumo } from "./types";

/**
 * Relatórios do mês (`RelatoriosDesktop`, `RelatoriosCelular`; D-22). Só
 * leitura: os meses, o texto e, ao lado, os números que o produziram. O
 * texto vem de um modelo e pode errar; os números vêm do banco (regra 7). A
 * geração continua pelo CLI no computador de casa (`make relatorio`).
 */

/** Quantos meses fechados aparecem na lista, mesmo sem relatório. */
const MESES_NA_LISTA = 12;

interface Entrada {
  chave: string;
  competencia: string;
  relatorio: RelatorioResumo | null;
}

export function RelatoriosPage() {
  const lista = useRelatorios();
  const atualDoMes = competenciaDe(new Date());
  const entradas = useMemo(
    () => montarEntradas(lista.data?.items ?? [], atualDoMes),
    [lista.data, atualDoMes],
  );
  const [escolhida, setEscolhida] = useState<string | null>(null);

  const atual =
    entradas.find((e) => e.chave === escolhida) ??
    entradas.find((e) => e.relatorio !== null) ??
    entradas[0];
  const mesCorrenteSemRelatorio = !entradas.some(
    (e) => e.competencia === atualDoMes && e.relatorio !== null,
  );

  return (
    <div className="flex max-w-[1100px] flex-col gap-7 md:gap-8">
      <header className="flex items-center gap-4">
        <a
          href={href("mais")}
          aria-label="Voltar"
          className="bg-superficie text-texto rounded-interno flex size-22 shrink-0 items-center justify-center md:hidden"
        >
          <Icone nome="esquerda" />
        </a>
        <h1 className="md:text-pagina m-0 text-[22px] font-bold tracking-[-0.3px] md:tracking-[-0.4px]">
          Relatórios do mês
        </h1>
      </header>

      {lista.isLoading ? (
        <Carregando rotulo="Carregando os relatórios" alturas={["h-160"]} />
      ) : lista.isError ? (
        <Falha
          titulo="Não foi possível carregar os relatórios"
          erro={lista.error}
          onTentar={() => void lista.refetch()}
        />
      ) : (
        <>
          {/* Celular: os meses em pílulas. */}
          <nav aria-label="Meses" className="-mx-7 flex gap-4 overflow-x-auto px-7 md:hidden">
            {entradas.map((e) => (
              <Pilula
                key={e.chave}
                fundo="superficie"
                ativa={e.chave === atual?.chave}
                aria-current={e.chave === atual?.chave ? "page" : undefined}
                onClick={() => setEscolhida(e.chave)}
                className={cn(!e.relatorio && e.chave !== atual?.chave && "text-texto-inativo")}
              >
                {e.competencia.slice(0, 4) === atualDoMes.slice(0, 4)
                  ? mesCurto(e.competencia).split(" ")[0]
                  : mesCurto(e.competencia)}
                <span className="sr-only">
                  {`${e.competencia.slice(0, 4) === atualDoMes.slice(0, 4) ? ` de ${e.competencia.slice(0, 4)}` : ""}${e.relatorio ? "" : ", sem relatório"}`}
                </span>
              </Pilula>
            ))}
          </nav>

          <div className="flex flex-col items-start gap-8 lg:flex-row">
            {/* Computador: a lista de meses à esquerda. */}
            <nav
              aria-label="Meses"
              className="bg-superficie rounded-bloco hidden w-full flex-col gap-1 p-4 md:flex lg:w-[230px] lg:shrink-0"
            >
              {entradas.map((e) => {
                const ativa = e.chave === atual?.chave;
                return (
                  <button
                    key={e.chave}
                    type="button"
                    aria-current={ativa ? "page" : undefined}
                    onClick={() => setEscolhida(e.chave)}
                    className={cn(
                      "rounded-interno text-texto flex min-h-22 cursor-pointer items-center justify-between gap-4 border-none px-6 text-left",
                      ativa ? "bg-destaque-fundo" : "hover:bg-superficie-2 bg-transparent",
                    )}
                  >
                    <span className={cn("text-corpo", ativa ? "font-forte" : "font-normal")}>
                      {e.competencia.slice(0, 4) === atualDoMes.slice(0, 4)
                        ? nomeDoMesCapital(e.competencia)
                        : mesCurto(e.competencia)}
                      {e.relatorio && e.relatorio.tipo !== "mensal" ? `, ${e.relatorio.tipo}` : ""}
                    </span>
                    <SeloDoMes relatorio={e.relatorio} />
                  </button>
                );
              })}
            </nav>

            <div className="flex w-full min-w-0 flex-1 flex-col gap-7 md:gap-8 lg:flex-row lg:items-start">
              {atual?.relatorio ? (
                <Detalhe id={atual.relatorio.id} />
              ) : atual ? (
                <SemRelatorio competencia={atual.competencia} />
              ) : null}
            </div>
          </div>

          {mesCorrenteSemRelatorio && atual?.competencia !== atualDoMes ? (
            <Card className="hidden flex-wrap items-center gap-6 px-11 py-9 md:flex">
              <span className="flex flex-[1_1_320px] flex-col gap-1">
                <span className="text-corpo font-forte">
                  {nomeDoMesCapital(atualDoMes)} ainda não tem relatório
                </span>
                <span className="text-apoio text-texto-2">
                  Ele é gerado depois que o mês fecha. Para gerar agora, rode no computador de casa:
                </span>
              </span>
              <Comando competencia={atualDoMes} />
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}

function Detalhe({ id }: { id: number }) {
  const { data: relatorio, isLoading, error, refetch } = useRelatorio(id);

  if (isLoading) return <Carregando rotulo="Carregando o relatório" alturas={["h-160"]} className="w-full" />;
  if (error || !relatorio) {
    return (
      <div className="w-full">
        <Falha titulo="Não foi possível abrir o relatório" erro={error} onTentar={() => void refetch()} />
      </div>
    );
  }

  return (
    <>
      {/* Celular: despesas, receitas e sobra antes do texto. */}
      {relatorio.dossie?.resumo ? (
        <Card className="grid w-full grid-cols-3 gap-4 p-8 md:hidden">
          <Resumo rotulo="Despesas" valor={relatorio.dossie.resumo.despesas} />
          <Resumo rotulo="Receitas" valor={relatorio.dossie.resumo.receitas} receita />
          <Resumo rotulo="Sobra" valor={relatorio.dossie.resumo.saldo} />
        </Card>
      ) : null}

      <Artigo relatorio={relatorio} />

      {/* Computador: os números ao lado. */}
      <aside aria-label="Números usados no relatório" className="hidden w-full md:block lg:w-[280px] lg:shrink-0">
        {relatorio.dossie ? (
          <DossiePainel dossie={relatorio.dossie} />
        ) : (
          <SemDossie />
        )}
      </aside>

      {/* Celular: os números recolhidos. */}
      <details className="bg-superficie rounded-bloco w-full px-9 py-8 md:hidden">
        <summary className="text-corpo font-forte flex min-h-22 cursor-pointer items-center">
          Ver os números que o relatório usou
        </summary>
        <div className="pt-4">
          {relatorio.dossie ? <DossiePainel dossie={relatorio.dossie} solto={false} /> : <SemDossie />}
        </div>
      </details>
    </>
  );
}

function Artigo({ relatorio }: { relatorio: RelatorioDetalhe }) {
  const quando = diaDeMes(dataLocal(new Date(relatorio.criado_em)));
  return (
    <article className="bg-superficie rounded-bloco flex w-full min-w-0 flex-1 flex-col gap-7 px-9 py-10 md:px-15 md:py-13">
      <header className="linha-abaixo-suave flex flex-col gap-3 pb-5">
        <div className="flex flex-wrap items-center gap-5">
          <h2 className="md:text-valor-medio m-0 text-[20px] font-bold">
            {mesPorExtenso(relatorio.competencia)}
          </h2>
          <Selo tom={relatorio.com_ia ? "destaque" : "neutro"}>
            {relatorio.com_ia ? "Escrito com IA" : "Só números"}
          </Selo>
        </div>
        <p className="text-pequeno md:text-apoio text-texto-2 m-0">
          Gerado em {quando}
          <span className="hidden md:inline">
            {relatorio.com_ia
              ? ". Os números ao lado são exatamente os que o modelo recebeu; se um número do texto não está lá, o texto errou."
              : ", só a partir dos números ao lado, sem modelo."}
          </span>{" "}
          <span className="text-texto-inativo">({relatorio.prompt_versao})</span>
        </p>
      </header>
      <MarkdownSeguro texto={relatorio.conteudo} />
    </article>
  );
}

function SemRelatorio({ competencia }: { competencia: string }) {
  return (
    <article className="bg-superficie rounded-bloco flex w-full flex-col items-start gap-5 px-9 py-10 md:px-15 md:py-13">
      <h2 className="md:text-valor-medio m-0 text-[20px] font-bold">{mesPorExtenso(competencia)}</h2>
      <p className="text-corpo text-texto-2 m-0 leading-normal">
        Este mês ainda não tem relatório. Ele é gerado no computador de casa, pelo terminal:
      </p>
      <Comando competencia={competencia} />
      <p className="text-apoio text-texto-2 m-0">
        Depois de gerado, aparece aqui com os números que o produziram.
      </p>
    </article>
  );
}

function SemDossie() {
  return (
    <p className="text-apoio text-texto-2 bg-superficie rounded-bloco m-0 px-10 py-9">
      Este relatório foi gravado sem o dossiê de números.
    </p>
  );
}

function Comando({ competencia }: { competencia: string }) {
  return (
    <code className="bg-superficie-2 text-apoio rounded-campo px-6 py-4 select-all">
      make relatorio m={competencia.slice(0, 7)}
    </code>
  );
}

function Resumo({ rotulo, valor, receita = false }: { rotulo: string; valor?: string; receita?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-selo text-texto-2">{rotulo}</span>
      <span className={cn("text-enfase font-bold", receita && "text-receita")}>
        {reais(valor, { centavos: false })}
      </span>
    </div>
  );
}

function SeloDoMes({ relatorio }: { relatorio: RelatorioResumo | null }) {
  const classe = "text-selo font-semibold whitespace-nowrap";
  if (!relatorio) return <Selo tom="inativo" className={classe}>Sem relatório</Selo>;
  return relatorio.com_ia ? (
    <Selo tom="destaque" className={classe}>Com IA</Selo>
  ) : (
    <Selo tom="neutro" className={classe}>Só números</Selo>
  );
}

/** `2026-10-01` do dia local de um instante (o `criado_em` vem em UTC). */
function dataLocal(momento: Date): string {
  const mes = String(momento.getMonth() + 1).padStart(2, "0");
  const dia = String(momento.getDate()).padStart(2, "0");
  return `${momento.getFullYear()}-${mes}-${dia}`;
}

function nomeDoMesCapital(competencia: string): string {
  const nome = nomeDoMes(Number(competencia.slice(5, 7)));
  return nome.charAt(0).toUpperCase() + nome.slice(1);
}

/**
 * O mês corrente, os últimos meses fechados e qualquer mês que tenha
 * relatório fora dessa janela. Mais recente primeiro.
 */
function montarEntradas(relatorios: RelatorioResumo[], corrente: string): Entrada[] {
  const porChave = new Map<string, Entrada>();
  for (let i = 0; i <= MESES_NA_LISTA; i++) {
    const competencia = somarMeses(corrente, -i);
    porChave.set(`${competencia}|mensal`, { chave: `${competencia}|mensal`, competencia, relatorio: null });
  }
  for (const r of relatorios) {
    const chave = `${r.competencia}|${r.tipo}`;
    porChave.set(chave, { chave, competencia: r.competencia, relatorio: r });
  }
  return [...porChave.values()].sort((a, b) =>
    a.competencia === b.competencia
      ? a.chave.localeCompare(b.chave)
      : b.competencia.localeCompare(a.competencia),
  );
}
