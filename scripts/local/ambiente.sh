# Exporta, no terminal atual, as variáveis do modo local.
#
#   source scripts/local/ambiente.sh
#
# Com `source`, e não `bash`: um script rodado com `bash` exporta para um
# processo filho que morre no fim, e o terminal continua sem nada. Depois
# disto, `cd api && pytest`, `python -m scripts.relatorio` e os outros
# scripts falam com o Postgres local e com a role read-only certa.
#
# Exporta DATABASE_URL, TEST_DATABASE_URL (banco `_test`, truncado entre
# testes), INSIGHTS_PASSWORD e PGPASSWORD.
source "$(dirname "${BASH_SOURCE[0]}")/_config.sh"
if casa_exportar_ambiente; then
  echo "ambiente local: Postgres 127.0.0.1:$PG_PORT, banco $PG_DB (testes em $PG_DB_TESTE)"
fi
