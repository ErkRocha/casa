import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/controls";
import type { GrupoDeCategoria } from "@/features/cadastros/queries";
import { FormaPagamentoTag } from "@/features/cadastros/forma-pagamento-tag";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import { diaDaSemanaEMes, reais, reaisDoLancamento, sinal } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TotalDia, Transacao } from "../types";
import { CategoriaInline } from "./categoria-inline";

interface Dia {
  data: string;
  itens: Transacao[];
}

/** Agrupa na ordem da API (data mais recente primeiro). */
function porDia(transacoes: Transacao[]): Dia[] {
  const dias: Dia[] = [];
  for (const t of transacoes) {
    const ultimo = dias[dias.length - 1];
    if (ultimo && ultimo.data === t.data) ultimo.itens.push(t);
    else dias.push({ data: t.data, itens: [t] });
  }
  return dias;
}

/**
 * "R$ 818,00 em despesas", ou "+ R$ 320,00" no celular. O total vem de
 * `/transacoes/dias`, somado no banco: com paginação, o dia pode estar só em
 * parte na tela.
 */
function totalDoDia(dia: TotalDia | undefined, curto: boolean): string {
  if (!dia) return "";
  const despesas = sinal(dia.despesas) !== 0;
  const receitas = sinal(dia.receitas) !== 0;
  if (curto) {
    if (despesas) return reais(dia.despesas);
    return receitas ? `+ ${reais(dia.receitas)}` : "";
  }
  const partes = [
    despesas ? `${reais(dia.despesas)} em despesas` : null,
    receitas ? `${reais(dia.receitas)} em receitas` : null,
  ].filter(Boolean);
  return partes.length > 0 ? partes.join(", ") : "Só transferências";
}

function quem(t: Transacao): string {
  return t.pessoa_id === null ? ROTULO_JUNTOS : t.pessoa_nome;
}

function corDoValor(t: Transacao): string {
  if (t.tipo === "receita") return "text-receita";
  if (t.tipo === "transferencia") return "text-texto-2";
  return "text-texto";
}

/**
 * Os lançamentos agrupados por dia, com o total de cada dia
 * (`LancamentosDesktop`, `LancamentosCelular`). No computador, uma tabela com
 * seleção múltipla; no celular, um bloco por dia.
 */
