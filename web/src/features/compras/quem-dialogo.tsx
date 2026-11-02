import { useState } from "react";

import { Button, Input } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { usePessoas } from "@/features/cadastros/queries";
import { definirQuem } from "./quem";

/**
 * "Quem é você?" (D-25): sem identidade do Tailscale, o aparelho pergunta
 * uma vez e guarda. As opções são as pessoas cadastradas em finanças; sem
 * elas (API fora do ar), dá para digitar o nome.
 */
export function QuemDialogo({ aberto, onFechar }: { aberto: boolean; onFechar: () => void }) {
  const pessoas = usePessoas();
  const [digitado, setDigitado] = useState("");
  const individuais = (pessoas.data ?? []).filter((p) => p.tipo === "individual");

  function escolher(nome: string) {
    const limpo = nome.trim();
    if (!limpo) return;
    definirQuem(limpo);
    onFechar();
  }

  return (
    <Dialogo aberto={aberto} onFechar={onFechar} titulo="Quem é você?">
      <div className="flex flex-col gap-7">
        <p className="text-apoio text-texto-2 m-0 leading-normal">
          Este aparelho guarda a resposta. É o nome que aparece em "adicionou" e "pegou" para a
          outra pessoa.
        </p>
        {individuais.length > 0 ? (
          <div className="grid grid-cols-2 gap-4">
            {individuais.map((p) => (
              <Button key={p.id} className="h-26 text-[17px]" onClick={() => escolher(p.nome)}>
                {p.nome}
              </Button>
            ))}
          </div>
        ) : null}
        <form
          className="flex gap-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            escolher(digitado);
          }}
        >
          <Input
            aria-label="Seu nome"
            placeholder={individuais.length > 0 ? "Outro nome" : "Seu nome"}
            value={digitado}
            maxLength={60}
            onChange={(e) => setDigitado(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="secondary" disabled={!digitado.trim()}>
            Usar
          </Button>
        </form>
      </div>
    </Dialogo>
  );
}
