import { href } from "@/lib/rotas";
import { useEstadoSincronizacao } from "./queries";
import { textoSyncAtrasada } from "./textos";

/**
 * Faixa no topo do Início quando a sync parou (`atrasada`, calculada pela
 * API). O "Atualizar agora" mora na tela da sincronização: o link leva até lá.
 */
export function AvisoSyncAtrasada() {
  const estado = useEstadoSincronizacao();
  if (!estado.data?.atrasada) return null;
  return (
    <div
      role="alert"
      className="bg-atencao-fundo text-atencao-texto border-atencao-borda rounded-interno flex flex-col gap-2 border px-7 py-6"
    >
      <strong className="text-corpo font-semibold">
        {textoSyncAtrasada(estado.data.ultima_atualizacao)}
      </strong>
      <span className="text-apoio leading-snug">
        Confira se o Docker Desktop está aberto e toque em Atualizar agora.{" "}
        <a href={href("sincronizacao")} className="text-atencao-texto font-semibold underline">
          Atualizar agora
        </a>
      </span>
    </div>
  );
}
