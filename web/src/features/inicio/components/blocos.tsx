import type { ReactNode } from "react";

import { CabecalhoBloco, Card } from "@/components/ui/card";
import { Selo } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import type { Pessoa } from "@/features/cadastros/types";
import { corDaChave } from "@/features/filters/baldes";
import type { RevisarResumo } from "@/features/revisar/types";
import { inteiro, reais, reaisAbs, sinal } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { COR_FAIXA, textoComparacao, textoRevisar } from "../textos";
import type { AvisoOrcamento, AvisoReajuste, Inicio } from "../types";

function textoPrevisao(i: Inicio, curto: boolean): string {
  const diferenca = i.previsao?.diferenca_orcamento;
  if (!diferenca) return "no ritmo atual";
  const s = sinal(diferenca);
  if (s === 0) return curto ? "no limite" : "exatamente o orçamento, no ritmo atual";
  const quanto = reaisAbs(diferenca, { centavos: false });
  const lado = s > 0 ? "acima" : "abaixo";
  return curto ? `${quanto} ${lado}` : `${quanto} ${lado} do orçamento, no ritmo atual`;
}

function BarraOrcamento({ i, grossa = false }: { i: Inicio; grossa?: boolean }) {
  if (!i.orcamento) return null;
  const largura = Math.min(i.orcamento.percentual_usado, 100);
  return (
    <div className={cn("bg-trilho rounded-[3px]", grossa ? "h-4" : "h-3")}>
      <div
        className={cn("h-full rounded-[3px]", COR_FAIXA[i.orcamento.faixa])}
        style={{ width: `${largura}%` }}
      />
    </div>
  );
}

function Caixa({
  rotulo,
  valor,
  apoio,
  tom = "interno",
  tamanho = "normal",
  children,
  className,
}: {
  rotulo: string;
  valor: ReactNode;
  apoio?: ReactNode;
  tom?: "interno" | "atencao" | "nenhum";
  /** `grande`: o gasto do mês; `compacto`: as caixas lado a lado do celular. */
  tamanho?: "grande" | "normal" | "compacto";
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col",
        tamanho === "compacto" ? "gap-2 p-6" : "gap-3 px-8 py-7",
        tom === "interno" && "bg-superficie-2 rounded-interno",
        tom === "atencao" && "bg-atencao-fundo text-atencao-texto rounded-interno",
        className,
      )}
    >
      <span
        className={cn(
          tamanho === "compacto" ? "text-pequeno" : "text-apoio",
          tom !== "atencao" && "text-texto-2",
        )}
      >
        {rotulo}
      </span>
      <span
        className={cn(
          tamanho === "grande" && "text-numero leading-[1.05] font-bold tracking-[-1px]",
          tamanho === "normal" && "text-valor font-forte",
          tamanho === "compacto" && "font-forte text-[18px]",
        )}
      >
        {valor}
      </span>
      {children}
      {apoio ? (
        <span className={cn("text-pequeno", tom !== "atencao" && "text-texto-2")}>{apoio}</span>
      ) : null}
    </div>
  );
}

function CaixaOrcamento({ i, compacta = false }: { i: Inicio; compacta?: boolean }) {
  return (
    <Caixa
      rotulo="Orçamento do mês"
      valor={i.orcamento ? reais(i.orcamento.total, { centavos: false }) : "Sem meta"}
      apoio={i.orcamento ? `${i.orcamento.percentual_usado}% já usado` : "Nenhuma meta neste mês"}
      tamanho={compacta ? "compacto" : "normal"}
    >
      {compacta ? null : <BarraOrcamento i={i} />}
    </Caixa>
  );
}

function CaixaFechamento({ i, compacta = false }: { i: Inicio; compacta?: boolean }) {
  const tamanho = compacta ? "compacto" : "normal";
  if (i.previsao) {
    const acima = sinal(i.previsao.diferenca_orcamento) > 0;
    return (
      <Caixa
        rotulo="Previsão de fechamento"
        valor={reais(i.previsao.valor, { centavos: false })}
        apoio={textoPrevisao(i, compacta)}
        tom={acima ? "atencao" : "interno"}
        tamanho={tamanho}
      />
    );
  }
  // Mês fechado: o que fechou, contra a meta que havia.
  return (
    <Caixa
      rotulo="Fechamento do mês"
      valor={reais(i.gasto, { centavos: false })}
      apoio={i.orcamento ? `${i.orcamento.percentual_usado}% do orçamento` : "mês encerrado"}
      tom={i.orcamento?.faixa === "estourado" ? "atencao" : "interno"}
      tamanho={tamanho}
    />
  );
}

