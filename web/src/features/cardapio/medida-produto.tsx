import { useId, useState } from "react";

import { Button, Input, Select } from "@/components/ui/controls";
import { ApiError } from "@/lib/api";
import { useCadastrarMedida } from "./queries";
import { decimalDigitado } from "./textos";
import type { MedidaBase } from "./types";

const BASES: Array<{ id: MedidaBase; rotulo: string }> = [
  { id: "g", rotulo: "g" },
  { id: "ml", rotulo: "ml" },
  { id: "un", rotulo: "un" },
];

/**
 * "Cadastrar a medida" de um produto que não converte (PATCH /produtos/{id}):
 * quanto tem em UMA unidade do produto (uma embalagem ou uma peça), em g, ml
 * ou un. Com isso a lista sabe quantos comprar. Sai do ingrediente sem
 * trocar de tela.
 */
export function MedidaProduto({
  produtoId,
  produtoNome,
  quem,
  onSalva,
  onCancelar,
}: {
  produtoId: number;
  produtoNome: string;
  quem: string | null;
  onSalva: () => void;
  onCancelar: () => void;
}) {
  const id = useId();
  const [base, setBase] = useState<MedidaBase>("g");
  const [quanto, setQuanto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const cadastrar = useCadastrarMedida(quem ?? "");

  function salvar() {
    const valor = quanto.trim() ? decimalDigitado(quanto) : null;
    if (quanto.trim() && valor === null) {
      setErro("Escreva um número, como 150 ou 0,5.");
      return;
    }
    if (valor === null && base !== "un") {
      setErro(`Diga quanto ${base} tem em 1 unidade de ${produtoNome}.`);
      return;
    }
    if (valor !== null && Number(valor) <= 0) {
      setErro("A medida precisa ser maior que zero.");
      return;
    }
    setErro(null);
    cadastrar.mutate(
      { produtoId, medida_base: base, medida_por_unidade: valor },
      {
        onSuccess: onSalva,
        onError: (e) =>
          setErro(e instanceof ApiError ? e.detail : "Não foi possível salvar. Tente de novo."),
      },
    );
  }

  return (
    <div className="bg-atencao-fundo-2 rounded-interno flex flex-col gap-5 p-6 shadow-[inset_0_0_0_1px_var(--color-atencao-borda-2)]">
      <div className="flex flex-wrap items-center gap-4">
        <span id={`${id}-frase`} className="text-apoio">
          1 unidade de {produtoNome} tem
        </span>
        <Input
          aria-labelledby={`${id}-frase`}
          inputMode="decimal"
          value={quanto}
          placeholder="150"
          onChange={(e) => setQuanto(e.target.value)}
          className="w-28 text-right"
        />
        <Select
          aria-label="Medida do produto"
          value={base}
          onChange={(e) => setBase(e.target.value as MedidaBase)}
        >
          {BASES.map((b) => (
            <option key={b.id} value={b.id}>
              {b.rotulo}
            </option>
          ))}
        </Select>
      </div>
      <p className="text-pequeno text-texto-2 m-0 leading-normal">
        "Unidade" é o que se compra: uma embalagem ou uma peça. Ex.: 1 unidade de Cebola tem 150 g;
        1 unidade de Leite 1L tem 1000 ml; ovo conta em un (deixe em branco). Colher e xícara são
        volume: para convertê-las, o produto precisa estar em ml.
      </p>
      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      <div className="flex gap-4">
        <Button disabled={!quem || cadastrar.isPending} onClick={salvar}>
          {cadastrar.isPending ? "Salvando…" : "Salvar medida"}
        </Button>
        <Button variant="ghost" onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
