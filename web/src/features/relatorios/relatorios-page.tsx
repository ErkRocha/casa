import { useMemo, useState } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import { formatCompetencia, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DossiePainel } from "./components/dossie-painel";
import { MarkdownSeguro } from "./components/markdown-seguro";
import { useRelatorio, useRelatorios } from "./queries";
import type { RelatorioResumo } from "./types";

/**
 * Relatórios do mês — fase 6. Só leitura.
 *
 * Meses à esquerda, o relatório à direita, e ao lado do texto os números que
 * o produziram: o texto vem de um modelo e pode errar, os números vêm do
 * banco (regra 7). A geração continua pelo CLI no host (`make relatorio`);
 * não há botão de gerar aqui.
 */

/** Quantos meses fechados aparecem na coluna, mesmo sem relatório. */
const MESES_NA_COLUNA = 12;

interface Entrada {
  chave: string;
  competencia: string;
  relatorio: RelatorioResumo | null;
}

export function RelatoriosPage() {
  const lista = useRelatorios();
  const entradas = useMemo(() => montarEntradas(lista.data?.items ?? []), [lista.data]);
  const [escolhida, setEscolhida] = useState<string | null>(null);

  if (lista.isLoading) {
    return <div className="bg-surface-sunken animate-shimmer h-120 rounded-md" />;
  }
  if (lista.error) {
    return <Erro erro={lista.error} />;
  }

  const atual =
    entradas.find((e) => e.chave === escolhida) ??
    entradas.find((e) => e.relatorio !== null) ??
    entradas[0];

  return (
    <div className="flex items-start gap-8">
      <Card className="w-80 shrink-0 py-3">
        {entradas.map((e) => (
          <button
            key={e.chave}
            type="button"
            aria-current={e.chave === atual?.chave ? "true" : undefined}
            onClick={() => setEscolhida(e.chave)}
            className={cn(
              "flex w-full cursor-pointer items-center gap-4 px-7 py-4 text-left",
              e.chave === atual?.chave ? "bg-surface" : "hover:bg-surface",
            )}
          >
            <span
              className={cn(
                "text-body flex-1",
                e.relatorio ? "text-text-primary font-medium" : "text-text-tertiary",
              )}
            >
              {formatCompetencia(e.competencia)}
              {e.relatorio && e.relatorio.tipo !== "mensal" ? ` · ${e.relatorio.tipo}` : ""}
            </span>
            <span className="text-tag text-text-tertiary tracking-label-wide uppercase">
              {e.relatorio ? (e.relatorio.com_ia ? "IA" : "seco") : "—"}
            </span>
          </button>
        ))}
      </Card>

      <div className="min-w-0 flex-1">
        {atual?.relatorio ? (
          <Detalhe id={atual.relatorio.id} />
        ) : atual ? (
          <SemRelatorio competencia={atual.competencia} />
        ) : null}
      </div>
    </div>
  );
}

function Detalhe({ id }: { id: number }) {
  const { data: relatorio, isLoading, error } = useRelatorio(id);

  if (isLoading) return <div className="bg-surface-sunken animate-shimmer h-120 rounded-md" />;
  if (error) return <Erro erro={error} />;
  if (!relatorio) return null;

  return (
    <>
      <div className="mb-8 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h2 className="text-title-lg text-text-primary font-semibold">
          {formatCompetencia(relatorio.competencia)}
        </h2>
        <span
          className={cn(
            "text-tag tracking-label-wide rounded-sm px-3 py-1 uppercase",
            relatorio.com_ia ? "bg-accent-soft text-accent" : "bg-surface-sunken text-text-secondary",
          )}
        >
          {relatorio.com_ia ? "Com IA" : "Seco · só números"}
        </span>
        <span className="text-body-sm text-text-tertiary">
          prompt <span className="font-mono">{relatorio.prompt_versao}</span>
          {" · "}gerado em {formatarMomento(relatorio.criado_em)}
          {relatorio.periodo_inicio && relatorio.periodo_fim
            ? ` · dados de ${formatCompetencia(relatorio.periodo_inicio)} a ${formatCompetencia(
                mesAnterior(relatorio.periodo_fim),
              )}`
            : ""}
        </span>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_22rem] items-start gap-8">
        <Card className="p-10">
          {relatorio.com_ia ? (
            <p className="text-caption text-text-tertiary mb-7">
              Texto escrito por modelo a partir dos números ao lado. Confira qualquer afirmação
              contra eles: se um número do texto não está lá, o texto errou.
            </p>
          ) : null}
          <MarkdownSeguro texto={relatorio.conteudo} />
        </Card>

        <div>
          <CardTitle className="mb-5">Números do dossiê</CardTitle>
          {relatorio.dossie ? (
            <DossiePainel dossie={relatorio.dossie} />
          ) : (
            <Card className="p-7">
              <p className="text-body-sm text-text-tertiary">
                Este relatório foi gravado sem o dossiê de números.
              </p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function SemRelatorio({ competencia }: { competencia: string }) {
  const mes = competencia.slice(0, 7);
  return (
    <Card className="p-12">
      <h2 className="text-title-lg text-text-primary mb-4 font-semibold">
        {formatCompetencia(competencia)}
      </h2>
      <p className="text-body text-text-secondary mb-7">
        Ainda não há relatório deste mês. A geração roda no computador de casa, pelo terminal:
      </p>
      <pre className="bg-surface text-body text-text-primary rounded-md px-7 py-5 font-mono select-all">
        make relatorio m={mes}
      </pre>
      <p className="text-body-sm text-text-tertiary mt-7">
        Depois de gerado, ele aparece aqui com os números que o produziram.
      </p>
    </Card>
  );
}

function Erro({ erro }: { erro: unknown }) {
  return (
    <p role="alert" className="text-body-sm text-expense">
      {erro instanceof ApiError ? erro.detail : "Não foi possível carregar os relatórios."}
    </p>
  );
}

/**
 * Os últimos meses fechados, com ou sem relatório, mais qualquer mês que
 * tenha relatório fora dessa janela. Mais recente primeiro.
 */
function montarEntradas(relatorios: RelatorioResumo[]): Entrada[] {
  const porChave = new Map<string, Entrada>();

  const hoje = new Date();
  for (let i = 1; i <= MESES_NA_COLUNA; i++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - i, 1);
    const competencia = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
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

/** O fim do período é exclusivo: `[jul/2025, ago/2026)` termina em julho. */
function mesAnterior(competencia: string): string {
  const [ano = 0, mes = 1] = competencia.split("-").map(Number);
  const d = new Date(ano, mes - 2, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function formatarMomento(iso: string): string {
  const d = new Date(iso);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${formatDate(iso.slice(0, 10))} ${hora}`;
}
