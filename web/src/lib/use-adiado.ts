import { useEffect, useState } from "react";

/**
 * O valor, só depois de `ms` sem mudar. A busca usa para não mandar uma
 * consulta à API por tecla.
 */
export function useAdiado<T>(valor: T, ms: number): T {
  const [adiado, setAdiado] = useState(valor);
  useEffect(() => {
    const espera = setTimeout(() => setAdiado(valor), ms);
    return () => clearTimeout(espera);
  }, [valor, ms]);
  return adiado;
}
