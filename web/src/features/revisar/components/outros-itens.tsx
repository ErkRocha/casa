import { useState } from "react";

import { Card } from "@/components/ui/card";
import { Button, SelectSobreposto } from "@/components/ui/controls";
import type { GrupoDeCategoria } from "@/features/cadastros/queries";
import { reaisDoLancamento } from "@/lib/format";
import { cn } from "@/lib/utils";
import { deOndeVeio } from "../textos";
import type { ItemRevisar, Motivo } from "../types";

const TITULOS: Partial<Record<Motivo, { titulo: string; texto: string }>> = {
  encargos: {
    titulo: "Encargos de fatura",
    texto: "Juros, multa e IOF que a fatura cobrou além das compras.",
  },
  observacao: {
    titulo: "Com observação",
    texto: "O banco mandou algo que o sistema não leu com segurança. Leia a nota antes de lançar.",
  },
  sem_categoria: {
    titulo: "Sem categoria",
    texto: "Escolha a categoria e lance. A escolha vira regra para as próximas.",
  },
  outros: {
    titulo: "Outros",
    texto: "Itens importados esperando a sua aprovação.",
  },
};

/**
 * Os motivos que as pranchetas não desenham (encargos, observação, sem
 * categoria, outros), no mesmo visual: a linha com a nota do banco, a
 * categoria editável e "Lançar" / "Descartar". Usa as ações que a API já
 * tem em `/importacoes/itens`.
 */
export function OutrosItens({
  motivo,
  itens,
  grupos,
  ocupado,
  onCategoria,
  onAprovar,
  onDescartar,
}: {
  motivo: Motivo;
  itens: ItemRevisar[];
  grupos: GrupoDeCategoria[];
  ocupado: boolean;
  onCategoria: (item: ItemRevisar, categoriaId: number | null) => void;
  onAprovar: (ids: number[]) => void;
  onDescartar: (ids: number[]) => void;
}) {
  const textos = TITULOS[motivo] ?? { titulo: "Para revisar", texto: "" };
  return (
    <Card className="flex flex-col gap-2 p-8 md:gap-3 md:px-11 md:py-10">
      <div className="flex flex-wrap items-center justify-between gap-5 pb-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-enfase md:text-bloco font-forte m-0">{textos.titulo}</h2>
          <span className="text-apoio text-texto-2">{textos.texto}</span>
        </div>
        {itens.length > 1 ? (
          <Button
            variant="ghost"
            disabled={ocupado}
            onClick={() => onAprovar(itens.map((i) => i.id))}
            className="bg-destaque-fundo text-destaque-hover hover:text-destaque-hover font-forte rounded-botao shrink-0"
          >
            Lançar os {itens.length}
          </Button>
        ) : null}
      </div>
      <ul className="m-0 flex list-none flex-col p-0">
        {itens.map((item) => (
          <li
            key={item.id}
            className="linha-acima grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-7 gap-y-4 py-6 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_120px_auto] md:py-7"
          >
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-corpo font-semibold">{item.descricao}</span>
              <span className="text-pequeno text-texto-2">{deOndeVeio(item)}</span>
            </span>
            <span className="text-enfase text-right font-bold whitespace-nowrap md:order-3">
              {reaisDoLancamento(item.valor, item.tipo_sugerido ?? "despesa")}
            </span>
            <span className="md:order-2">
              <CategoriaDoItem
                key={`${item.id}-${item.categoria_sugerida_id}`}
                item={item}
                grupos={grupos}
                onMudar={(id) => onCategoria(item, id)}
              />
            </span>
            <span className="col-span-2 flex justify-end gap-4 md:order-4 md:col-span-1">
              <Button disabled={ocupado} onClick={() => onAprovar([item.id])} className="flex-1 md:flex-none">
                Lançar
              </Button>
              <Button
                variant="secondary"
                disabled={ocupado}
                onClick={() => onDescartar([item.id])}
                className="flex-1 md:flex-none"
              >
                Descartar
              </Button>
            </span>
            {item.observacao ? (
              <p className="bg-atencao-fundo-2 text-atencao-texto rounded-campo text-pequeno col-span-2 m-0 px-6 py-4 leading-normal md:order-5 md:col-span-4">
                {item.observacao}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** A categoria sugerida, editável; trocar grava uma regra (D-09). */
function CategoriaDoItem({
  item,
  grupos,
  onMudar,
}: {
  item: ItemRevisar;
  grupos: GrupoDeCategoria[];
  onMudar: (categoriaId: number | null) => void;
}) {
  const [escolhida, setEscolhida] = useState(item.categoria_sugerida_id);
  const tipo = item.tipo_sugerido ?? "despesa";
  const doTipo = grupos.filter((g) => g.tipo === tipo);
  const nomes = new Map(doTipo.flatMap((g) => g.opcoes.map((o) => [o.id, o.nome] as const)));
  const vazia = escolhida === null;
  const nome = vazia ? "Sem categoria" : (nomes.get(escolhida) ?? item.categoria_nome ?? "Categoria");

  return (
    <SelectSobreposto
      rotulo={`Categoria de ${item.descricao}`}
      mostrar={nome}
      value={escolhida ?? ""}
      onChange={(e) => {
        const id = e.target.value === "" ? null : Number(e.target.value);
        setEscolhida(id);
        onMudar(id);
      }}
      className={cn(
        "text-apoio rounded-campo px-5 py-2.5",
        vazia
          ? "bg-atencao-fundo-2 text-atencao-texto shadow-[inset_0_0_0_1.5px_var(--color-atencao-borda-2)]"
          : "bg-superficie-2 text-texto",
      )}
    >
      <option value="">Sem categoria</option>
      {!vazia && !nomes.has(escolhida) ? (
        <option value={escolhida}>{item.categoria_nome ?? `Categoria ${escolhida}`}</option>
      ) : null}
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
