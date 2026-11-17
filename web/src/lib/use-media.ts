import { useSyncExternalStore } from "react";

/**
 * Se a media query vale agora, e avisa quando muda. Quem desenha duas telas
 * (celular e computador) escolhe uma por aqui, em vez de montar as duas.
 */
export function useMedia(consulta: string): boolean {
  return useSyncExternalStore(
    (ouvir) => {
      const lista = window.matchMedia(consulta);
      lista.addEventListener("change", ouvir);
      return () => lista.removeEventListener("change", ouvir);
    },
    () => window.matchMedia(consulta).matches,
    () => false,
  );
}
