import { useState } from "react";

import { SelectSobreposto } from "@/components/ui/controls";
import type { GrupoDeCategoria } from "@/features/cadastros/queries";
import { cn } from "@/lib/utils";
import type { Transacao } from "../types";

/**
 * A categoria da linha, editável ali mesmo (`LancamentosDesktop`): a pílula
 * cinza com o nome da folha, âmbar quando falta categoria. Trocar grava pelo
 * PATCH de `/transacoes`, que aprende a regra (D-09).
 *
 * Transferência não tem categoria (D-05): aparece só o texto.
 */
export function CategoriaInline({
  transacao,
  grupos,
  onMudar,
  compacta = false,
}: {
  transacao: Transacao;
  grupos: GrupoDeCategoria[];
  onMudar: (categoriaId: number | null) => void;
  compacta?: boolean;
}) {
  // O valor escolhido aparece na hora; a linha volta ao que a API disser
  // quando a listagem recarregar (o componente é recriado pela `key`).
  const [escolhida, setEscolhida] = useState<number | null>(transacao.categoria_id);

  if (transacao.tipo === "transferencia") {
    return <span className="text-apoio text-texto-2">Transferência</span>;
  }

  const doTipo = grupos.filter((g) => g.tipo === transacao.tipo);
  const nomes = new Map(doTipo.flatMap((g) => g.opcoes.map((o) => [o.id, o.nome] as const)));
  const atual = escolhida ?? null;
  // Categoria fora da lista (inativa, de outro tipo): continua visível.
  const avulsa = atual !== null && !nomes.has(atual);
  const nome = atual === null ? "Sem categoria" : (nomes.get(atual) ?? transacao.categoria_nome);
  const vazia = atual === null;

  return (
    <SelectSobreposto
      rotulo={`Categoria de ${transacao.descricao}`}
      mostrar={nome}
      value={atual ?? ""}
      onChange={(evento) => {
        const id = evento.target.value === "" ? null : Number(evento.target.value);
        setEscolhida(id);
        onMudar(id);
      }}
      className={cn(
        compacta
          ? "text-selo rounded-selo gap-2 px-3.5 py-0.5 font-semibold"
          : "text-apoio rounded-campo px-5 py-2.5",
        vazia
          ? "bg-atencao-fundo-2 text-atencao-texto shadow-[inset_0_0_0_1.5px_var(--color-atencao-borda-2)]"
          : cn("bg-superficie-2", compacta ? "text-texto-apoio" : "text-texto"),
      )}
    >
      <option value="">Sem categoria</option>
      {avulsa ? <option value={atual}>{transacao.categoria_nome ?? `Categoria ${atual}`}</option> : null}
      {doTipo.map((grupo) => (
        <optgroup key={grupo.raizId} label={grupo.raizNome}>
          {grupo.opcoes.map((opcao) => (
            <option key={opcao.id} value={opcao.id}>
              {opcao.nome}
            </option>
          ))}
        </optgroup>
      ))}
    </SelectSobreposto>
  );
}
