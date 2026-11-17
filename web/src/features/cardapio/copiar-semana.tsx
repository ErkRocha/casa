import { useState } from "react";

import { Button, BotaoIcone } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { Icone } from "@/components/ui/icone";
import { ApiError } from "@/lib/api";
import { intervaloDaSemana, somarDias } from "./datas";
import { useCopiarSemana } from "./queries";
import type { Semana, SemanaCopiada } from "./types";

/**
 * "Copiar esta semana para a próxima": escolhe a segunda-feira de destino
 * (a seguinte, por padrão) e copia refeições, quem come, ajustes e sessões.
 * Destino que já tem refeição: a API recusa (409) e a tela diz.
 */
export function CopiarSemana({
  aberto,
  onFechar,
  semana,
  quem,
  onCopiada,
}: {
  aberto: boolean;
  onFechar: () => void;
  semana: Semana;
  quem: string | null;
  onCopiada: (nova: SemanaCopiada) => void;
}) {
  return (
    <Dialogo aberto={aberto} onFechar={onFechar} titulo="Copiar semana">
      {aberto ? (
        <Conteudo semana={semana} quem={quem} onFechar={onFechar} onCopiada={onCopiada} />
      ) : null}
    </Dialogo>
  );
}

function Conteudo({
  semana,
  quem,
  onFechar,
  onCopiada,
}: {
  semana: Semana;
  quem: string | null;
  onFechar: () => void;
  onCopiada: (nova: SemanaCopiada) => void;
}) {
  const [destino, setDestino] = useState(() => somarDias(semana.inicio, 7));
  const [erro, setErro] = useState<string | null>(null);
  const copiar = useCopiarSemana(quem ?? "");

  return (
    <div className="flex flex-col gap-7">
      <p className="text-apoio text-texto-2 m-0 leading-normal">
        Leva os pratos, quem come e as sessões de preparo da semana de{" "}
        {intervaloDaSemana(semana.inicio)} para a semana de destino, deslocando as datas.
      </p>
      <div className="bg-superficie-2 rounded-interno flex items-center justify-between p-2">
        <BotaoIcone
          rotulo="Semana anterior"
          className="bg-transparent"
          disabled={destino <= somarDias(semana.inicio, -6)}
          onClick={() => setDestino((d) => somarDias(d, -7))}
        >
          <Icone nome="esquerda" tamanho={16} />
        </BotaoIcone>
        <span aria-live="polite" className="text-enfase font-forte">
          {intervaloDaSemana(destino)}
        </span>
        <BotaoIcone
          rotulo="Próxima semana"
          className="bg-transparent"
          onClick={() => setDestino((d) => somarDias(d, 7))}
        >
          <Icone nome="direita" tamanho={16} />
        </BotaoIcone>
      </div>
      {destino === semana.inicio ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          O destino é a própria semana.
        </p>
      ) : null}
      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-4">
        <Button
          disabled={!quem || copiar.isPending || destino === semana.inicio}
          onClick={() => {
            setErro(null);
            copiar.mutate(
              { semanaId: semana.id, destino },
              {
                onSuccess: (nova) => {
                  onFechar();
                  onCopiada(nova);
                },
                onError: (e) =>
                  setErro(
                    e instanceof ApiError && e.isConflito
                      ? `A semana de ${intervaloDaSemana(destino)} já tem pratos. ${e.detail}`
                      : e instanceof ApiError
                        ? e.detail
                        : "Não foi possível copiar. Tente de novo.",
                  ),
              },
            );
          }}
        >
          {copiar.isPending ? "Copiando…" : "Copiar"}
        </Button>
        <Button variant="ghost" onClick={onFechar}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}
