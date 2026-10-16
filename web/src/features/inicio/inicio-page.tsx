import { useState } from "react";

import { Card } from "@/components/ui/card";
import { BotaoIcone, Button } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { usePessoas } from "@/features/cadastros/queries";
import { useRevisarResumo } from "@/features/revisar/queries";
import { ApiError } from "@/lib/api";
import { competenciaDe, mesPorExtenso, somarMeses } from "@/lib/format";
import { href } from "@/lib/rotas";
import {
  Avisos,
  CartaoRevisar,
  PorCategoria,
  QuemGastou,
  ResumoCelular,
  ResumoComputador,
} from "./components/blocos";
import { GraficoAcumulado } from "./components/grafico-acumulado";
import { UltimosLancamentos } from "./components/ultimos-lancamentos";
import { useInicio, useUltimosLancamentos } from "./queries";
import type { Inicio } from "./types";

/**
 * Início (`InicioDesktop`, `InicioCelular`; D-22): o mês num relance.
 *
 * Todo número vem de `/analytics/inicio`, somado no banco. A tela escolhe o
 * mês, formata e desenha.
 */
export function InicioPage() {
  const mesAtual = competenciaDe(new Date());
  const [competencia, setCompetencia] = useState(mesAtual);
  const inicio = useInicio(competencia);
  const ultimos = useUltimosLancamentos(competencia);
  const revisar = useRevisarResumo();
  const { data: pessoas = [] } = usePessoas();

  return (
    <div className="flex max-w-[1100px] flex-col gap-7 md:gap-8">
      <header className="flex items-center gap-5 pb-1 md:pb-2">
        <BotaoIcone
          rotulo="Mês anterior"
          onClick={() => setCompetencia(somarMeses(competencia, -1))}
          className="md:order-2"
        >
          <Icone nome="esquerda" />
        </BotaoIcone>
        <h1 className="font-forte md:text-pagina m-0 flex-1 text-center text-[18px] md:order-1 md:text-left md:font-bold md:tracking-[-0.4px]">
          {mesPorExtenso(competencia)}
        </h1>
        <BotaoIcone
          rotulo="Próximo mês"
          onClick={() => setCompetencia(somarMeses(competencia, 1))}
          className="md:order-3"
        >
          <Icone nome="direita" />
        </BotaoIcone>
      </header>

      {inicio.isLoading ? (
        <Carregando />
      ) : inicio.isError || !inicio.data ? (
        <Falha erro={inicio.error} onTentar={() => void inicio.refetch()} />
      ) : inicio.data.situacao === "futuro" ? (
        <Vazio
          titulo={`${mesPorExtenso(competencia)} ainda não começou`}
          texto="Os números aparecem quando o mês chegar e os bancos mandarem os primeiros lançamentos."
          onVoltar={() => setCompetencia(mesAtual)}
        />
      ) : !inicio.data.tem_dados ? (
        <Vazio
          titulo={`Nenhum lançamento em ${mesPorExtenso(competencia).toLowerCase()}`}
          texto="Se este mês deveria ter dados, confira se a sincronização com os bancos está em dia."
          link={{ rotulo: "Ver a sincronização", destino: href("sincronizacao") }}
          onVoltar={competencia === mesAtual ? undefined : () => setCompetencia(mesAtual)}
        />
      ) : (
        <Conteudo
          i={inicio.data}
          pessoas={pessoas}
          revisar={revisar.data}
          ultimos={ultimos.data?.items ?? []}
          carregandoUltimos={ultimos.isLoading}
        />
      )}
    </div>
  );
}

function Conteudo({
  i,
  pessoas,
  revisar,
  ultimos,
  carregandoUltimos,
}: {
  i: Inicio;
  pessoas: Parameters<typeof QuemGastou>[0]["pessoas"];
  revisar: Parameters<typeof CartaoRevisar>[0]["resumo"];
  ultimos: Parameters<typeof UltimosLancamentos>[0]["transacoes"];
  carregandoUltimos: boolean;
}) {
  const grafico = (variante: "computador" | "celular") => (
    <GraficoAcumulado
      serie={i.serie}
      diasNoMes={i.dias_no_mes}
      diaReferencia={i.dia_referencia}
      orcamento={i.orcamento?.total ?? null}
      situacao={i.situacao}
      variante={variante}
    />
  );

  return (
    <>
      {/* Celular: um bloco com o gasto, a meta, a previsão e o gráfico. */}
      <div className="flex flex-col gap-7 md:hidden">
        <ResumoCelular i={i} grafico={grafico("celular")} />
        <CartaoRevisar resumo={revisar} />
        <QuemGastou i={i} pessoas={pessoas} />
        <PorCategoria i={i} />
        <Avisos avisos={i.avisos} />
      </div>

      {/* Computador. */}
      <div className="hidden flex-col gap-8 md:flex">
        <ResumoComputador i={i} />
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <Card className="flex flex-col gap-6 px-11 py-10 lg:col-span-2">
            <div className="flex items-baseline justify-between">
              <h2 className="text-bloco font-forte m-0">Gasto acumulado no mês</h2>
              <span className="text-apoio text-texto-2">
                dia {i.dia_referencia} de {i.dias_no_mes}
              </span>
            </div>
            {grafico("computador")}
          </Card>
          <div className="flex flex-col gap-8">
            <CartaoRevisar resumo={revisar} />
            <Avisos avisos={i.avisos} className="flex-1" />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <QuemGastou i={i} pessoas={pessoas} />
          <PorCategoria i={i} className="lg:col-span-2" />
        </div>
      </div>

      <UltimosLancamentos transacoes={ultimos} carregando={carregandoUltimos} />
    </>
  );
}

function Carregando() {
  return (
    <div aria-busy="true" aria-label="Carregando o mês" className="flex flex-col gap-8">
      <div className="bg-superficie rounded-bloco animate-shimmer h-60" />
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="bg-superficie rounded-bloco animate-shimmer h-120 lg:col-span-2" />
        <div className="bg-superficie rounded-bloco animate-shimmer h-120" />
      </div>
    </div>
  );
}

function Falha({ erro, onTentar }: { erro: unknown; onTentar: () => void }) {
  return (
    <Card role="alert" className="flex flex-col items-start gap-5 px-11 py-10">
      <h2 className="text-bloco font-forte m-0">Não foi possível carregar o mês</h2>
      <p className="text-apoio text-texto-2 m-0">
        {erro instanceof ApiError ? erro.detail : "A API não respondeu. Confira se ela está no ar."}
      </p>
      <Button onClick={onTentar}>Tentar de novo</Button>
    </Card>
  );
}

function Vazio({
  titulo,
  texto,
  link,
  onVoltar,
}: {
  titulo: string;
  texto: string;
  link?: { rotulo: string; destino: string };
  onVoltar?: () => void;
}) {
  return (
    <Card className="flex flex-col items-start gap-5 px-11 py-12">
      <h2 className="text-bloco font-forte m-0">{titulo}</h2>
      <p className="text-corpo text-texto-2 m-0 max-w-[560px] leading-normal">{texto}</p>
      <div className="flex flex-wrap items-center gap-6">
        {onVoltar ? <Button onClick={onVoltar}>Voltar para o mês atual</Button> : null}
        {link ? (
          <a href={link.destino} className="text-apoio font-semibold">
            {link.rotulo}
          </a>
        ) : null}
      </div>
    </Card>
  );
}
