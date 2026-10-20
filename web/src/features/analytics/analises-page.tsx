import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Carregando, Falha } from "@/components/ui/estados";
import { Segmentado } from "@/components/ui/segmentado";
import { usePessoas } from "@/features/cadastros/queries";
import { ROTULO_JUNTOS, rotuloDoBalde } from "@/features/filters/baldes";
import type { BaldePessoa } from "@/features/filters/types";
import { reais } from "@/lib/format";
import { OQueMudou, OrcamentoDoMes, PorCategoria } from "./components/blocos";
import { GraficoMeses } from "./components/grafico-meses";
import { useAnalises } from "./queries";
import { mesAbreviado, mesDoAno } from "./textos";
import type { Analises, Periodo } from "./types";

const PERIODOS: Array<{ id: Periodo; rotulo: string }> = [
  { id: "mes", rotulo: "Este mês" },
  { id: "3m", rotulo: "3 meses" },
  { id: "12m", rotulo: "12 meses" },
];

/** Chave do seletor de pessoa: o balde, ou `todos`. */
type Quem = "todos" | "conjunto" | number;

/**
 * Análises (`AnalisesDesktop`, `AnalisesCelular`; D-22): o período e a pessoa
 * valem para a tela inteira. Tudo vem de `/analytics/analises`, somado no
 * banco; a tela escolhe, formata e desenha.
 */
export function AnalisesPage() {
  const [periodo, setPeriodo] = useState<Periodo>("12m");
  const [quem, setQuem] = useState<Quem>("todos");
  const { data: pessoas = [] } = usePessoas();
  const balde: BaldePessoa | null = quem === "todos" ? null : quem;
  const analises = useAnalises(periodo, balde);

  const opcoesQuem: Array<{ id: Quem; rotulo: string }> = [
    { id: "todos", rotulo: "Todos" },
    ...pessoas.map((p) => ({ id: p.id as Quem, rotulo: p.nome })),
    { id: "conjunto", rotulo: ROTULO_JUNTOS },
  ];

  return (
    <div className="flex max-w-[1100px] flex-col gap-7 md:gap-8">
      <header className="flex flex-col gap-6 md:flex-row md:flex-wrap md:items-center">
        <h1 className="text-pagina-celular md:text-pagina m-0 flex-1 font-bold tracking-[-0.4px]">
          Análises
        </h1>
        <Segmentado
          rotulo="Período"
          opcoes={PERIODOS}
          atual={periodo}
          onMudar={setPeriodo}
          cheio
          className="md:flex"
        />
        <Segmentado
          rotulo="Pessoa"
          opcoes={opcoesQuem}
          atual={quem}
          onMudar={setQuem}
          tom="destaque"
          cheio
          className="md:flex"
        />
      </header>

      {analises.isLoading ? (
        <Carregando rotulo="Carregando as análises" alturas={["h-160", "h-120"]} />
      ) : analises.isError || !analises.data ? (
        <Falha
          titulo="Não foi possível carregar as análises"
          erro={analises.error}
          onTentar={() => void analises.refetch()}
        />
      ) : (
        <Conteudo a={analises.data} nomePessoa={balde === null ? null : rotuloDoBalde(balde, pessoas)} />
      )}
    </div>
  );
}

function Conteudo({ a, nomePessoa }: { a: Analises; nomePessoa: string | null }) {
  const corrente = a.meses.find((m) => m.em_curso);
  const nota = corrente
    ? `${mesDoAno(corrente.competencia).replace(/^./, (l) => l.toUpperCase())} está em andamento: a barra mostra o gasto até o dia ${a.dia_referencia}.`
    : null;

  return (
    <>
      {/* Computador: receitas e despesas. */}
      <Card className="hidden flex-col gap-6 px-11 py-10 md:flex">
        <div className="flex flex-wrap items-baseline justify-between gap-5">
          <h2 className="text-bloco font-forte m-0">Receitas e despesas por mês</h2>
          <span className="text-apoio text-texto-2 flex gap-8" aria-hidden>
            <span className="flex items-center gap-3">
              <span className="bg-destaque inline-block size-5 rounded-[3px]" />
              Despesas
            </span>
            <span className="flex items-center gap-3">
              <span className="bg-receita-barra inline-block size-5 rounded-[3px]" />
              Receitas
            </span>
          </span>
        </div>
        <GraficoMeses meses={a.meses} variante="computador" />
        {nota ? <p className="text-apoio text-texto-2 m-0">{nota}</p> : null}
      </Card>

      {/* Celular: o gasto por mês e dois números. */}
      <Card className="flex flex-col gap-6 px-8 py-9 md:hidden">
        <h2 className="text-bloco-celular font-forte m-0">Gasto por mês</h2>
        <GraficoMeses meses={a.meses} variante="celular" />
        <div className="grid grid-cols-2 gap-4">
          {a.media_mensal !== null ? (
            <Numero rotulo="Média mensal" valor={reais(a.media_mensal, { centavos: false })} />
          ) : (
            <Numero
              rotulo="Gasto até hoje"
              valor={reais(corrente?.despesas ?? "0", { centavos: false })}
            />
          )}
          {a.mes_mais_caro ? (
            <Numero
              rotulo="Mês mais caro"
              valor={`${mesAbreviado(a.mes_mais_caro.competencia)}, ${reais(a.mes_mais_caro.despesas, { centavos: false })}`}
            />
          ) : (
            <Numero rotulo="Mês mais caro" valor="—" />
          )}
        </div>
        {nota ? <p className="text-pequeno text-texto-2 m-0">{nota}</p> : null}
      </Card>

      <div className="grid grid-cols-1 gap-7 md:gap-8 lg:grid-cols-2">
        <PorCategoria key={`${a.periodo}`} a={a} />
        <OQueMudou a={a} />
      </div>

      <OrcamentoDoMes a={a} nomePessoa={nomePessoa} />
    </>
  );
}

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="bg-superficie-2 rounded-interno flex flex-col gap-1 px-6 py-5">
      <span className="text-selo text-texto-2">{rotulo}</span>
      <span className="text-bloco-celular font-forte">{valor}</span>
    </div>
  );
}
