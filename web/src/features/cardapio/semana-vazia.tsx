import { useState } from "react";

import { Button } from "@/components/ui/controls";
import { Vazio } from "@/components/ui/estados";
import { ApiError } from "@/lib/api";
import { intervaloDaSemana, semanaEncerrada, somarDias } from "./datas";
import { useCopiarSemana, useCriarSemana, useSemana } from "./queries";
import type { SemanaCopiada } from "./types";

/**
 * Semana que ainda não existe (a API dá 404 com `existe: false`): oferece
 * criar a semana, vazia, ou copiar a anterior, quando ela existe.
 */
export function SemanaVazia({
  inicio,
  quem,
  onCriada,
}: {
  inicio: string;
  quem: string | null;
  onCriada: (copiada: SemanaCopiada | null) => void;
}) {
  const anterior = useSemana(somarDias(inicio, -7));
  const criar = useCriarSemana(quem ?? "");
  const copiar = useCopiarSemana(quem ?? "");
  const [erro, setErro] = useState<string | null>(null);
  const aoFalhar = (e: unknown) =>
    setErro(e instanceof ApiError ? e.detail : "Não foi possível. Tente de novo.");

  const semanaAnterior = anterior.data ?? null;
  const ocupado = criar.isPending || copiar.isPending;

  return (
    <Vazio
      titulo={`Sem cardápio de ${intervaloDaSemana(inicio)}`}
      texto={
        semanaEncerrada(inicio)
          ? "Esta semana já passou e não tem cardápio. Criar uma semana vazia serve para registrar o que foi comido."
          : "Crie a semana, vazia, para ir escolhendo os pratos, ou copie a semana anterior e ajuste."
      }
    >
      <Button
        disabled={!quem || ocupado}
        onClick={() => {
          setErro(null);
          criar.mutate(inicio, { onSuccess: () => onCriada(null), onError: aoFalhar });
        }}
      >
        Criar semana
      </Button>
      <Button
        variant="secondary"
        disabled={!quem || ocupado || !semanaAnterior}
        onClick={() => {
          if (!semanaAnterior) return;
          setErro(null);
          copiar.mutate(
            { semanaId: semanaAnterior.id, destino: inicio },
            { onSuccess: (nova) => onCriada(nova), onError: aoFalhar },
          );
        }}
      >
        Copiar da semana anterior
      </Button>
      {!anterior.isLoading && !semanaAnterior ? (
        <span className="text-apoio text-texto-2">
          A semana anterior ({intervaloDaSemana(somarDias(inicio, -7))}) também não tem cardápio.
        </span>
      ) : null}
      {erro ? (
        <span role="alert" className="text-apoio text-perigo">
          {erro}
        </span>
      ) : null}
    </Vazio>
  );
}
