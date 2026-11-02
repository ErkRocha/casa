/**
 * O `id_cliente` de cada escrita que cria (D-25): gerado no aparelho, ele faz
 * o reenvio do mesmo pedido devolver o que o primeiro criou.
 *
 * `crypto.randomUUID` só existe em contexto seguro (HTTPS ou localhost); pelo
 * IP da rede de casa não. Aí vale o `getRandomValues`, que existe sempre.
 */
export function novoIdCliente(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