/** As quatro caixas do topo no computador (`InicioDesktop`). */
export function ResumoComputador({ i }: { i: Inicio }) {
  return (
    <section
      aria-label="Resumo do mês"
      className="bg-superficie rounded-bloco grid grid-cols-2 gap-4 p-4 xl:grid-cols-4"
    >
      <Caixa
        rotulo={i.situacao === "corrente" ? "Gasto até hoje" : "Gasto no mês"}
        valor={reais(i.gasto)}
        apoio={textoComparacao(i)}
        tom="nenhum"
        tamanho="grande"
      />
      <CaixaOrcamento i={i} />
      <CaixaFechamento i={i} />
      <Caixa
        rotulo="Receitas do mês"
        valor={<span className="text-receita">{reais(i.receitas, { centavos: false })}</span>}
        apoio={`${i.situacao === "corrente" ? "Sobra até agora" : "Sobra do mês"}: ${reais(i.sobra)}`}
      />
    </section>
  );
}

/** O bloco do topo no celular: gasto grande, meta e previsão, e o gráfico. */
export function ResumoCelular({ i, grafico }: { i: Inicio; grafico: ReactNode }) {
  return (
    <section
      aria-label="Resumo do mês"
      className="bg-superficie rounded-bloco flex flex-col gap-8 p-9"
    >
      <div className="flex flex-col gap-2">
        <span className="text-apoio text-texto-2">
          {i.situacao === "corrente" ? "Gasto até hoje" : "Gasto no mês"}
        </span>
        <span className="text-numero-grande leading-none font-bold tracking-[-1.5px]">
          {reais(i.gasto)}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <CaixaOrcamento i={i} compacta />
        <CaixaFechamento i={i} compacta />
      </div>
      <figure className="m-0 flex flex-col gap-3">
        {grafico}
        <figcaption className="text-pequeno text-texto-2">
          Linha azul: quanto já saiu no mês, somado dia a dia.
        </figcaption>
      </figure>
    </section>
  );
}

/** Atalho para Revisar, com o que está esperando decisão. */
export function CartaoRevisar({ resumo }: { resumo: RevisarResumo | undefined }) {
  const total = resumo?.total ?? 0;
  return (
    <a
      href={href("revisar")}
      className="bg-superficie rounded-bloco text-texto hover:text-texto flex min-h-22 items-center gap-7 px-9 py-8 no-underline md:px-10 md:py-9"
    >
      <span
        className={cn(
          "rounded-interno flex size-22 shrink-0 items-center justify-center text-[20px] font-bold md:size-24 md:text-[22px]",
          total ? "bg-atencao-fundo text-atencao-texto" : "bg-receita-fundo text-receita-texto",
        )}
      >
        {total ? total : <Icone nome="revisar" tamanho={22} />}
      </span>
      <span className="flex flex-1 flex-col gap-1">
        <span className="text-enfase font-forte">
          {total ? "Para revisar" : "Nada para revisar"}
        </span>
        <span className="text-apoio text-texto-2">
          {resumo
            ? total
              ? textoRevisar(resumo)
              : "O que veio limpo dos bancos já entrou sozinho."
            : "Carregando..."}
        </span>
      </span>
      <Icone nome="direita" className="text-texto-2" />
    </a>
  );
}

