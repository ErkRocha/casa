import { corDaCategoria } from "@/features/filters/baldes";
import { formatBRLTexto, toNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ComposicaoCategoria } from "../types";

/**
 * Composição do gasto por categoria, com um nível de drill-down.
 *
 * É uma tabela de magnitude com barra embutida, não um plot — cada linha já
 * carrega rótulo, valor e percentual em texto, então a cor é reforço e não o
 * canal de leitura. Por isso HTML, e não SVG.
 *
 * A cor vem de `categorias.cor` no banco, amarrada ao id da categoria. Não é
 * derivada da posição no ranking: filtrar reordena as barras, mas nenhuma
 * categoria troca de cor.
 */
export function CategoryCompositionChart({
  data,
  onDrillDown,
  onClearDrill,
}: {
  data: ComposicaoCategoria;
  onDrillDown: (categoriaId: number) => void;
  onClearDrill: () => void;
}) {
  const { categoria_pai: pai, linhas } = data;
  const emDrill = pai !== null;

  if (linhas.length === 0) {
    return (
      <p className="text-body-sm text-text-tertiary py-8">
        Nenhum gasto no período — ajuste os filtros.
      </p>
    );
  }

  /* A barra é relativa à maior linha, não ao total: comparar categorias entre
     si é o que a tela responde. O percentual sobre o total vai em texto. */
  const maior = linhas.reduce((max, linha) => Math.max(max, toNumero(linha.valor)), 0) || 1;

  return (
    <div>
      {emDrill ? (
        <nav className="text-body-sm mb-5" aria-label="Trilha de categorias">
          <button
            type="button"
            onClick={onClearDrill}
            className="text-text-primary cursor-pointer font-semibold hover:underline"
          >
            Todas categorias
          </button>
          <span className="text-text-tertiary"> › </span>
          <span className="text-text-primary font-semibold">{pai.nome}</span>
        </nav>
      ) : null}

      <table className="w-full border-separate border-spacing-y-0.5">
        <caption className="sr-only">
          {emDrill
            ? `Composição do gasto em ${pai.nome} por subcategoria`
            : "Composição do gasto por categoria"}
        </caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Categoria</th>
            <th scope="col">Proporção</th>
            <th scope="col">Valor</th>
            <th scope="col">Participação</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => {
            const cor = corDaCategoria(linha.cor);
            const podeDescer = !emDrill && linha.tem_filhos;

            return (
              <tr
                key={linha.categoria_id}
                onClick={podeDescer ? () => onDrillDown(linha.categoria_id) : undefined}
                className={cn("group", podeDescer && "hover:bg-surface/60 cursor-pointer")}
              >
                <th
                  scope="row"
                  className="text-body text-text-primary w-50 max-w-50 truncate py-2.5 pr-5 text-left font-medium"
                >
                  <span className="flex items-center gap-5">
                    <span
                      aria-hidden
                      className="size-4 shrink-0 rounded-xs"
                      style={{ background: cor }}
                    />
                    <span className="truncate">
                      {podeDescer ? (
                        <button
                          type="button"
                          onClick={(evento) => {
                            evento.stopPropagation();
                            onDrillDown(linha.categoria_id);
                          }}
                          className="cursor-pointer group-hover:underline"
                        >
                          {linha.nome}
                        </button>
                      ) : (
                        linha.nome
                      )}
                    </span>
                  </span>
                </th>

                <td className="w-full py-2.5 pr-5">
                  <div className="h-5 w-full" aria-hidden>
                    <div
                      className="h-full rounded-xs"
                      style={{
                        width: `${(toNumero(linha.valor) / maior) * 100}%`,
                        background: cor,
                      }}
                    />
                  </div>
                </td>

                {/* Largura mínima dita pelo pior caso real: "R$ 35.497,45"
                    são 12 caracteres em fonte mono. Sem `min-w`, a tabela
                    espreme a coluna e o valor encosta no percentual. */}
                <td className="tabular text-body-lg text-text-primary w-55 min-w-55 py-2.5 pr-4 text-right font-semibold whitespace-nowrap">
                  {formatBRLTexto(linha.valor)}
                </td>

                <td className="text-caption text-text-tertiary w-22 min-w-22 py-2.5 text-right tabular-nums whitespace-nowrap">
                  {Math.round(toNumero(linha.percentual))}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