export function ListaPorDia({
  transacoes,
  totais,
  grupos,
  selecionadas,
  onAlternar,
  onAlternarTodas,
  onAbrir,
  onCategoria,
}: {
  transacoes: Transacao[];
  totais: Map<string, TotalDia>;
  grupos: GrupoDeCategoria[];
  selecionadas: Set<number>;
  onAlternar: (id: number) => void;
  onAlternarTodas: () => void;
  onAbrir: (t: Transacao) => void;
  onCategoria: (t: Transacao, categoriaId: number | null) => void;
}) {
  const dias = porDia(transacoes);
  const todas = transacoes.length > 0 && transacoes.every((t) => selecionadas.has(t.id));

  return (
    <>
      {/* Celular: um bloco por dia. */}
      <div className="flex flex-col gap-6 md:hidden">
        {dias.map((dia) => (
          <Card key={dia.data} className="px-8 pt-3 pb-4">
            <div className="flex items-baseline justify-between gap-5 pt-3 pb-3">
              <h2 className="text-corpo font-forte m-0">{diaDaSemanaEMes(dia.data)}</h2>
              <span className="text-pequeno text-texto-2">
                {totalDoDia(totais.get(dia.data), true)}
              </span>
            </div>
            <ul className="m-0 flex list-none flex-col p-0">
              {dia.itens.map((t) => (
                <li
                  key={t.id}
                  className="linha-acima flex items-center justify-between gap-6 py-5.5"
                >
                  <div className="flex min-w-0 flex-col gap-2.5">
                    <button
                      type="button"
                      onClick={() => onAbrir(t)}
                      className="text-corpo font-medio text-texto cursor-pointer truncate border-none bg-transparent p-0 text-left"
                    >
                      {t.descricao}
                    </button>
                    <span className="text-selo flex flex-wrap items-center gap-3">
                      <CategoriaInline
                        key={`${t.id}-${t.categoria_id}`}
                        transacao={t}
                        grupos={grupos}
                        onMudar={(id) => onCategoria(t, id)}
                        compacta
                      />
                      <FormaPagamentoTag
                        tipo={t.forma_pagamento_tipo}
                        apelido={t.forma_pagamento_apelido}
                        contaNome={t.forma_pagamento_conta_nome}
                        curto
                        className="text-selo"
                      />
                      <span className="text-texto-2">{quem(t)}</span>
                    </span>
                  </div>
                  <span
                    className={cn("text-corpo font-forte whitespace-nowrap", corDoValor(t))}
                  >
                    {reaisDoLancamento(t.valor, t.tipo)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      {/* Computador: tabela, com o dia como grupo de linhas. */}
      <Card className="hidden px-11 pt-3 pb-8 md:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] table-fixed border-collapse">
            <colgroup>
              <col className="w-[46px]" />
              <col />
              <col className="w-[24%]" />
              <col className="w-[196px]" />
              <col className="w-[110px]" />
              <col className="w-[124px]" />
            </colgroup>
            <thead>
              <tr className="linha-abaixo text-pequeno text-texto-2 text-left">
                <th className="py-1 font-semibold">
                  <label className="flex size-22 cursor-pointer items-center justify-center">
                    <Checkbox
                      checked={todas}
                      onChange={onAlternarTodas}
                      aria-label="Selecionar todos os lançamentos carregados"
                    />
                  </label>
                </th>
                <th className="py-6 pr-7 font-semibold">Descrição</th>
                <th className="py-6 pr-7 font-semibold">Categoria</th>
                <th className="py-6 pr-7 font-semibold">Pagamento</th>
                <th className="py-6 pr-7 font-semibold">Quem</th>
                <th className="py-6 text-right font-semibold">Valor</th>
              </tr>
            </thead>
            {dias.map((dia) => (
              <tbody key={dia.data}>
                <tr>
                  <th colSpan={6} scope="colgroup" className="text-apoio pt-8 pb-4 text-left font-normal">
                    <span className="flex justify-between gap-6">
                      <span className="font-forte">{diaDaSemanaEMes(dia.data)}</span>
                      <span className="text-texto-2">
                        {totalDoDia(totais.get(dia.data), false)}
                      </span>
                    </span>
                  </th>
                </tr>
                {dia.itens.map((t) => {
                  const marcada = selecionadas.has(t.id);
                  return (
                    <tr
                      key={t.id}
                      className={cn("linha-acima text-corpo", marcada && "bg-selecao")}
                    >
                      <td className="py-1">
                        <label className="flex size-22 cursor-pointer items-center justify-center">
                          <Checkbox
                            checked={marcada}
                            onChange={() => onAlternar(t.id)}
                            aria-label={`Selecionar ${t.descricao}`}
                          />
                        </label>
                      </td>
                      <td className="py-5 pr-7">
                        <span className="flex min-w-0 flex-col gap-1">
                          <button
                            type="button"
                            onClick={() => onAbrir(t)}
                            className="font-medio text-texto cursor-pointer truncate border-none bg-transparent p-0 text-left hover:underline"
                          >
                            {t.descricao}
                          </button>
                          {t.descricao_original ? (
                            <span className="text-pequeno text-texto-2 truncate">
                              {t.descricao_original}
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td className="py-5 pr-7">
                        <CategoriaInline
                          key={`${t.id}-${t.categoria_id}`}
                          transacao={t}
                          grupos={grupos}
                          onMudar={(id) => onCategoria(t, id)}
                        />
                      </td>
                      <td className="py-5 pr-7">
                        <FormaPagamentoTag
                          tipo={t.forma_pagamento_tipo}
                          apelido={t.forma_pagamento_apelido}
                          contaNome={t.forma_pagamento_conta_nome}
                        />
                      </td>
                      <td className="text-texto-apoio truncate py-5 pr-7">{quem(t)}</td>
                      <td
                        className={cn(
                          "font-forte py-5 text-right whitespace-nowrap",
                          corDoValor(t),
                        )}
                      >
                        {reaisDoLancamento(t.valor, t.tipo)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
        </div>
      </Card>
    </>
  );
}
