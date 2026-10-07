#!/usr/bin/env bash
# Servidor MCP do chat sob demanda (D-20), no modo local, para o Claude Desktop.
#
#   "command": "C:\Program Files\Git\bin\bash.exe",
#   "args": ["C:/caminho/para/controle-casa/scripts/local/mcp.sh"]
#
# Carrega o .env pelo _config.sh (nenhuma senha vai para a configuração do
# Claude Desktop) e troca de processo para `python -m app.mcp`.
#
# A stdout é o canal do protocolo: nada aqui escreve nela. Mensagens vão
# para a stderr, que o Claude Desktop guarda no log do servidor.
set -euo pipefail
source "$(dirname "$0")/_config.sh"

if [[ -f "$CASA_MARCADOR_MIGRACAO" && "${CASA_FORCAR_LOCAL:-}" != "1" ]]; then
  echo "O sistema foi migrado para o Docker: use a configuração com docker exec (D-17)." >&2
  exit 1
fi

casa_exportar_ambiente >/dev/null
cd "$CASA_REPO/api"
exec "$PY" -m app.mcp