function textoAviso(aviso: AvisoOrcamento | AvisoReajuste): string {
  if (aviso.tipo === "reajuste") {
    return `${aviso.descricao} subiu de ${reais(aviso.valor_anterior)} para ${reais(aviso.valor_atual)}`;
  }
  const pct = inteiro(aviso.percentual);
  if (aviso.situacao === "estourado") {
    return `${aviso.categoria} passou do orçamento: usou ${pct}% (${reais(aviso.realizado, { centavos: false })} de ${reais(aviso.meta, { centavos: false })})`;
  }
  const faltam =
    aviso.dias_restantes !== null
      ? `, ${aviso.dias_restantes === 1 ? "falta 1 dia" : `faltam ${aviso.dias_restantes} dias`}`
      : "";
  return `${aviso.categoria} usou ${pct}%${faltam}`;
}

/** Avisos das detecções que o relatório mensal já usa: reajuste e orçamento. */
export function Avisos({ avisos, className }: { avisos: Inicio["avisos"]; className?: string }) {
  return (
    <Card className={cn("flex flex-col gap-5 px-9 py-9 md:px-10", className)}>
      <CabecalhoBloco titulo="Avisos" />
      {avisos.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">Nenhum aviso neste mês.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {avisos.map((aviso, indice) => (
            <li
              key={indice}
              className="bg-superficie-2 rounded-interno flex items-start gap-5 p-6 md:flex-col md:gap-3"
            >
              <Selo tom="atencao" className="shrink-0">
                {aviso.tipo === "reajuste" ? "Reajuste" : "Orçamento"}
              </Selo>
              <span className="text-apoio leading-snug">{textoAviso(aviso)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** "Quem gastou": barra empilhada e a linha de cada balde (D-03). */
export function QuemGastou({ i, pessoas }: { i: Inicio; pessoas: Pessoa[] }) {
  const comGasto = i.pessoas.filter((p) => p.percentual > 0);
  return (
    <Card className="flex flex-col gap-7 px-9 py-9 md:px-11 md:py-10">
      <CabecalhoBloco titulo="Quem gastou" />
      {comGasto.length > 0 ? (
        <div
          className="flex h-5 gap-1 overflow-hidden rounded-[6px] md:h-6"
          role="img"
          aria-label={i.pessoas.map((p) => `${p.nome} ${p.percentual}%`).join(", ")}
        >
          {comGasto.map((p) => (
            <div
              key={p.balde}
              style={{ width: `${p.percentual}%`, background: corDaChave(p.balde, pessoas) }}
            />
          ))}
        </div>
      ) : null}
      <ul className="m-0 flex list-none flex-col gap-5 p-0">
        {i.pessoas.map((p) => (
          <li key={p.balde} className="text-corpo flex items-center justify-between">
            <span className="flex items-center gap-4">
              <span
                aria-hidden
                className="inline-block size-5 rounded-[3px]"
                style={{ background: corDaChave(p.balde, pessoas) }}
              />
              {p.nome}
            </span>
            <span>
              <span className="font-forte">{reais(p.valor)}</span>
              <span className="text-texto-2 inline-block w-23 text-right">{p.percentual}%</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** "Por categoria": as maiores do mês, com "Sem categoria" no fim. */
export function PorCategoria({ i, className }: { i: Inicio; className?: string }) {
  return (
    <Card className={cn("flex flex-col gap-6 px-9 py-9 md:px-11 md:py-10", className)}>
      <CabecalhoBloco
        titulo="Por categoria"
        direita={
          <a href={href("analises")} className="text-apoio font-semibold">
            Ver análise
          </a>
        }
      />
      {i.categorias.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">Nenhum gasto neste mês.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-6 p-0">
          {i.categorias.map((c) => (
            <li
              key={c.categoria_id ?? "sem"}
              className="text-corpo flex flex-col gap-3 md:grid md:grid-cols-[170px_minmax(0,1fr)_110px_48px] md:items-center md:gap-7"
            >
              <span className="flex justify-between md:contents">
                <span className="truncate">{c.nome}</span>
                <span className="font-semibold md:order-3 md:text-right">{reais(c.valor)}</span>
              </span>
              <div className="bg-linha-suave h-3 rounded-[3px] md:order-2 md:h-4 md:rounded-[4px]">
                <div
                  className="bg-destaque h-full rounded-[inherit]"
                  style={{ width: `${c.largura}%` }}
                />
              </div>
              <span className="text-apoio text-texto-2 hidden text-right md:order-4 md:block">
                {c.percentual}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
