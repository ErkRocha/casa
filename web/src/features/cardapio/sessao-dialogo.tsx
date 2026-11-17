import { useState } from "react";

import { Button, Input } from "@/components/ui/controls";
import { Dialogo } from "@/components/ui/dialogo";
import { ApiError } from "@/lib/api";
import { dataBR, domingoDa, somarDias } from "./datas";
import { useCriarSessao } from "./queries";

/**
 * "Adicionar sessão": o dia (do sábado anterior ao domingo da semana) e um
 * rótulo opcional ("quarta à noite"). As refeições passam a usar a sessão
 * mais próxima antes delas, pelo roteiro.
 */
export function SessaoDialogo({
  aberto,
  onFechar,
  semanaId,
  inicio,
  hoje,
  quem,
}: {
  aberto: boolean;
  onFechar: () => void;
  semanaId: number;
  inicio: string;
  hoje: string;
  quem: string | null;
}) {
  return (
    <Dialogo aberto={aberto} onFechar={onFechar} titulo="Adicionar sessão de preparo">
      {aberto ? (
        <Conteudo semanaId={semanaId} inicio={inicio} hoje={hoje} quem={quem} onFechar={onFechar} />
      ) : null}
    </Dialogo>
  );
}

function Conteudo({
  semanaId,
  inicio,
  hoje,
  quem,
  onFechar,
}: {
  semanaId: number;
  inicio: string;
  hoje: string;
  quem: string | null;
  onFechar: () => void;
}) {
  const minimo = somarDias(inicio, -2);
  const maximo = domingoDa(inicio);
  const [data, setData] = useState(hoje >= minimo && hoje <= maximo ? hoje : inicio);
  const [rotulo, setRotulo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const criar = useCriarSessao(quem ?? "");

  return (
    <form
      className="flex flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (!data || data < minimo || data > maximo) {
          setErro(`O dia precisa ficar entre ${dataBR(minimo)} e ${dataBR(maximo)}.`);
          return;
        }
        setErro(null);
        criar.mutate(
          { semanaId, data, rotulo: rotulo.trim() || null },
          {
            onSuccess: onFechar,
            onError: (e) =>
              setErro(e instanceof ApiError ? e.detail : "Não foi possível criar. Tente de novo."),
          },
        );
      }}
    >
      <p className="text-apoio text-texto-2 m-0 leading-normal">
        Do sábado anterior ({dataBR(minimo)}) ao domingo ({dataBR(maximo)}).
      </p>
      <label className="flex flex-col gap-3">
        <span className="text-apoio font-semibold">Dia</span>
        <Input type="date" min={minimo} max={maximo} value={data} onChange={(e) => setData(e.target.value)} />
      </label>
      <label className="flex flex-col gap-3">
        <span className="text-apoio font-semibold">
          Rótulo <span className="text-texto-2 font-normal">(opcional)</span>
        </span>
        <Input
          value={rotulo}
          maxLength={60}
          placeholder="Ex.: quarta à noite"
          onChange={(e) => setRotulo(e.target.value)}
        />
      </label>
      {erro ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          {erro}
        </p>
      ) : null}
      <div className="flex gap-4">
        <Button type="submit" disabled={!quem || criar.isPending}>
          {criar.isPending ? "Criando…" : "Criar sessão"}
        </Button>
        <Button variant="ghost" onClick={onFechar}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
