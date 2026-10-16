import { useState, type ReactNode } from "react";

import type { Rota } from "@/lib/rotas";
import { BarraInferior } from "./barra-inferior";
import { BarraLateral } from "./barra-lateral";

const CHAVE_RECOLHIDA = "controle-casa:menu-recolhido";

function lerRecolhida(): boolean {
  try {
    return window.localStorage.getItem(CHAVE_RECOLHIDA) !== "nao";
  } catch {
    return true;
  }
}

/**
 * Casca do painel (D-22): barra lateral a partir de 768px, barra inferior
 * abaixo disso. A página rola inteira; a barra lateral fica presa.
 */
export function AppShell({ rota, children }: { rota: Rota; children: ReactNode }) {
  // Entre 768 e 1023px a barra começa recolhida, para sobrar espaço.
  const [recolhida, setRecolhida] = useState(lerRecolhida);

  function alternar() {
    setRecolhida((atual) => {
      try {
        window.localStorage.setItem(CHAVE_RECOLHIDA, atual ? "nao" : "sim");
      } catch {
        // Sem armazenamento (aba privada): vale só nesta visita.
      }
      return !atual;
    });
  }

  return (
    <div className="bg-fundo text-texto flex min-h-screen w-full">
      <a
        href="#conteudo"
        onClick={(evento) => {
          // O hash é a rota: pular para o conteúdo não pode trocar de tela.
          evento.preventDefault();
          document.getElementById("conteudo")?.focus();
        }}
        className="bg-destaque rounded-interno sr-only z-50 px-8 py-4 text-white focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
      >
        Pular para o conteúdo
      </a>
      <BarraLateral rota={rota} recolhida={recolhida} onAlternar={alternar} />
      <main
        id="conteudo"
        tabIndex={-1}
        className="min-w-0 flex-1 px-7 pt-8 pb-60 outline-none md:px-16 md:pt-14 md:pb-22"
      >
        {children}
      </main>
      <BarraInferior rota={rota} />
    </div>
  );
}
