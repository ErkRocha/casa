import type { ReactNode } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { formatBRLTexto, formatCompetencia, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Dossie } from "../types";

/**
 * Os números que o modelo recebeu, ao lado do texto (regra 7: quem soma é o
 * banco). Cada afirmação do relatório tem que poder ser conferida aqui; se
 * um número do texto não aparece neste painel, o texto inventou.
 *
 * Só exibe: nada é somado ou recalculado no navegador.
 */
export function DossiePainel({ dossie }: { dossie: Dossie }) {
  const { resumo, cobertura, gasto_por_categoria, divisao_pessoas, comparacao } = dossie;
  const { orcamento, atipicas, reajustes } = dossie;

  return (
    <div className="flex flex-col gap-6">
      {resumo ? (
        <Bloco titulo="Resumo do mês">
          <Linha rotulo="Despesas" valor={formatBRLTexto(resumo.despesas)} />
          <Linha rotulo="Receitas" valor={formatBRLTexto(resumo.receitas)} />
          <Linha rotulo="Saldo" valor={formatBRLTexto(resumo.saldo)} forte />
          <Linha rotulo="Lançamentos" valor={String(resumo.transacoes ?? 0)} />
          {resumo.em_curso ? (
            <Nota>Mês ainda em curso quando o relatório foi gerado.</Nota>
          ) : null}
        </Bloco>
      ) : null}

      {cobertura ? (
        <Bloco titulo="Cobertura de categoria">
          <Linha rotulo="Categorizado" valor={pct(cobertura.percentual)} />
          <Linha rotulo="Sem categoria" valor={formatBRLTexto(cobertura.sem_categoria)} />
          <Linha
            rotulo="Lançamentos sem categoria"
            valor={String(cobertura.transacoes_sem_categoria ?? 0)}
          />
        </Bloco>
      ) : null}

      {gasto_por_categoria?.linhas?.length ? (
        <Bloco titulo="Gasto por categoria">
          {gasto_por_categoria.linhas.map((l) => (
            <Linha
              key={l.categoria}
              rotulo={l.categoria}
              valor={formatBRLTexto(l.total)}
              detalhe={pct(l.participacao)}
            />
          ))}
        </Bloco>
      ) : null}

      {divisao_pessoas?.linhas?.length ? (
        <Bloco titulo="Por pessoa">
          {divisao_pessoas.linhas.map((l) => (
            <Linha
              key={l.pessoa}
              rotulo={l.pessoa}
              valor={formatBRLTexto(l.total)}
              detalhe={pct(l.participacao)}
            />
          ))}
        </Bloco>
      ) : null}

      {comparacao ? (
        <Bloco
          titulo={
            comparacao.competencia_anterior
              ? `Contra ${formatCompetencia(comparacao.competencia_anterior)}`
              : "Comparação"
          }
        >
          <Linha rotulo="Este mês" valor={formatBRLTexto(comparacao.total_atual)} />
          <Linha rotulo="Mês anterior" valor={formatBRLTexto(comparacao.total_anterior)} />
          <Linha
            rotulo="Diferença"
            valor={formatBRLTexto(comparacao.diferenca)}
            detalhe={comparacao.variacao_pct != null ? pct(comparacao.variacao_pct) : undefined}
          />
          <Linha
            rotulo={`Média de ${comparacao.meses_na_media ?? 0} meses`}
            valor={formatBRLTexto(comparacao.media_janela)}
          />
        </Bloco>
      ) : null}

      {orcamento?.tem_orcamento && orcamento.linhas?.length ? (
        <Bloco titulo={`Orçamento · ${orcamento.estourados ?? 0} estourado(s)`}>
          {orcamento.linhas.map((l) => (
            <Linha
              key={l.categoria}
              rotulo={l.categoria}
              valor={`${formatBRLTexto(l.realizado)} de ${formatBRLTexto(l.meta)}`}
              detalhe={pct(l.percentual)}
              alerta={l.situacao === "estourado"}
            />
          ))}
        </Bloco>
      ) : null}

      {atipicas?.linhas?.length ? (
        <Bloco titulo="Fora do padrão">
          {atipicas.linhas.map((l, i) => (
            <Linha
              key={`${l.data}-${i}`}
              rotulo={`${formatDate(l.data)} · ${l.descricao}`}
              valor={formatBRLTexto(l.valor)}
              detalhe={`mediana ${formatBRLTexto(l.mediana_categoria)}`}
            />
          ))}
        </Bloco>
      ) : null}

      {reajustes?.linhas?.length ? (
        <Bloco titulo="Reajustes">
          {reajustes.linhas.map((l, i) => (
            <Linha
              key={`${l.descricao}-${i}`}
              rotulo={l.descricao}
              valor={`${formatBRLTexto(l.valor_anterior)} → ${formatBRLTexto(l.valor_atual)}`}
              detalhe={pct(l.variacao_pct)}
            />
          ))}
        </Bloco>
      ) : null}
    </div>
  );
}

/** `42,5%` a partir do texto que a API manda (0 a 100). */
function pct(valor: string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function Bloco({ titulo, children }: { titulo: ReactNode; children: ReactNode }) {
  return (
    <Card className="p-7">
      <CardTitle className="mb-5">{titulo}</CardTitle>
      <div className="flex flex-col gap-3">{children}</div>
    </Card>
  );
}

function Linha({
  rotulo,
  valor,
  detalhe,
  forte = false,
  alerta = false,
}: {
  rotulo: string;
  valor: string;
  detalhe?: string;
  forte?: boolean;
  alerta?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-4">
      <span className="text-body-sm text-text-secondary min-w-0 flex-1 truncate" title={rotulo}>
        {rotulo}
      </span>
      {detalhe ? <span className="text-caption text-text-tertiary tabular">{detalhe}</span> : null}
      <span
        className={cn(
          "text-body-sm tabular whitespace-nowrap",
          forte ? "text-text-primary font-semibold" : "text-text-primary",
          alerta && "text-expense",
        )}
      >
        {valor}
      </span>
    </div>
  );
}

function Nota({ children }: { children: ReactNode }) {
  return <p className="text-caption text-text-tertiary mt-1">{children}</p>;
}
