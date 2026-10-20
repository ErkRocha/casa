import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

/** Campo e erro dos formulários das telas de configuração (D-22). */

export function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-3">
      <span className="text-apoio font-semibold">{rotulo}</span>
      {children}
    </label>
  );
}

export function ErroDoFormulario({ erro }: { erro: unknown }) {
  return (
    <p role="alert" className="text-apoio text-perigo m-0">
      {erro instanceof ApiError ? erro.detail : "Não foi possível salvar."}
    </p>
  );
}
