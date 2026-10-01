#!/usr/bin/env bash
# Valida o ambiente de ponta a ponta, com backup antes de tocar no schema.
#
# Chamado por `make validar`. Roda as etapas em ordem e para na primeira que
# falhar — migration aplicada em cima de banco que não subiu direito é o tipo
# de erro que só aparece depois, e longe da causa.
#
# O backup vem primeiro de propósito: se a migration der problema, o caminho
# de volta é restaurar o arquivo impresso no resumo (README, "Subindo").

set -uo pipefail

COMPOSE="docker compose"
MAKE="${MAKE:-make}"
HEALTH_TIMEOUT="${VALIDAR_TIMEOUT:-120}"

cd "$(dirname "$0")/.."

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP="backups/casa_${TS}.dump"
LOG_TESTES="$(mktemp)"
trap 'rm -f "$LOG_TESTES"' EXIT

# Resultado por etapa em RES_<etapa>. Sem `declare -A` de propósito: o bash
# do macOS é o 3.2, que não tem array associativo.
ETAPAS=(backup build health migrate roles lint test)
marcar() { printf -v "RES_$1" '%s' "$2"; }
for e in "${ETAPAS[@]}"; do marcar "$e" "não executada"; done
TESTES="?"

resumo() {
  echo
  echo "== validar: resumo =="
  for e in "${ETAPAS[@]}"; do
    var="RES_$e"
    printf "  %-8s %s\n" "$e" "${!var}"
  done
  echo "  testes   $TESTES"
  if [[ -s "$BACKUP" ]]; then
    echo "  backup   $BACKUP"
  else
    echo "  backup   (não gerado)"
  fi
}

falhou() {
  marcar "$1" "FALHOU"
  echo
  echo "!! etapa '$1' falhou — parando aqui." >&2
  resumo
  if [[ -s "$BACKUP" ]]; then
    echo
    echo "Para voltar o banco ao estado de antes: README, seção \"Subindo\"," \
      "em \"Restaurando o backup\"."
  fi
  exit 1
}

ok() { marcar "$1" "OK"; }

etapa() { echo; echo "== validar: $1 =="; }

# --- a. backup -------------------------------------------------------------
etapa "backup do banco atual"
mkdir -p backups
if ! $COMPOSE ps --status running --services 2>/dev/null | grep -qx db; then
  echo "container do banco parado; subindo só o db"
  $COMPOSE up -d --wait db || falhou backup
fi
# Formato custom (-Fc): comprimido e restaurável com pg_restore. Usuário e
# banco vêm do ambiente do próprio container, o mesmo que o compose montou.
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$BACKUP" \
  || { rm -f "$BACKUP"; falhou backup; }
[[ -s "$BACKUP" ]] || { rm -f "$BACKUP"; falhou backup; }
echo "backup em $BACKUP ($(wc -c <"$BACKUP") bytes)"
ok backup

# --- b. rebuild e subida ---------------------------------------------------
etapa "rebuild e subida dos containers"
$COMPOSE up -d --build || falhou build
ok build

# --- c. espera pelo /health ------------------------------------------------
# Pergunta de dentro do container da api (a imagem tem curl): não depende de
# curl no host nem de saber qual porta foi publicada.
etapa "esperando /health com banco ok (até ${HEALTH_TIMEOUT}s)"
inicio=$SECONDS
until $COMPOSE exec -T api curl -fsS http://127.0.0.1:8000/health 2>/dev/null \
  | grep -q '"banco":"ok"'; do
  if (( SECONDS - inicio >= HEALTH_TIMEOUT )); then
    echo "sem resposta saudável em ${HEALTH_TIMEOUT}s" >&2
    falhou health
  fi
  sleep 2
done
echo "api saudável em $(( SECONDS - inicio ))s"
ok health

# --- d..g. alvos do próprio Makefile ---------------------------------------
etapa "make migrate"
$MAKE --no-print-directory migrate || falhou migrate
ok migrate

etapa "make roles"
$MAKE --no-print-directory roles || falhou roles
ok roles

etapa "make lint"
$MAKE --no-print-directory lint || falhou lint
ok lint

etapa "make test"
$MAKE --no-print-directory test 2>&1 | tee "$LOG_TESTES"
status_teste=${PIPESTATUS[0]}
# Linha final do pytest -q: "189 passed, 2 skipped in 14.2s".
TESTES="$(grep -Eo '[0-9]+ passed' "$LOG_TESTES" | tail -1 || true)"
TESTES="${TESTES:-0 passed}"
falhas="$(grep -Eo '[0-9]+ (failed|errors?)' "$LOG_TESTES" | tail -2 | paste -sd ',' - || true)"
[[ -n "$falhas" ]] && TESTES="$TESTES, $falhas"
(( status_teste == 0 )) || falhou test
ok test

resumo
