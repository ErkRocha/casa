import type { ReactNode } from "react";

import { diaDeMes, mesPorExtenso, reais } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Dossie } from "../types";

/**
 * Os números que o modelo recebeu, ao lado do texto (regra 7: quem soma é o
 * banco). Cada afirmação do relatório tem que poder ser conferida aqui; se
 * um número do texto não aparece neste painel, o texto inventou. Por isso
 * os valores vão com centavos, exatamente como estão no dossiê.
 *
 * Os dois primeiros blocos são os da prancheta ("Números do mês", "Maiores
 * categorias"); os outros seguem o mesmo visual, com o resto do dossiê.
 * Só exibe: nada é somado ou recalculado no navegador.
 *
 * `solto`: blocos brancos separados (computador). Sem ele, os blocos ficam
 * dentro do "Ver os números" do celular.
 */
export function DossiePainel({ dossie, solto = true }: { dossie: Dossie; solto?: boolean }) {
  const { resumo, cobertura, gasto_por_categoria, divisao_pessoas, comparacao } = dossie;
  const { orcamento, atipicas, reajustes } = dossie;
  const props = { solto };

  return (
    <div className={cn("flex flex-col", solto ? "gap-6" : "gap-7")}>
      {resumo || comparacao || cobertura ? (
        <Bloco titulo="Números do mês" {...props}>
          {resumo ? (
            <>
              <Linha rotulo="Despesas" valor={reais(resumo.despesas)} />
              <Linha rotulo="Receitas" valor={reais(resumo.receitas)} />
              <Linha rotulo="Sobra" valor={reais(resumo.saldo)} />
              <Linha rotulo="Lançamentos" valor={String(resumo.transacoes ?? 0)} />
            </>
          ) : null}
          {comparacao?.media_janela ? (
            <Linha
              rotulo={`Média de ${comparacao.meses_na_media ?? 0} meses`}
              valor={reais(comparacao.media_janela)}
            />
          ) : null}
          {cobertura ? <Linha rotulo="Com categoria" valor={pct(cobertura.percentual)} /> : null}
          {resumo?.em_curso ? <Nota>O mês ainda estava em curso quando o relatório foi gerado.</Nota> : null}
        </Bloco>
      ) : null}

      {gasto_por_categoria?.linhas?.length ? (
        <Bloco titulo="Maiores categorias" {...props}>
          {gasto_por_categoria.linhas.map((l) => (
            <Linha key={l.categoria} rotulo={l.categoria} valor={reais(l.total)} detalhe={pct(l.participacao)} />
          ))}
        </Bloco>
      ) : null}

      {divisao_pessoas?.linhas?.length ? (
        <Bloco titulo="Por pessoa" {...props}>
          {divisao_pessoas.linhas.map((l) => (
            <Linha key={l.pessoa} rotulo={l.pessoa} valor={reais(l.total)} detalhe={pct(l.participacao)} />
          ))}
        </Bloco>
      ) : null}

      {comparacao?.competencia_anterior ? (
        <Bloco titulo={`Contra ${mesPorExtenso(comparacao.competencia_anterior).toLowerCase()}`} {...props}>
          <Linha rotulo="Este mês" valor={reais(comparacao.total_atual)} />
          <Linha rotulo="Mês anterior" valor={reais(comparacao.total_anterior)} />
          <Linha
            rotulo="Diferença"
            valor={reais(comparacao.diferenca)}
            detalhe={comparacao.variacao_pct != null ? pct(comparacao.variacao_pct) : undefined}
          />
        </Bloco>
      ) : null}

      {orcamento?.tem_orcamento && orcamento.linhas?.length ? (
        <Bloco
          titulo={
            orcamento.estourados
              ? `Orçamento, ${orcamento.estourados} estourado${orcamento.estourados > 1 ? "s" : ""}`
              : "Orçamento"
          }
          {...props}
        >
          {orcamento.linhas.map((l) => (
            <Linha
              key={l.categoria}
              rotulo={l.categoria}
              valor={`${reais(l.realizado)} de ${reais(l.meta)}`}
              detalhe={pct(l.percentual)}
              alerta={l.situacao === "estourado"}
              empilhada
            />
          ))}
        </Bloco>
      ) : null}

      {atipicas?.linhas?.length ? (
        <Bloco titulo="Fora do padrão" {...props}>
          {atipicas.linhas.map((l, i) => (
            <Linha
              key={`${l.data}-${i}`}
              rotulo={`${diaDeMes(l.data)}, ${l.descricao}`}
              valor={reais(l.valor)}
              detalhe={`mediana ${reais(l.mediana_categoria)}`}
              empilhada
            />
          ))}
        </Bloco>
      ) : null}

      {reajustes?.linhas?.length ? (
        <Bloco titulo="Reajustes" {...props}>
          {reajustes.linhas.map((l, i) => (
            <Linha
              key={`${l.descricao}-${i}`}
              rotulo={l.descricao}
              valor={`${reais(l.valor_anterior)} → ${reais(l.valor_atual)}`}
              detalhe={pct(l.variacao_pct)}
              empilhada
            />
          ))}
        </Bloco>
      ) : null}
    </div>
  );
}

/** `42,5%` a partir do texto que a API manda (0 a 100). Percentual, não dinheiro. */
function pct(valor: string | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function Bloco({
  titulo,
  solto,
  children,
}: {
  titulo: ReactNode;
  solto: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={cn("flex flex-col gap-3", solto && "bg-superficie rounded-bloco px-10 py-9")}
    >
      <h3 className="text-enfase font-forte m-0 pb-1">{titulo}</h3>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

function Linha({
  rotulo,
  valor,
  detalhe,
  alerta = false,
  empilhada = false,
}: {
  rotulo: string;
  valor: string;
  detalhe?: string;
  alerta?: boolean;
  /** Rótulo numa linha e os números na de baixo: valores longos ("R$ 215,00 de R$ 200,00"). */
  empilhada?: boolean;
}) {
  const numeros = (
    <>
      {detalhe ? <span className="text-pequeno text-texto-2">{detalhe}</span> : null}
      <span className={cn("font-forte whitespace-nowrap", alerta && "text-orcamento-estourado")}>
        {valor}
      </span>
    </>
  );
  if (empilhada) {
    return (
      <div className="linha-acima text-apoio flex flex-col gap-1 py-3">
        <span className="text-texto-2">{rotulo}</span>
        <span className="flex items-baseline justify-between gap-4">{numeros}</span>
      </div>
    );
  }
  return (
    <div className="linha-acima text-apoio flex items-baseline gap-4 py-3">
      <span className="text-texto-2 min-w-0 flex-1 truncate" title={rotulo}>
        {rotulo}
      </span>
      {numeros}
    </div>
  );
}

function Nota({ children }: { children: ReactNode }) {
  return <p className="text-pequeno text-texto-2 m-0 pt-3">{children}</p>;
}
