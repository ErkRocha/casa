import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card } from "./card";
import { Button } from "./controls";

/**
 * Os três estados de uma tela que lê da API (D-22): carregando, falha e
 * vazio. Cada tela escolhe o texto; o desenho é um só.
 */

/** Blocos cinza no lugar do conteúdo. `alturas` são classes (`h-60`). */
export function Carregando({
  rotulo,
  alturas = ["h-60", "h-120"],
  className,
}: {
  rotulo: string;
  alturas?: string[];
  className?: string;
}) {
  return (
    <div aria-busy="true" aria-label={rotulo} className={cn("flex flex-col gap-8", className)}>
      {alturas.map((altura, i) => (
        <div key={i} className={cn("bg-superficie rounded-bloco animate-shimmer", altura)} />
      ))}
    </div>
  );
}

export function Falha({
  titulo,
  erro,
  onTentar,
}: {
  titulo: string;
  erro: unknown;
  onTentar: () => void;
}) {
  return (
    <Card role="alert" className="flex flex-col items-start gap-5 px-9 py-9 md:px-11 md:py-10">
      <h2 className="text-bloco font-forte m-0">{titulo}</h2>
      <p className="text-apoio text-texto-2 m-0">{mensagemDeErro(erro)}</p>
      <Button onClick={onTentar}>Tentar de novo</Button>
    </Card>
  );
}

export function Vazio({
  titulo,
  texto,
  children,
}: {
  titulo: string;
  texto: string;
  /** Ações: botão de voltar, link para outra tela. */
  children?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-start gap-5 px-9 py-10 md:px-11 md:py-12">
      <h2 className="text-bloco font-forte m-0">{titulo}</h2>
      <p className="text-corpo text-texto-2 m-0 max-w-[560px] leading-normal">{texto}</p>
      {children ? <div className="flex flex-wrap items-center gap-6">{children}</div> : null}
    </Card>
  );
}

/** O `detail` da API, já em pt-BR, ou um texto genérico. */
function mensagemDeErro(erro: unknown): string {
  return erro instanceof ApiError
    ? erro.detail
    : "A API não respondeu. Confira se ela está no ar.";
}
