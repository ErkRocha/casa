import { useState } from "react";

import { CabecalhoBloco, Card } from "@/components/ui/card";
import { Selo } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { COR_FAIXA } from "@/features/inicio/textos";
import { MENOS, reais } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";
import { mesDoAno } from "../textos";
import type { Analises, CategoriaAnalise, LinhaOrcamentoAnalise } from "../types";

const SEM_CENTAVOS = { centavos: false } as const;

/**
 * "Por categoria" (`AnalisesDesktop`): as raízes pela média mensal, cada uma
 * abrindo as subcategorias. A primeira com filhas já vem aberta, como na
 * prancheta.
 */
export function PorCategoria({ a, className }: { a: Analises; className?: string }) {
  const primeira = a.categorias.find((c) => c.subcategorias.length > 0)?.categoria_id;
  const [abertas, setAbertas] = useState<Set<number | null>>(
    () => new Set(primeira !== undefined ? [primeira] : []),
  );

  function alternar(id: number | null) {
    setAbertas((atual) => {
      const proxima = new Set(atual);
      if (proxima.has(id)) proxima.delete(id);
      else proxima.add(id);
      return proxima;
    });
  }

  return (
    <Card className={cn("flex flex-col gap-1 px-8 py-9 md:px-11 md:py-10", className)}>
      <CabecalhoBloco
        titulo="Por categoria"
        direita={a.base_categorias === "media_mensal" ? "média mensal" : "neste mês"}
        className="pb-3"
      />
      {a.categorias.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0 pt-2">Nenhuma despesa no período.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {a.categorias.map((c) => (
            <Raiz
              key={c.categoria_id ?? "sem"}
              c={c}
              aberta={abertas.has(c.categoria_id)}
              onAlternar={() => alternar(c.categoria_id)}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function Raiz({
  c,
  aberta,
  onAlternar,
}: {
  c: CategoriaAnalise;
  aberta: boolean;
  onAlternar: () => void;
}) {
  const temFilhas = c.subcategorias.length > 0;
  const idFilhas = `categoria-${c.categoria_id ?? "sem"}-filhas`;
  const conteudo = (
    <>
      <span className="text-corpo flex items-center gap-4 font-semibold">
        {temFilhas ? (
          <Icone nome={aberta ? "baixo" : "direita"} tamanho={14} espessura={2.2} />
        ) : (
          <span aria-hidden className="w-7" />
        )}
        {c.nome}
      </span>
      <span className="text-corpo font-forte">{reais(c.valor, SEM_CENTAVOS)}</span>
    </>
  );

  return (
    <li className="linha-acima">
      {temFilhas ? (
        <button
          type="button"
          aria-expanded={aberta}
          aria-controls={idFilhas}
          onClick={onAlternar}
          className="text-texto flex min-h-22 w-full cursor-pointer items-center justify-between border-none bg-transparent p-0 text-left"
        >
          {conteudo}
        </button>
      ) : (
        <div className="flex min-h-22 items-center justify-between">{conteudo}</div>
      )}
      {temFilhas && aberta ? (
        <ul id={idFilhas} className="m-0 flex list-none flex-col gap-4 pt-1 pb-5 pl-11">
          {c.subcategorias.map((s) => (
            <li key={s.categoria_id} className="text-apoio text-texto-apoio flex justify-between">
              <span>{s.nome}</span>
              <span>{reais(s.valor, SEM_CENTAVOS)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * "O que mais mudou": o último mês fechado contra a média dos anteriores.
 * Subir gasto é atenção (âmbar); cair, verde.
 */
export function OQueMudou({ a, className }: { a: Analises; className?: string }) {
  const m = a.mudancas;
  const direita = m
    ? m.meses_base === 1
      ? `${mesDoAno(m.referencia)} contra o mês anterior`
      : `${mesDoAno(m.referencia)} contra a média`
    : undefined;

  return (
    <Card className={cn("flex flex-col gap-1 px-8 py-9 md:px-11 md:py-10", className)}>
      <CabecalhoBloco titulo="O que mais mudou" direita={direita} className="pb-3" />
      {!m ? (
        <p className="text-apoio text-texto-2 m-0 pt-2 leading-normal">
          Escolha 3 ou 12 meses para comparar o último mês fechado com a média.
        </p>
      ) : m.linhas.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0 pt-2">Ainda não há meses para comparar.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {m.linhas.map((linha) => (
            <li
              key={linha.categoria_id}
              className="linha-acima text-corpo flex items-center justify-between gap-5 py-5.5 md:grid md:grid-cols-[minmax(0,1fr)_110px_90px] md:gap-6 md:py-6"
            >
              <span className="min-w-0 truncate">{linha.nome}</span>
              <span className="flex items-center gap-5 md:contents">
                <span className="font-semibold md:text-right">
                  {reais(linha.valor, SEM_CENTAVOS)}
                </span>
                <Variacao valor={linha.variacao} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Variacao({ valor }: { valor: number }) {
  const texto = valor > 0 ? `+${valor}%` : valor < 0 ? `${MENOS}${Math.abs(valor)}%` : "igual";
  return (
    <Selo
      tom={valor > 0 ? "atencao" : valor < 0 ? "receita" : "neutro"}
      className="text-selo md:text-pequeno justify-self-end"
    >
      <span className="sr-only">{valor > 0 ? "subiu " : valor < 0 ? "caiu " : ""}</span>
      {texto}
    </Selo>
  );
}

/** "Orçamento de outubro": barras nas faixas do README, calculadas pela API. */
export function OrcamentoDoMes({
  a,
  nomePessoa,
}: {
  a: Analises;
  /** Com pessoa escolhida, o gasto é o dela contra a meta da casa. */
  nomePessoa: string | null;
}) {
  const mes = mesDoAno(a.fim);
  return (
    <Card className="flex flex-col gap-7 px-8 py-9 md:gap-6 md:px-11 md:py-10">
      <div className="flex flex-col gap-1">
        <CabecalhoBloco
          titulo={`Orçamento de ${mes}`}
          direita={
            <a href={href("categorias")} className="text-apoio font-semibold">
              Editar metas
            </a>
          }
        />
        {nomePessoa ? (
          <span className="text-apoio text-texto-2">
            Gasto de {nomePessoa} contra a meta da casa.
          </span>
        ) : null}
      </div>
      {a.orcamento.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">
          Nenhuma meta para {mes}. As metas ficam em Categorias.
        </p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-7 p-0 md:gap-6">
          {a.orcamento.map((o) => (
            <LinhaOrcamento key={o.categoria_id} o={o} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function LinhaOrcamento({ o }: { o: LinhaOrcamentoAnalise }) {
  const valores = (
    <span className="text-apoio md:text-right">
      <span className="font-forte">{reais(o.gasto, SEM_CENTAVOS)}</span>
      <span className="text-texto-2">
        {" "}
        de {reais(o.meta, SEM_CENTAVOS)}
        {o.excesso ? ` (estourou ${reais(o.excesso, SEM_CENTAVOS)})` : ""}
      </span>
    </span>
  );
  return (
    <li className="flex flex-col gap-3 md:grid md:grid-cols-[170px_minmax(0,1fr)_250px] md:items-center md:gap-8">
      <span className="flex items-baseline justify-between gap-4 md:contents">
        <span className="text-corpo">{o.nome}</span>
        <span className="md:hidden">{valores}</span>
      </span>
      <div
        role="meter"
        aria-label={`${o.nome}: ${o.percentual}% da meta`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={o.largura}
        className="bg-linha-suave h-4 overflow-hidden rounded-full md:h-5"
      >
        <div className={cn("h-full rounded-full", COR_FAIXA[o.faixa])} style={{ width: `${o.largura}%` }} />
      </div>
      <span className="hidden md:inline">{valores}</span>
    </li>
  );
}
