import { useState } from "react";

import { Icone } from "@/components/ui/icone";
import { useAdiado } from "@/lib/use-adiado";
import { cn } from "@/lib/utils";
import { useReceitas } from "./queries";
import { ROTULO_TIPO } from "./textos";
import type { ReceitaResumo } from "./types";

/**
 * Busca de receitas enquanto digita (`GET /receitas?busca=`). Serve para
 * trocar ou adicionar um prato e para a lista de receitas.
 */
export function BuscaReceitas({
  onEscolher,
  atual,
  rotuloDaLista = "Receitas",
}: {
  onEscolher: (receita: ReceitaResumo) => void;
  /** A receita que já está no lugar: aparece marcada. */
  atual?: number | null;
  rotuloDaLista?: string;
}) {
  const [texto, setTexto] = useState("");
  const busca = useAdiado(texto, 200);
  const receitas = useReceitas(busca);
  const itens = receitas.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <label className="bg-superficie-2 rounded-sub flex h-26 items-center gap-4 px-7 shadow-[inset_0_0_0_2px_var(--color-destaque)]">
        <span className="sr-only">Buscar receita</span>
        <Icone nome="busca" tamanho={18} />
        <input
          autoFocus
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Arroz, frango, omelete…"
          className="text-texto placeholder:text-texto-2 flex-1 border-none bg-transparent text-[17px] outline-none"
          autoComplete="off"
          enterKeyHint="search"
        />
      </label>

      {receitas.isError ? (
        <p role="alert" className="text-apoio text-perigo m-0">
          Não foi possível ler as receitas. Tente de novo.
        </p>
      ) : receitas.isLoading ? (
        <p role="status" className="text-apoio text-texto-2 m-0">
          Carregando as receitas…
        </p>
      ) : itens.length === 0 ? (
        <p className="text-apoio text-texto-2 m-0">
          {texto.trim() ? `Nenhuma receita com "${texto.trim()}".` : "Nenhuma receita cadastrada."}
        </p>
      ) : (
        <ul aria-label={rotuloDaLista} className="m-0 flex list-none flex-col p-0">
          {itens.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onEscolher(r)}
                aria-current={r.id === atual ? "true" : undefined}
                className={cn(
                  "text-texto rounded-interno flex min-h-26 w-full cursor-pointer items-center justify-between gap-4 border-none px-6 text-left",
                  r.id === atual ? "bg-destaque-fundo" : "bg-transparent",
                )}
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-enfase font-semibold">{r.nome}</span>
                  <span className="text-pequeno text-texto-2">
                    {ROTULO_TIPO[r.tipo]}
                    {r.tempo_preparo_min ? ` · ${r.tempo_preparo_min} min` : ""}
                    {r.quantidades_revisadas ? "" : " · quantidades estimadas"}
                  </span>
                </span>
                {r.id === atual ? (
                  <span className="text-pequeno text-texto-2 shrink-0">atual</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}
      {receitas.data && receitas.data.total > itens.length ? (
        <p className="text-pequeno text-texto-2 m-0">
          Mostrando {itens.length} de {receitas.data.total}. Digite para afunilar.
        </p>
      ) : null}
    </div>
  );
}
