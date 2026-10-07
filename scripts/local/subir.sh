#!/usr/bin/env bash
# Sobe o Controle de Casa sem Docker: Postgres local, API e painel.
#
#   bash scripts/local/subir.sh
#
# Cada peça só sobe se já não estiver no ar, então rodar duas vezes é seguro.
# Logs em $CASA_DEV_DIR/{pg,api,web}.log. Para derrubar: scripts/local/parar.sh.
set -uo pipefail
source "$(dirname "$0")/_config.sh"
casa_exportar_ambiente || exit 1
casa_checar_banco_unico || exit 1

echo "1/3 Postgres (porta $PG_PORT)..."
casa_subir_postgres || exit 1

echo "2/3 API (porta $API_PORTA)..."
if [[ -n "$(casa_pid_da_porta "$API_PORTA")" ]]; then
  echo "    já estava no ar"
else
  (cd "$CASA_REPO/api" && nohup "$PY" -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$API_PORTA" >"$CASA_DEV_DIR/api.log" 2>&1 &)
fi

echo "3/3 Painel (porta $WEB_PORTA)..."
if [[ -n "$(casa_pid_da_porta "$WEB_PORTA")" ]]; then
  echo "    já estava no ar"
else
  # Só no loopback: o sistema não vai para a rede (o `npm run dev` do Docker
  # escuta em 0.0.0.0 porque precisa sair do container).
  (cd "$CASA_REPO/web" && VITE_API_URL="http://127.0.0.1:$API_PORTA" nohup npx vite \
    --host 127.0.0.1 --port "$WEB_PORTA" --strictPort >"$CASA_DEV_DIR/web.log" 2>&1 &)
fi

for _ in $(seq 1 30); do
  curl -fs --max-time 2 "http://127.0.0.1:$API_PORTA/health" >/dev/null && break
  sleep 1
done
echo
echo "  painel : http://127.0.0.1:$WEB_PORTA"
echo "  API    : http://127.0.0.1:$API_PORTA/docs"
echo "  health : $(curl -s --max-time 5 "http://127.0.0.1:$API_PORTA/health" || echo 'sem resposta — ver api.log')"
