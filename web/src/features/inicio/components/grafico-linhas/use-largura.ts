import { useEffect, useRef, useState } from "react";

/**
 * Largura do contêiner em px, acompanhando o redimensionamento. O SVG usa
 * essa largura como coordenada (1 unidade = 1px), então o texto não encolhe
 * no celular e nunca há largura fixa que estoure a página.
 */
export function useLargura<T extends HTMLElement>(inicial = 600) {
  const ref = useRef<T>(null);
  const [largura, setLargura] = useState(inicial);

  useEffect(() => {
    const elemento = ref.current;
    if (!elemento) return;
    const medir = () => {
      const nova = Math.floor(elemento.getBoundingClientRect().width);
      if (nova > 0) setLargura(nova);
    };
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(elemento);
    return () => observador.disconnect();
  }, []);

  return { ref, largura };
}
