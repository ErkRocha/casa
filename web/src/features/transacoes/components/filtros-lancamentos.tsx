import { useState } from "react";

import { CheckBox, Pilula, Popover } from "@/components/ui/controls";
import { Icone } from "@/components/ui/icone";
import { rotuloDaForma } from "@/features/cadastros/forma-pagamento";
import { useContas, useFormasPagamento, useGruposDeCategoria } from "@/features/cadastros/queries";
import type { Pessoa } from "@/features/cadastros/types";
import { ROTULO_JUNTOS } from "@/features/filters/baldes";
import type { BaldePessoa, TipoTransacao } from "@/features/filters/types";
import { cn } from "@/lib/utils";
import { ROTULO_TIPO, type FiltrosLancamentos } from "../filtros";

/**
 * Os filtros de Lançamentos (`LancamentosDesktop`, `LancamentosCelular`):
 * busca, quem, categoria, pagamento, tipo e o atalho "N sem categoria".
 *
 * No celular, categoria, pagamento e tipo ficam atrás da pílula "Filtros".
 */
export function FiltrosLancamentos({
  filtros,
  texto,
  onTexto,
  onMudar,
  pessoas,
  semCategoria,
}: {
  filtros: FiltrosLancamentos;
  /** O que está no campo de busca, antes da espera (a busca vai adiada). */
  texto: string;
  onTexto: (texto: string) => void;
  onMudar: (patch: Partial<FiltrosLancamentos>) => void;
  pessoas: Pessoa[];
  /** Quantos sem categoria no recorte, contados pelo banco. */
  semCategoria: number;
}) {
  const [maisAberto, setMaisAberto] = useState(false);
  const { data: grupos } = useGruposDeCategoria();
  const { data: formas = [] } = useFormasPagamento();
  const { data: contas = [] } = useContas();

  const nomeDaConta = new Map(contas.map((c) => [c.id, c.nome]));
  const opcoesCategoria = grupos.flatMap((g) =>
    g.opcoes.map((o) => ({
      id: o.id,
      rotulo: o.nome === g.raizNome ? o.nome : `${g.raizNome} › ${o.nome}`,
    })),
  );
  const opcoesForma = formas
    .map((f) => ({
      id: f.id,
      rotulo: rotuloDaForma(f.tipo, f.apelido, f.conta_id ? nomeDaConta.get(f.conta_id) : null),
    }))
    .sort((a, b) => a.rotulo.localeCompare(b.rotulo, "pt-BR"));
  const opcoesTipo = (Object.keys(ROTULO_TIPO) as TipoTransacao[]).map((tipo) => ({
    id: tipo,
    rotulo: ROTULO_TIPO[tipo],
  }));

  const quem: Array<{ balde: BaldePessoa | null; nome: string }> = [
    { balde: null, nome: "Todos" },
    ...pessoas.map((p) => ({ balde: p.id as BaldePessoa, nome: p.nome })),
    { balde: "conjunto", nome: ROTULO_JUNTOS },
  ];
  const outrosAtivos =
    filtros.categoriaIds.length + filtros.formaPagamentoIds.length + filtros.tipos.length;

  return (
    <section
      aria-label="Filtros"
      className="md:bg-superficie md:rounded-bloco flex flex-col gap-6 md:p-7"
    >
      <div className="flex flex-wrap items-center gap-5">
        <label className="bg-superficie md:bg-superficie-2 rounded-sub md:rounded-interno text-texto-2 flex min-h-24 flex-[1_1_260px] items-center gap-4 px-7 md:min-h-22">
          <Icone nome="busca" />
          <span className="sr-only">Buscar lançamentos</span>
          <input
            type="search"
            value={texto}
            onChange={(e) => onTexto(e.target.value)}
            placeholder="Buscar por descrição, loja ou valor"
            className="text-texto placeholder:text-texto-2 text-enfase md:text-corpo min-w-0 flex-1 border-none bg-transparent outline-none"
          />
        </label>
        <div
          id="filtros-mais"
          className={cn("w-full flex-wrap gap-5 md:flex md:w-auto", maisAberto ? "flex" : "hidden")}
        >
          <FiltroMultiplo
            rotulo="Categoria"
            opcoes={opcoesCategoria}
            escolhidos={filtros.categoriaIds}
            onMudar={(categoriaIds) => onMudar({ categoriaIds })}
          />
          <FiltroMultiplo
            rotulo="Pagamento"
            opcoes={opcoesForma}
            escolhidos={filtros.formaPagamentoIds}
            onMudar={(formaPagamentoIds) => onMudar({ formaPagamentoIds })}
          />
          <FiltroMultiplo
            rotulo="Tipo"
            opcoes={opcoesTipo}
            escolhidos={filtros.tipos}
            onMudar={(tipos) => onMudar({ tipos })}
          />
        </div>
      </div>

      <div className="-mx-7 flex items-center gap-4 overflow-x-auto px-7 md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
        <span className="text-apoio text-texto-2 hidden pr-2 md:inline">Quem:</span>
        {quem.map(({ balde, nome }) => (
          <Pilula
            key={String(balde)}
            ativa={filtros.pessoa === balde}
            aria-pressed={filtros.pessoa === balde}
            fundo="adaptavel"
            onClick={() => onMudar({ pessoa: balde })}
          >
            {nome}
          </Pilula>
        ))}
        <span className="hidden flex-1 md:block" />
        {semCategoria > 0 || filtros.semCategoria ? (
          <Pilula
            atencao
            ativa={filtros.semCategoria}
            aria-pressed={filtros.semCategoria}
            onClick={() => onMudar({ semCategoria: !filtros.semCategoria })}
          >
            {semCategoria} sem categoria
          </Pilula>
        ) : null}
        <Pilula
          fundo="superficie"
          ativa={outrosAtivos > 0}
          aria-expanded={maisAberto}
          aria-controls="filtros-mais"
          onClick={() => setMaisAberto((aberto) => !aberto)}
          className="md:hidden"
        >
          <Icone nome="filtros" tamanho={14} />
          Filtros{outrosAtivos > 0 ? ` (${outrosAtivos})` : ""}
        </Pilula>
      </div>
    </section>
  );
}

