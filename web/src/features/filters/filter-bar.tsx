import { useState } from "react";

import { PersonDot } from "@/components/layout/person-legend";
import { Button, CheckBox, Input, Popover } from "@/components/ui/controls";
import { useCategoriaArvore, useFormasPagamento, usePessoas } from "@/features/cadastros/queries";
import { TIPO_PAGAMENTO_LABEL } from "@/features/cadastros/types";
import { corDoBalde, rotuloDoBalde } from "@/features/filters/baldes";
import { useFiltros } from "./filter-context";
import {
  PERIODO_LABELS,
  PERIODO_ORDEM,
  contarFiltrosAtivos,
  temFiltroAtivo,
  type BaldePessoa,
} from "./types";

/**
 * Barra de filtro compartilhada. A mesma instância serve Transações e
 * Analytics — o recorte não se perde ao trocar de tela.
 *
 * Toda mudança aqui vira parâmetro de URL da API; nenhum filtro é aplicado
 * sobre array no navegador (D-14).
 */
export function FilterBar() {
  const { filtros, setFiltros, alternarCategoria, alternarFormaPagamento, limparTudo } =
    useFiltros();
  const [aberto, setAberto] = useState<"periodo" | "mais" | null>(null);

  const { data: arvore = [] } = useCategoriaArvore();
  const { data: pessoas = [] } = usePessoas();
  const { data: formas = [] } = useFormasPagamento();

  const quantidade = contarFiltrosAtivos(filtros);
  const baldes: BaldePessoa[] = [...pessoas.map((p) => p.id), "conjunto"];

  return (
    <div className="relative flex flex-wrap items-center gap-4 px-14 pb-8">
      {/* Período */}
      <div className="relative">
        <Button
          variant={filtros.periodo === "todo_periodo" ? "filter" : "filterActive"}
          onClick={() => setAberto(aberto === "periodo" ? null : "periodo")}
          className="px-5 py-3.5"
        >
          {PERIODO_LABELS[filtros.periodo]}
        </Button>
        <Popover aberto={aberto === "periodo"} onClose={() => setAberto(null)}>
          {PERIODO_ORDEM.map((periodo) => {
            const ativo = filtros.periodo === periodo;
            return (
              <div
                key={periodo}
                onClick={() => {
                  setFiltros({ periodo });
                  setAberto(null);
                }}
                className={
                  "text-body cursor-pointer rounded-lg px-5 py-3.5 " +
                  (ativo
                    ? "bg-accent-soft text-accent font-semibold"
                    : "text-text-primary hover:bg-surface-sunken")
                }
              >
                {PERIODO_LABELS[periodo]}
              </div>
            );
          })}
        </Popover>
      </div>

      <Input
        className="w-120 flex-1"
        placeholder="Buscar descrição, local, categoria..."
        value={filtros.texto}
        onChange={(e) => setFiltros({ texto: e.target.value })}
      />

      {/* Demais filtros */}
      <div className="relative">
        <Button
          variant={quantidade > 0 ? "filterActive" : "filter"}
          onClick={() => setAberto(aberto === "mais" ? null : "mais")}
          className="px-5 py-3.5"
        >
          Filtros{quantidade > 0 ? ` (${quantidade})` : ""}
        </Button>

        <Popover
          aberto={aberto === "mais"}
          onClose={() => setAberto(null)}
          className="right-0 left-auto max-h-220 min-w-150 overflow-y-auto p-6"
        >
          <SecaoTitulo>Categoria</SecaoTitulo>
          {arvore.map((raiz) => (
            <div key={raiz.id}>
              <LinhaCheck
                label={raiz.nome}
                marcado={filtros.categoriaIds.includes(raiz.id)}
                onClick={() => alternarCategoria(raiz.id)}
              />
              {raiz.subcategorias.map((sub) => (
                <LinhaCheck
                  key={sub.id}
                  label={sub.nome}
                  recuado
                  marcado={filtros.categoriaIds.includes(sub.id)}
                  onClick={() => alternarCategoria(sub.id)}
                />
              ))}
            </div>
          ))}

          <SecaoTitulo>Pessoa</SecaoTitulo>
          <div className="flex flex-wrap gap-3">
            <Button
              variant={filtros.pessoa === null ? "filterActive" : "filter"}
              onClick={() => setFiltros({ pessoa: null })}
              className="px-5 py-3"
            >
              Todos
            </Button>
            {baldes.map((balde) => (
              <Button
                key={String(balde)}
                variant={filtros.pessoa === balde ? "filterActive" : "filter"}
                onClick={() => setFiltros({ pessoa: balde })}
                className="flex items-center gap-3 px-5 py-3"
              >
                <PersonDot color={corDoBalde(balde, pessoas)} />
                {rotuloDoBalde(balde, pessoas)}
              </Button>
            ))}
          </div>

          <SecaoTitulo>Pagamento</SecaoTitulo>
          {formas.map((forma) => (
            <LinhaCheck
              key={forma.id}
              label={`${forma.apelido} · ${TIPO_PAGAMENTO_LABEL[forma.tipo]}`}
              marcado={filtros.formaPagamentoIds.includes(forma.id)}
              onClick={() => alternarFormaPagamento(forma.id)}
            />
          ))}

          <SecaoTitulo>Local</SecaoTitulo>
          <Input
            className="w-full"
            placeholder="Local..."
            value={filtros.local}
            onChange={(e) => setFiltros({ local: e.target.value })}
          />

          <SecaoTitulo>Valor</SecaoTitulo>
          <div className="flex gap-3">
            <Input
              className="tabular w-full"
              inputMode="decimal"
              placeholder="mín"
              value={filtros.valorMin}
              onChange={(e) => setFiltros({ valorMin: e.target.value })}
            />
            <Input
              className="tabular w-full"
              inputMode="decimal"
              placeholder="máx"
              value={filtros.valorMax}
              onChange={(e) => setFiltros({ valorMax: e.target.value })}
            />
          </div>
        </Popover>
      </div>

      {temFiltroAtivo(filtros) ? (
        <Button variant="ghost" onClick={limparTudo} className="px-4 py-3">
          Limpar
        </Button>
      ) : null}
    </div>
  );
}

function SecaoTitulo({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-label text-text-tertiary tracking-caps mt-7 mb-3 px-2 font-semibold uppercase first:mt-0">
      {children}
    </div>
  );
}

function LinhaCheck({
  label,
  marcado,
  onClick,
  recuado = false,
}: {
  label: string;
  marcado: boolean;
  onClick: () => void;
  recuado?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={
        "text-body text-text-primary hover:bg-surface-sunken flex cursor-pointer items-center gap-4 rounded-md px-2 py-2 " +
        (recuado ? "pl-9" : "")
      }
    >
      <CheckBox marcado={marcado} />
      {label}
    </div>
  );
}
