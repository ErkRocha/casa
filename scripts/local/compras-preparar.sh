#!/usr/bin/env bash
# Prepara o serviço de compras no modo local (D-25): role e schema, migrations
# e seed. O equivalente sem Docker de `make compras-role compras-migrate
# compras-seed`.
#
#   bash scripts/local/compras-preparar.sh
#
# Idempotente: rodar de novo repara a role, aplica só a migration que faltar
# e acrescenta só a seção ou o produto que faltar. O Postgres precisa estar
# no ar (scripts/local/subir.sh).
set -uo pipefail
source "$(dirname "$0")/_config.sh"
casa_exportar_ambiente || exit 1

if [[ -z "${COMPRAS_DATABASE_URL:-}" ]]; then
  echo "Defina COMPRAS_DB_PASSWORD (ou LOCAL_COMPRAS_PASSWORD) no .env." >&2
  exit 1
fi
casa_pg_pronto || { echo "O Postgres não está no ar: rode scripts/local/subir.sh." >&2; exit 1; }

cd "$CASA_REPO/compras" || exit 1
echo "1/3 Role casa_compras e schema compras (credencial dona do banco)..."
"$PY" -m scripts.aplicar_role || exit 1

# Daqui em diante, só com a credencial da role.
unset DATABASE_URL DATABASE_ADMIN_URL TEST_DATABASE_URL COMPRAS_DONO_DATABASE_URL PGPASSWORD
echo "2/3 Migrations..."
"$PY" -m alembic upgrade head || exit 1
echo "3/3 Seed..."
"$PY" -m compras.seed || exit 1
