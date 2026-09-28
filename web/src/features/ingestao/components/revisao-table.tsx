import { Checkbox, PessoaBadge, Select } from "@/components/ui/controls";
import { useCategoriaOpcoes, usePessoas } from "@/features/cadastros/queries";
import { corDoBalde, corSuaveDoBalde } from "@/features/filters/baldes";
import { formatBRLTexto, formatDate, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAjustarItem } from "../queries";
import { STATUS_ITEM_LABEL, type ItemImportacao, type StatusItem } from "../types";

/**
 * Tabela de revisão do staging.
 *
 * A coluna da linha crua é o ponto da tela: é contra o texto original do PDF
 * que se confere se a leitura está certa. Sem ela, aprovar vira ato de fé.
 *
 * Mudar a categoria aqui grava uma regra — a próxima importação já vem certa
 * (D-09).
 */

const CORES_STATUS: Record<StatusItem, string> = {
  pendente: "text-text-secondary",
  aprovado: "text-income",
  rejeitado: "text-text-tertiary",
  duplicado: "text-accent",
};

export function RevisaoTable({
  itens,
  selecionados,
  onAlternar,
  onAlternarTodos,
}: {
  itens: ItemImportacao[];
  selecionados: Set<number>;
  onAlternar: (id: number) => void;
  onAlternarTodos: () => void;
}) {
  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();
  const ajustar = useAjustarItem();

  const pendentes = itens.filter((item) => item.status === "pendente");
  const todosMarcados =
    pendentes.length > 0 && pendentes.every((item) => selecionados.has(item.id));

  return (
    <div className="px-6">
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col className="w-16" />
          <col className="w-46" />
          <col />
          <col className="w-95" />
          <col className="w-55" />
          {/* Valor e situação precisam de folga entre si: sem o `pr` na
              coluna de valor, "R$ 8,90" encosta em "Pendente". */}
          <col className="w-60" />
          <col className="w-55" />
        </colgroup>

        <thead>
          <tr className="border-border-faint border-b">
            <th className="px-3 py-4">
              <Checkbox
                checked={todosMarcados}
                onChange={onAlternarTodos}
                aria-label="Selecionar todos os itens pendentes"
              />
            </th>
            <Th>Data</Th>
            <Th>Linha do PDF</Th>
            <Th>Categoria</Th>
            <Th>Pessoa</Th>
            <Th alinhamento="right" className="pr-5">
              Valor
            </Th>
            <Th className="pl-5">Situação</Th>
          </tr>
        </thead>

        <tbody>
          {itens.map((item) => {
            const pendente = item.status === "pendente";
            const transferencia = item.tipo_sugerido === "transferencia";
            const receita = item.tipo_sugerido === "receita";
            const confianca = toNumero(item.confianca);

            return (
              <tr
                key={item.id}
                className={cn(
                  "border-border-faint border-b",
                  !pendente && "opacity-60",
                  selecionados.has(item.id) && "bg-surface",
                )}
              >
                <td className="px-3 py-4">
                  <Checkbox
                    checked={selecionados.has(item.id)}
                    disabled={!pendente}
                    onChange={() => onAlternar(item.id)}
                    aria-label={`Selecionar ${item.linha_bruta}`}
                  />
                </td>

                <td className="tabular text-body-sm text-text-secondary py-4">
                  {item.data ? formatDate(item.data) : "—"}
                </td>

                {/* O texto cru do PDF: é contra ele que se confere. */}
                <td className="py-4 pr-4">
                  <div className="text-body-sm text-text-primary truncate font-mono">
                    {item.linha_bruta}
                  </div>
                  {confianca < 0.8 ? (
                    <div className="text-caption text-text-tertiary mt-1">
                      confiança {Math.round(confianca * 100)}% · sugestão por{" "}
                      {item.origem_sugestao ?? "parser"}
                    </div>
                  ) : null}
                </td>

                <td className="py-4 pr-4">
                  <Select
                    className="w-full"
                    disabled={!pendente || transferencia}
                    value={item.categoria_sugerida_id ?? ""}
                    onChange={(e) =>
                      ajustar.mutate({
                        id: item.id,
                        patch: {
                          categoria_sugerida_id:
                            e.target.value === "" ? null : Number(e.target.value),
                        },
                      })
                    }
                  >
                    <option value="">— sem categoria —</option>
                    {categorias.map((opcao) => (
                      <option key={opcao.id} value={opcao.id}>
                        {opcao.label}
                      </option>
                    ))}
                  </Select>
                </td>

                <td className="py-4 pr-4">
                  {pendente ? (
                    <Select
                      className="w-full"
                      value={item.pessoa_sugerida_id ?? "conjunto"}
                      onChange={(e) =>
                        ajustar.mutate({
                          id: item.id,
                          patch: {
                            pessoa_sugerida_id:
                              e.target.value === "conjunto" ? null : Number(e.target.value),
                          },
                        })
                      }
                    >
                      {pessoas.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome}
                        </option>
                      ))}
                      <option value="conjunto">Conjunto</option>
                    </Select>
                  ) : (
                    <PessoaBadge
                      nome={
                        pessoas.find((p) => p.id === item.pessoa_sugerida_id)?.nome ??
                        "Conjunto"
                      }
                      fundo={corSuaveDoBalde(item.pessoa_sugerida_id ?? "conjunto", pessoas)}
                      cor={corDoBalde(item.pessoa_sugerida_id ?? "conjunto", pessoas)}
                    />
                  )}
                </td>

                <td
                  className={cn(
                    "tabular py-4 pr-5 text-right font-bold whitespace-nowrap",
                    transferencia
                      ? "text-text-tertiary"
                      : receita
                        ? "text-income"
                        : "text-expense",
                  )}
                >
                  {transferencia ? "↔ " : receita ? "↑ " : "↓ "}
                  {formatBRLTexto(item.valor)}
                </td>

                <td className={cn("text-body-sm py-4 pl-5", CORES_STATUS[item.status])}>
                  {STATUS_ITEM_LABEL[item.status]}
                  {transferencia && pendente ? (
                    <div
                      className="text-caption text-text-tertiary mt-1"
                      title="Pagar fatura não é despesa nova (D-05)"
                    >
                      transferência
                    </div>
                  ) : null}
                  {item.motivo_rejeicao ? (
                    <div className="text-caption text-text-tertiary mt-1 truncate">
                      {item.motivo_rejeicao}
                    </div>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  alinhamento = "left",
  className,
}: {
  children: React.ReactNode;
  alinhamento?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "text-label text-text-tertiary tracking-caps-wide py-4 font-semibold uppercase",
        alinhamento === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}
