#!/usr/bin/env bash
# Derruba o que o `subir.sh` levantou. Os dados ficam no disco.
#
#   bash scripts/local/parar.sh
#
# Encerra só o processo que escuta em cada porta do projeto — e não todo
# `python` e `node` da máquina. O Postgres para com `pg_ctl stop -m fast`,
# que fecha as conexões e grava tudo antes de sair.
set -uo pipefail
source "$(dirname "$0")/_config.sh"

for porta in "$WEB_PORTA" "$API_PORTA"; do
  pid="$(casa_pid_da_porta "$porta")"
  if [[ -n "$pid" ]]; then
    taskkill //PID "$pid" //T //F >/dev/null 2>&1 && echo "porta $porta: processo $pid encerrado"
  fi
done

if casa_pg_pronto; then
  "$PG_BIN/pg_ctl.exe" -D "$PG_DATA" stop -m fast >/dev/null 2>&1 && echo "Postgres parado"
fi
echo "tudo parado. Os dados continuam em $PG_DATA"
