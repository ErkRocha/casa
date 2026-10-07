#!/usr/bin/env bash
# Monta o modo local sem Docker do zero, no Windows (Git Bash).
#
#   bash scripts/local/instalar.sh
#
# Pré-requisitos, uma vez só:
#   1. Python 3.12 e Node 20+ (o Node pode vir do winget, sem PATH).
#   2. Binários portáteis do PostgreSQL 16 (zip, sem instalação e sem admin):
#      https://www.enterprisedb.com/download-postgresql-binaries
#      Extraia a pasta `pgsql` dentro de $CASA_DEV_DIR (padrão:
#      ~/.controle-casa-dev), ou aponte LOCAL_PG_BIN para o `bin` dela.
#   3. `.env` na raiz (copie do `.env.example`) com POSTGRES_PASSWORD e
#      INSIGHTS_PASSWORD — ou LOCAL_POSTGRES_PASSWORD e LOCAL_INSIGHTS_PASSWORD,
#      se o modo local usar senhas diferentes das do Docker.
#
# Idempotente: o que já existe é mantido. Cria o cluster do Postgres, os
# bancos (o de verdade e o `_test`), o venv, instala as dependências da API e
# do web, aplica as migrations, cria a role read-only (D-11) e roda o seed.
set -uo pipefail
source "$(dirname "$0")/_config.sh"

falhar() { echo "ERRO: $*" >&2; exit 1; }

[[ -x "$PG_BIN/initdb.exe" ]] || falhar "não achei os binários do Postgres em $PG_BIN.
Baixe o zip em https://www.enterprisedb.com/download-postgresql-binaries e
extraia a pasta 'pgsql' em $CASA_DEV_DIR (ou defina LOCAL_PG_BIN)."
command -v python >/dev/null 2>&1 || falhar "Python não está no PATH."
casa_exportar_ambiente || exit 1
[[ -n "$INSIGHTS_SENHA" ]] || falhar "defina INSIGHTS_PASSWORD (ou LOCAL_INSIGHTS_PASSWORD) no .env."
mkdir -p "$CASA_DEV_DIR"

echo "1/6 Cluster do Postgres em $PG_DATA"
if [[ -f "$PG_DATA/PG_VERSION" ]]; then
  echo "    já existe"
else
  # A senha vai por arquivo temporário, nunca na linha de comando.
  senha_arquivo="$(mktemp "$CASA_DEV_DIR/.pwfile.XXXXXX")"
  trap 'rm -f "$senha_arquivo"' EXIT
  printf '%s' "$PG_SENHA" >"$senha_arquivo"
  "$PG_BIN/initdb.exe" -D "$PG_DATA" -U "$PG_USER" --pwfile="$senha_arquivo" \
    -A scram-sha-256 -E UTF8 --locale=C >"$CASA_DEV_DIR/initdb.log" 2>&1 \
    || falhar "initdb falhou; ver $CASA_DEV_DIR/initdb.log"
  rm -f "$senha_arquivo"
fi

echo "2/6 Postgres (porta $PG_PORT)"
casa_subir_postgres || exit 1

echo "3/6 Bancos $PG_DB e $PG_DB_TESTE"
for banco in "$PG_DB" "$PG_DB_TESTE"; do
  existe="$("$PG_BIN/psql.exe" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$banco'")"
  if [[ "$existe" == "1" ]]; then
    echo "    $banco já existe"
  else
    "$PG_BIN/createdb.exe" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" "$banco" \
      || falhar "createdb $banco falhou"
    echo "    $banco criado"
  fi
done

echo "4/6 Venv da API em $VENV"
[[ -x "$PY" ]] || python -m venv "$VENV" || falhar "não consegui criar o venv"
"$PY" -m pip install -q --upgrade pip || falhar "pip falhou"
(cd "$CASA_REPO/api" && "$PY" -m pip install -q -e ".[dev]") || falhar "pip install da API falhou"

echo "5/6 Dependências do web"
if command -v npm >/dev/null 2>&1; then
  (cd "$CASA_REPO/web" && npm ci --no-audit --no-fund) || falhar "npm ci falhou"
else
  echo "    Node não encontrado: pule o painel ou instale o Node e rode de novo"
fi

echo "6/6 Migrations, role read-only e seed"
(
  cd "$CASA_REPO/api" \
    && "$PY" -m alembic upgrade head \
    && "$PY" -m scripts.aplicar_roles \
    && "$PY" -m app.seed
) || falhar "migrations, roles ou seed falharam"

echo
echo "Pronto. Para subir: bash scripts/local/subir.sh"
echo "Para usar pytest e os scripts no terminal: source scripts/local/ambiente.sh"
