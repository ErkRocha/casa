import { reais, toNumero } from "@/lib/format";
import { nomeCurtoCartao } from "../textos";
import type { FaturaMes, PontoAcumulado, SituacaoMes } from "../types";

/**
 * "O que saiu da conta no mês" (`InicioDesktop` / `InicioCelular`, D-24).
 *
 * A curva cheia é o que já saiu da conta, em degraus (a fatura sobe de uma vez
 * no dia); o tracejado inclui as faturas a pagar; a linha guia é o orçamento. Os valores viram número só aqui, para virar
 * coordenada no SVG — nada é somado no navegador.
 */

const GEOMETRIA = {
  computador: { largura: 700, altura: 230, base: 200, topo: 22, eixo: 222, fonte: 13, area: true },
  celular: { largura: 354, altura: 170, base: 150, topo: 18, eixo: 166, fonte: 12, area: false },
} as const;

export function GraficoAcumulado({
  serie,
  faturas,
  diasNoMes,
  diaReferencia,
  orcamento,
  situacao,
  variante,
}: {
  serie: PontoAcumulado[];
  faturas: FaturaMes[];
  diasNoMes: number;
  diaReferencia: number;
  orcamento: string | null;
  situacao: SituacaoMes;
  variante: keyof typeof GEOMETRIA;
}) {
  const g = GEOMETRIA[variante];
  const realizada = serie.filter((p) => p.dia <= diaReferencia);
  const ultimo = realizada.at(-1)?.acumulado ?? "0";
  const meta = orcamento ? toNumero(orcamento) : 0;
  const maiorComAPagar = Math.max(0, ...serie.map((p) => toNumero(p.com_a_pagar)));
  const escala = Math.max(meta, maiorComAPagar, toNumero(ultimo), 1);
  const y = (valor: number) => g.base - (valor / escala) * (g.base - g.topo);
  const x = (dia: number) => (dia / diasNoMes) * g.largura;
  const par = (px: number, py: number) => `${px.toFixed(1)},${py.toFixed(1)}`;

  // Desenho em degraus: segue horizontal no valor anterior e sobe no dia.
  const degraus = (pontos: Array<[number, number]>, inicio: [number, number]) => {
    const saida = [par(...inicio)];
    let anterior = inicio[1];
    for (const [dia, valor] of pontos) {
      saida.push(par(x(dia), anterior), par(x(dia), y(valor)));
      anterior = y(valor);
    }
    return saida.join(" ");
  };

  const curva = degraus(
    realizada.map((p) => [p.dia, toNumero(p.acumulado)]),
    [0, g.base],
  );
  const hojeX = x(realizada.at(-1)?.dia ?? 0);
  const hojeY = y(toNumero(ultimo));
  const area = `${curva} ${hojeX.toFixed(1)},${g.base}`;
  const linhaOrcamento = meta > 0 ? y(meta) : null;

  // Tracejado: de onde `com_a_pagar` passa de `acumulado` até o fim do mês.
  const primeiraDiferenca = serie.findIndex(
    (p) => toNumero(p.com_a_pagar) > toNumero(p.acumulado),
  );
  let tracejado: string | null = null;
  if (primeiraDiferenca >= 0) {
    const anterior = serie[primeiraDiferenca - 1];
    const inicioY = anterior ? y(toNumero(anterior.com_a_pagar)) : g.base;
    tracejado = degraus(
      serie.slice(primeiraDiferenca).map((p) => [p.dia, toNumero(p.com_a_pagar)]),
      [x(anterior?.dia ?? 0), inicioY],
    );
  }

  const aPagar = faturas
    .filter((f) => f.situacao === "a_pagar")
    .map((f) => {
      const ponto = serie.find((p) => p.dia === f.dia);
      const cx = x(f.dia);
      const nome = nomeCurtoCartao(f.cartao);
      return {
        chave: f.forma_pagamento_id,
        cx,
        cy: ponto ? y(toNumero(ponto.com_a_pagar)) : g.topo,
        texto:
          variante === "celular"
            ? `Fatura ${nome}, dia ${f.dia}`
            : `Fatura ${nome}, vence dia ${f.dia}`,
      };
    });
  const pagas = faturas.filter((f) => f.situacao === "paga");

  // O rótulo do ponto vai para a esquerda quando encostaria na borda.
  const rotuloADireita = hojeX < g.largura * 0.78;
  const rotulo =
    variante === "celular"
      ? situacao === "corrente"
        ? "Hoje"
        : "Fim"
      : `${situacao === "corrente" ? "Hoje" : "Fechou"}: ${reais(ultimo, { centavos: false })}`;
  const mostrarDiaDoMeio =
    serie.length > 0 && diaReferencia > 2 && diaReferencia < diasNoMes - 2;

  // Caixas aproximadas dos textos, para os rótulos de fatura não se sobreporem.
  type Caixa = { x1: number; x2: number; y1: number; y2: number };
  const caixaDoTexto = (
    px: number,
    py: number,
    ancora: "start" | "end",
    texto: string,
    fonte: number,
  ): Caixa => {
    const largura = texto.length * fonte * 0.56;
    return {
      x1: ancora === "start" ? px : px - largura,
      x2: ancora === "start" ? px + largura : px,
      y1: py - fonte,
      y2: py + 3,
    };
  };
  const bate = (a: Caixa, b: Caixa) => a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
  const fonteHoje = variante === "computador" ? 14 : 12;
  const ocupadas: Caixa[] =
    realizada.length > 0
      ? [
          caixaDoTexto(
            rotuloADireita ? hojeX + 14 : hojeX - 14,
            hojeY + 5,
            rotuloADireita ? "start" : "end",
            rotulo,
            fonteHoje,
          ),
        ]
      : [];
  const rotulosFatura = aPagar.map((f) => {
    const fonte = g.fonte - 1;
    const aDireita = f.cx + 4 + f.texto.length * fonte * 0.56 <= g.largura;
    const ancora = aDireita ? ("start" as const) : ("end" as const);
    const px = aDireita ? f.cx + 4 : f.cx - 4;
    let py = f.cy - 6;
    let caixa = caixaDoTexto(px, py, ancora, f.texto, fonte);
    for (let n = 0; n < 8 && ocupadas.some((o) => bate(o, caixa)); n++) {
      py -= 14;
      caixa = caixaDoTexto(px, py, ancora, f.texto, fonte);
    }
    ocupadas.push(caixa);
    return { chave: f.chave, x: px, y: py, ancora, fonte, texto: f.texto };
  });

  const descricao =
    `Saiu da conta até o dia ${diaReferencia}: ${reais(ultimo)}` +
    (orcamento ? `, comparado ao orçamento de ${reais(orcamento, { centavos: false })}` : "") +
    (aPagar.length ? `. Faturas a pagar: ${aPagar.map((f) => f.texto).join("; ")}` : "") +
    (pagas.length
      ? `. Faturas pagas: ${pagas.map((f) => `${nomeCurtoCartao(f.cartao)}, dia ${f.dia}`).join("; ")}`
      : "");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${g.largura} ${g.altura}`}
      role="img"
      aria-label={descricao}
      className="block overflow-visible"
    >
      <line x1="0" y1={g.base} x2={g.largura} y2={g.base} className="stroke-linha" strokeWidth="1" />
      {variante === "computador" ? (
        <line
          x1="0"
          y1={(g.base + g.topo) / 2}
          x2={g.largura}
          y2={(g.base + g.topo) / 2}
          className="stroke-linha-suave"
          strokeWidth="1"
        />
      ) : null}
      {linhaOrcamento !== null ? (
        <>
          <line
            x1="0"
            y1={linhaOrcamento}
            x2={g.largura}
            y2={linhaOrcamento}
            className="stroke-guia"
            strokeWidth="1.5"
            strokeDasharray={variante === "computador" ? "6 6" : "5 5"}
          />
          <text
            x={g.largura}
            y={linhaOrcamento - 8}
            textAnchor="end"
            fontSize={g.fonte}
            className="fill-texto-2"
          >
            Orçamento {reais(orcamento, { centavos: false })}
          </text>
        </>
      ) : null}

      {tracejado ? (
        <polyline
          points={tracejado}
          fill="none"
          className="stroke-destaque"
          strokeWidth={variante === "computador" ? 2.5 : 2}
          strokeDasharray={variante === "computador" ? "6 6" : "5 5"}
          strokeLinejoin="round"
        />
      ) : null}
      {rotulosFatura.map((r) => (
        <text
          key={r.chave}
          x={r.x}
          y={r.y}
          textAnchor={r.ancora}
          fontSize={r.fonte}
          className="fill-texto-2 stroke-superficie"
          strokeWidth="3"
          strokeLinejoin="round"
          style={{ paintOrder: "stroke" }}
        >
          {r.texto}
        </text>
      ))}

      {realizada.length > 0 ? (
        <>
          {g.area ? <polyline points={area} className="fill-destaque-fundo" stroke="none" /> : null}
          <polyline
            points={curva}
            fill="none"
            className="stroke-destaque"
            strokeWidth={variante === "computador" ? 3.5 : 3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle
            cx={hojeX}
            cy={hojeY}
            r={variante === "computador" ? 7 : 6}
            className="fill-destaque stroke-superficie"
            strokeWidth="3"
          />
          <text
            x={rotuloADireita ? hojeX + 14 : hojeX - 14}
            y={hojeY + 5}
            textAnchor={rotuloADireita ? "start" : "end"}
            fontSize={variante === "computador" ? 14 : 12}
            fontWeight={variante === "computador" ? 650 : 600}
            className="fill-texto stroke-superficie"
            strokeWidth="3"
            strokeLinejoin="round"
            style={{ paintOrder: "stroke" }}
          >
            {rotulo}
          </text>
        </>
      ) : null}

      <text x="0" y={g.eixo} fontSize={g.fonte - 1} className="fill-texto-2">
        dia 1
      </text>
      {mostrarDiaDoMeio ? (
        <text x={hojeX} y={g.eixo} textAnchor="middle" fontSize={g.fonte - 1} className="fill-texto-2">
          dia {diaReferencia}
        </text>
      ) : null}
      <text x={g.largura} y={g.eixo} textAnchor="end" fontSize={g.fonte - 1} className="fill-texto-2">
        dia {diasNoMes}
      </text>
    </svg>
  );
}
