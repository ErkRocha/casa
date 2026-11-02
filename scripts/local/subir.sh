#!/usr/bin/env bash
# Sobe o Controle de Casa sem Docker: Postgres local, API, compras e painel.
#
#   bash scripts/local/subir.sh
#
# Cada peça só sobe se já não estiver no ar, então rodar duas vezes é seguro.
# Logs em $CASA_DEV_DIR/{pg,api,compras,web}.log. Para derrubar:
# scripts/local/parar.sh.
set -uo pipefail
source "$(dirname "$0")/_config.sh"
casa_exportar_ambiente || exit 1
casa_checar_banco_unico || exit 1

echo "1/4 Postgres (porta $PG_PORT)..."
casa_subir_postgres || exit 1

echo "2/4 API (porta $API_PORTA)..."
if [[ -n "$(casa_pid_da_porta "$API_PORTA")" ]]; then
  echo "    já estava no ar"
else
  (cd "$CASA_REPO/api" && nohup "$PY" -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$API_PORTA" >"$CASA_DEV_DIR/api.log" 2>&1 &)
fi

echo "3/4 Compras (porta $COMPRAS_PORTA)..."
if [[ -n "$(casa_pid_da_porta "$COMPRAS_PORTA")" ]]; then
  echo "    já estava no ar"
elif [[ -z "${COMPRAS_DATABASE_URL:-}" ]]; then
  echo "    pulado: defina COMPRAS_DB_PASSWORD no .env e rode scripts/local/compras-preparar.sh"
else
  # Só com a credencial da própria role (D-25): o processo não herda a URL
  # dona do banco nem as senhas de finanças. O prefixo é o do painel, como no
  # compose: o /docs funciona em /api/compras/docs pelo Vite. O
  # MSYS2_ENV_CONV_EXCL impede o Git Bash de converter o valor, que parece
  # caminho, em "C:/Program Files/Git/api/compras".
  (cd "$CASA_REPO/compras" && nohup env -u DATABASE_URL -u TEST_DATABASE_URL \
    -u COMPRAS_DONO_DATABASE_URL -u PGPASSWORD -u INSIGHTS_PASSWORD \
    MSYS2_ENV_CONV_EXCL=COMPRAS_ROOT_PATH COMPRAS_ROOT_PATH=/api/compras \
    "$PY" -m uvicorn compras.main:app \
    --host 127.0.0.1 --port "$COMPRAS_PORTA" >"$CASA_DEV_DIR/compras.log" 2>&1 &)
fi

echo "4/4 Painel (porta $WEB_PORTA)..."
if [[ -n "$(casa_pid_da_porta "$WEB_PORTA")" ]]; then
  echo "    já estava no ar"
else
  # Só no loopback: o sistema não vai para a rede (o `npm run dev` do Docker
  # escuta em 0.0.0.0 porque precisa sair do container). O painel chama /api
  # e /api/compras na mesma origem, e o Vite repassa (D-18, D-25).
  (cd "$CASA_REPO/web" && API_PROXY_TARGET="http://127.0.0.1:$API_PORTA" \
    COMPRAS_PROXY_TARGET="http://127.0.0.1:$COMPRAS_PORTA" nohup npx vite \
    --host 127.0.0.1 --port "$WEB_PORTA" --strictPort >"$CASA_DEV_DIR/web.log" 2>&1 &)
fi

for _ in $(seq 1 30); do
  curl -fs --max-time 2 "http://127.0.0.1:$API_PORTA/health" >/dev/null && break
  sleep 1
done
if [[ -n "${COMPRAS_DATABASE_URL:-}" ]]; then
  for _ in $(seq 1 15); do
    curl -fs --max-time 2 "http://127.0.0.1:$COMPRAS_PORTA/health" >/dev/null && break
    sleep 1
  done
fi
echo
echo "  painel  : http://127.0.0.1:$WEB_PORTA"
echo "  API     : http://127.0.0.1:$API_PORTA/docs"
echo "  compras : http://127.0.0.1:$WEB_PORTA/api/compras/docs"
echo "  health  : $(curl -s --max-time 5 "http://127.0.0.1:$API_PORTA/health" || echo 'sem resposta — ver api.log')"
if [[ -n "${COMPRAS_DATABASE_URL:-}" ]]; then
  echo "  compras : $(curl -s --max-time 5 "http://127.0.0.1:$COMPRAS_PORTA/health" || echo 'sem resposta — ver compras.log')"
fi