/** "Categoria ⌄": lista de escolha múltipla num popover. */
function FiltroMultiplo<T extends string | number>({
  rotulo,
  opcoes,
  escolhidos,
  onMudar,
}: {
  rotulo: string;
  opcoes: Array<{ id: T; rotulo: string }>;
  escolhidos: T[];
  onMudar: (escolhidos: T[]) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const ativo = escolhidos.length > 0;

  function alternar(id: T) {
    onMudar(escolhidos.includes(id) ? escolhidos.filter((x) => x !== id) : [...escolhidos, id]);
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={aberto}
        onClick={() => setAberto((a) => !a)}
        className={cn(
          "text-apoio font-medio rounded-interno flex min-h-22 cursor-pointer items-center gap-3 border-none px-7",
          ativo
            ? "bg-destaque-fundo text-destaque-hover"
            : "bg-superficie md:bg-superficie-2 text-texto",
        )}
      >
        {rotulo}
        {ativo ? ` (${escolhidos.length})` : ""}
        <Icone nome="baixo" tamanho={14} />
      </button>
      <Popover
        aberto={aberto}
        onClose={() => setAberto(false)}
        className="max-h-[360px] min-w-[240px] overflow-y-auto"
      >
        <ul className="m-0 flex list-none flex-col p-0" aria-label={rotulo}>
          {opcoes.map((opcao) => {
            const marcado = escolhidos.includes(opcao.id);
            return (
              <li key={String(opcao.id)}>
                <button
                  type="button"
                  aria-pressed={marcado}
                  onClick={() => alternar(opcao.id)}
                  className="text-apoio rounded-campo hover:bg-superficie-2 text-texto flex min-h-20 w-full cursor-pointer items-center gap-4 border-none bg-transparent px-4 text-left"
                >
                  <CheckBox marcado={marcado} />
                  {opcao.rotulo}
                </button>
              </li>
            );
          })}
        </ul>
        {ativo ? (
          <button
            type="button"
            onClick={() => onMudar([])}
            className="text-apoio text-destaque mt-2 min-h-20 w-full cursor-pointer border-none bg-transparent px-4 text-left font-semibold"
          >
            Limpar {rotulo.toLowerCase()}
          </button>
        ) : null}
      </Popover>
    </div>
  );
}
