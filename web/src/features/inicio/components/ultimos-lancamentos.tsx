import { CabecalhoBloco, Card } from "@/components/ui/card";
import { FormaPagamentoTag } from "@/features/cadastros/forma-pagamento-tag";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import type { Transacao } from "@/features/transacoes/types";
import { diaEMes, reaisDoLancamento } from "@/lib/format";
import { href } from "@/lib/rotas";
import { cn } from "@/lib/utils";

function quem(t: Transacao): string {
  return t.pessoa_id === null ? ROTULO_JUNTOS : t.pessoa_nome;
}

function corDoValor(t: Transacao): string {
  if (t.tipo === "receita") return "text-receita";
  if (t.tipo === "transferencia") return "text-texto-2";
  return "text-texto";
}

/**
 * "Últimos lançamentos" do mês, com a forma de pagamento legível (D-22).
 * Tabela no computador, lista no celular — como nas pranchetas.
 */
export function UltimosLancamentos({
  transacoes,
  carregando,
}: {
  transacoes: Transacao[];
  carregando: boolean;
}) {
  return (
    <Card className="flex flex-col px-9 py-9 md:px-11 md:py-10">
      <CabecalhoBloco
        titulo="Últimos lançamentos"
        className="pb-3 md:pb-5"
        direita={
          <a href={href("lancamentos")} className="text-apoio font-semibold">
            Ver todos
          </a>
        }
      />

      {carregando ? (
        <div className="bg-superficie-2 animate-shimmer rounded-interno mt-4 h-60" />
      ) : transacoes.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0 pt-2">Nenhum lançamento neste mês.</p>
      ) : (
        <>
          <ul className="m-0 flex list-none flex-col p-0 md:hidden">
            {transacoes.map((t) => (
              <li
                key={t.id}
                className="linha-acima flex items-center justify-between gap-6 py-5.5"
              >
                <span className="flex min-w-0 flex-col gap-2">
                  <span className="text-corpo font-medio truncate">{t.descricao}</span>
                  <span className="text-pequeno text-texto-2 flex items-center gap-3">
                    <FormaPagamentoTag
                      tipo={t.forma_pagamento_tipo}
                      apelido={t.forma_pagamento_apelido}
                      contaNome={t.forma_pagamento_conta_nome}
                      curto
                    />
                    {quem(t)}
                  </span>
                </span>
                <span className={cn("text-corpo font-forte whitespace-nowrap", corDoValor(t))}>
                  {reaisDoLancamento(t.valor, t.tipo)}
                </span>
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[680px] table-fixed border-collapse">
              <colgroup>
                <col className="w-[84px]" />
                <col />
                <col className="w-[20%]" />
                <col className="w-[220px]" />
                <col className="w-[96px]" />
                <col className="w-[130px]" />
              </colgroup>
              <thead>
                <tr className="linha-abaixo text-pequeno text-texto-2 text-left">
                  <th className="py-4 font-semibold">Data</th>
                  <th className="py-4 font-semibold">Descrição</th>
                  <th className="py-4 font-semibold">Categoria</th>
                  <th className="py-4 font-semibold">Pagamento</th>
                  <th className="py-4 font-semibold">Quem</th>
                  <th className="py-4 text-right font-semibold">Valor</th>
                </tr>
              </thead>
              <tbody>
                {transacoes.map((t) => (
                  <tr key={t.id} className="linha-abaixo-suave text-corpo">
                    <td className="text-texto-2 py-6 pr-4">{diaEMes(t.data)}</td>
                    <td className="font-medio truncate py-6 pr-6">{t.descricao}</td>
                    <td className="text-texto-apoio truncate py-6 pr-6">
                      {t.categoria_nome ?? "Sem categoria"}
                    </td>
                    <td className="py-6 pr-6">
                      <FormaPagamentoTag
                        tipo={t.forma_pagamento_tipo}
                        apelido={t.forma_pagamento_apelido}
                        contaNome={t.forma_pagamento_conta_nome}
                      />
                    </td>
                    <td className="text-texto-apoio truncate py-6 pr-4">{quem(t)}</td>
                    <td className={cn("font-forte py-6 text-right whitespace-nowrap", corDoValor(t))}>
                      {reaisDoLancamento(t.valor, t.tipo)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}
