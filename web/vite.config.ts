import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Para onde o servidor do front repassa `/api` (D-18). O front chama a API
 * por caminho relativo, na mesma origem; quem sabe onde a API está é este
 * servidor. No compose, o serviço `api` pela rede interna; no modo local,
 * 127.0.0.1 na porta da API.
 */
const destinoApi = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

/**
 * Hosts aceitos além de localhost e IPs (que o Vite sempre aceita). O padrão
 * libera só o domínio do Tailscale (`.ts.net`, com os subdomínios), por onde
 * o `tailscale serve` entrega o painel. Lista separada por vírgula; vazio
 * deixa só localhost. Nunca `true`: aceitar qualquer Host abre o servidor de
 * desenvolvimento para DNS rebinding.
 */
const hostsPermitidos = (process.env.WEB_ALLOWED_HOSTS ?? ".ts.net")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // O container publica a porta; `host` precisa ser aberto para o Docker.
    // O compose publica só em 127.0.0.1, e o modo local passa --host 127.0.0.1.
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: hostsPermitidos,
    proxy: {
      "/api": {
        target: destinoApi,
        changeOrigin: true,
        rewrite: (caminho) => caminho.replace(/^\/api/, ""),
      },
    },
  },
});
