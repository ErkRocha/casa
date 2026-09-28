import { useState } from "react";

import { Button, Select } from "@/components/ui/controls";
import { useCategoriaOpcoes, usePessoas } from "@/features/cadastros/queries";
import type { BaldePessoa } from "@/features/filters/types";

/**
 * Barra de ação em lote. Aparece quando há seleção.
 *
 * É o que torna a tela útil de verdade depois de uma importação: corrigir 40
 * categorias erradas de uma vez em vez de uma a uma.
 */
export function BatchBar({
  quantidade,
  onAplicar,
  onExcluir,
  onCancelar,
  ocupado,
}: {
  quantidade: number;
  onAplicar: (patch: { categoriaId: number | null; pessoa: BaldePessoa | null }) => void;
  onExcluir: () => void;
  onCancelar: () => void;
  ocupado: boolean;
}) {
  const [categoriaId, setCategoriaId] = useState<string>("");
  const [pessoa, setPessoa] = useState<string>("");

  const { data: categorias } = useCategoriaOpcoes();
  const { data: pessoas = [] } = usePessoas();

  const nadaEscolhido = categoriaId === "" && pessoa === "";

  return (
    <div className="bg-surface border-border-faint flex flex-wrap items-center gap-4 border-b px-8 py-5">
      <span className="text-body text-text-primary mr-2 font-semibold">
        {quantidade} selecionada{quantidade > 1 ? "s" : ""}
      </span>

      <Select
        value={categoriaId}
        onChange={(e) => setCategoriaId(e.target.value)}
        aria-label="Categoria para aplicar em lote"
      >
        <option value="">Categoria...</option>
        {categorias.map((opcao) => (
          <option key={opcao.id} value={opcao.id}>
            {opcao.label}
          </option>
        ))}
      </Select>

      <Select
        value={pessoa}
        onChange={(e) => setPessoa(e.target.value)}
        aria-label="Pessoa para aplicar em lote"
      >
        <option value="">Pessoa...</option>
        {pessoas.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
        <option value="conjunto">Conjunto</option>
      </Select>

      <Button
        disabled={nadaEscolhido || ocupado}
        onClick={() => {
          onAplicar({
            categoriaId: categoriaId === "" ? null : Number(categoriaId),
            // "conjunto" limpa o dono — é NULL no banco, não uma pessoa
            // chamada "conjunto" (D-03).
            pessoa: pessoa === "" ? null : pessoa === "conjunto" ? "conjunto" : Number(pessoa),
          });
          setCategoriaId("");
          setPessoa("");
        }}
        className="px-6 py-3"
      >
        Aplicar
      </Button>

      <Button variant="danger" onClick={onExcluir} disabled={ocupado} className="px-6 py-3">
        Excluir
      </Button>

      <Button variant="ghost" onClick={onCancelar} className="px-6 py-3">
        Cancelar
      </Button>
    </div>
  );
}
