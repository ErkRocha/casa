#!/usr/bin/env bash
# Migra o banco do modo local (scripts/local/) para o Docker (D-17).
#
#   bash scripts/migrar_para_docker.sh
#
# Roda uma vez, com o Docker Desktop instalado e no ar. Para no primeiro erro
# e diz em qual etapa:
#
#   a. docker   — `docker info` responde e há `make`;
#   b. backup   — pg_dump do banco local (formato custom) e contagem das
#                 tabelas principais, ambos em backups/;
#   c. versao   — o Postgres local não é mais novo que o da imagem do compose
#                 (pg_restore não volta de versão mais nova para mais velha);
#   d. parar    — para o ambiente local; a pasta de dados fica;
#   e. restore  — sobe só o db, confere que ele está vazio, restaura o dump e
#                 roda `make roles` (senha de insights do .env);
#   f. contagens— PORTÃO: as contagens no container têm que ser idênticas às
#                 do passo b; diferente, para sem apagar nada;
#   g. validar  — sobe tudo e roda `make validar`;
#   h. sync     — `make sync simular=1`: credenciais da Pluggy no container e
#                 nada duplicado.
#
# Passado o portão f, grava o marcador que faz o scripts/local/subir.sh
# recusar o banco local, que vira cópia congelada.
#
# Variáveis: COMPOSE (padrão "docker compose"), MAKE (padrão "make"),
# MIGRAR_BACKUPS (padrão backups/). O resto vem do .env, como no modo local.

set -uo pipefail
cd "$(dirname "$0")/.."
source scripts/local/_config.sh

COMPOSE="${COMPOSE:-docker compose}"
MAKE="${MAKE:-make}"
BACKUPS="${MIGRAR_BACKUPS:-backups}"
TS="$(date +%Y%m%d_%H%M%S)"
DUMP="$BACKUPS/casa_local_${TS}.dump"
CONTAGENS="$BACKUPS/contagens_local_${TS}.txt"
TABELAS=(pessoas contas formas_pagamento categorias transacoes importacoes
  importacao_itens contas_pluggy regras_categorizacao auditoria)

# Sem `declare -A`, como no validar.sh: o bash do macOS é o 3.2.
ETAPAS=(docker backup versao parar restore contagens validar sync)
marcar() { printf -v "RES_$1" '%s' "$2"; }
for e in "${ETAPAS[@]}"; do marcar "$e" "não executada"; done
VERSAO_LOCAL="?"
VERSAO_COMPOSE="?"

resumo() {
  echo
  echo "== migrar: resumo =="
  for e in "${ETAPAS[@]}"; do
    var="RES_$e"
    printf "  %-10s %s\n" "$e" "${!var}"
  done
  echo "  postgres   local $VERSAO_LOCAL, compose $VERSAO_COMPOSE"
  if [[ -s "$DUMP" ]]; then
    echo "  arquivo    dump em $DUMP"
    echo "  arquivo    contagens em $CONTAGENS"
  else
    echo "  arquivo    dump não gerado"
  fi
}

falhou() {
  marcar "$1" "FALHOU"
  echo
  echo "!! etapa '$1' falhou — parando aqui. ${2:-}" >&2
  resumo
  exit 1
}

ok() { marcar "$1" "OK"; }
etapa() { echo; echo "== migrar: $1 =="; }

# Uma contagem por linha, "tabela=n", na ordem de TABELAS.
contar_local() {
  local t n
  for t in "${TABELAS[@]}"; do
    n="$("$PG_BIN/psql.exe" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -tAc \
      "SELECT count(*) FROM $t")" || return 1
    echo "$t=${n//[[:space:]]/}"
  done
}

contar_container() {
  local t n
  for t in "${TABELAS[@]}"; do
    # Aspas simples: usuário e banco vêm do ambiente do próprio container.
    n="$($COMPOSE exec -T db sh -c \
      "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc 'SELECT count(*) FROM $t'")" || return 1
    echo "$t=${n//[[:space:]]/}"
  done
}

if [[ -f "$CASA_MARCADOR_MIGRACAO" ]]; then
  echo "A migração já foi feita: $(head -n 1 "$CASA_MARCADOR_MIGRACAO")." >&2
  echo "O banco local é cópia congelada (D-17); rodar de novo não é seguro." >&2
  exit 1
fi

# --- a. docker -----------------------------------------------------------------
etapa "Docker e make"
docker info >/dev/null 2>&1 || falhou docker "O Docker não respondeu: abra o Docker Desktop e espere ficar 'running'."
command -v "${MAKE%% *}" >/dev/null 2>&1 \
  || falhou docker "Não achei '$MAKE'. No Windows: winget install ezwinports.make (ou rode com MAKE=<caminho>)."
ok docker

# --- b. backup -----------------------------------------------------------------
etapa "backup do banco local"
casa_exportar_ambiente || falhou backup
casa_subir_postgres || falhou backup "O Postgres local não subiu."
mkdir -p "$BACKUPS"
"$PG_BIN/pg_dump.exe" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -Fc -f "$DUMP" \
  || { rm -f "$DUMP"; falhou backup "pg_dump falhou."; }
[[ -s "$DUMP" ]] || { rm -f "$DUMP"; falhou backup "o dump saiu vazio."; }
contar_local >"$CONTAGENS" || falhou backup "não consegui contar as tabelas locais."
echo "dump em $DUMP ($(wc -c <"$DUMP") bytes)"
sed 's/^/  /' "$CONTAGENS"
ok backup

# --- c. versão -----------------------------------------------------------------
etapa "versão do Postgres"
num="$("$PG_BIN/psql.exe" -h 127.0.0.1 -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -tAc \
  "SHOW server_version_num")" || falhou versao
num="${num//[[:space:]]/}"
VERSAO_LOCAL="$((num / 10000))"
VERSAO_COMPOSE="$(sed -n 's/^[[:space:]]*image:[[:space:]]*postgres:\([0-9][0-9]*\).*/\1/p' docker-compose.yml | head -n 1)"
[[ -n "$VERSAO_COMPOSE" ]] || falhou versao "não achei a imagem do Postgres no docker-compose.yml."
echo "local $VERSAO_LOCAL ($num), compose $VERSAO_COMPOSE"
if ((VERSAO_LOCAL > VERSAO_COMPOSE)); then
  falhou versao "O Postgres local ($VERSAO_LOCAL) é mais novo que o do compose ($VERSAO_COMPOSE): o restore não é suportado."
fi
ok versao

# --- d. parar o local ------------------------------------------------------------
etapa "parando o ambiente local (os dados ficam em $PG_DATA)"
bash scripts/local/parar.sh || falhou parar
if casa_pg_pronto; then falhou parar "o Postgres local continua respondendo."; fi
ok parar

# --- e. restore no container ---------------------------------------------------------
etapa "restore no container"
$COMPOSE up -d --wait db || falhou restore "o container do db não subiu."
tabelas="$($COMPOSE exec -T db sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM pg_tables WHERE schemaname = 'public'\"")" \
  || falhou restore "não consegui consultar o banco do container."
tabelas="${tabelas//[[:space:]]/}"
if [[ "$tabelas" != "0" ]]; then
  falhou restore "O banco do container já tem $tabelas tabela(s). Nada foi sobrescrito; confira o volume antes de migrar."
fi
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error' <"$DUMP" \
  || falhou restore "pg_restore falhou. O dump continua em $DUMP."
$MAKE --no-print-directory roles || falhou restore "make roles falhou."
ok restore

# --- f. PORTÃO: contagens ------------------------------------------------------------
etapa "contagens no container x local"
contar_container >"$CONTAGENS.container" || falhou contagens "não consegui contar no container."
if ! diferencas="$(diff "$CONTAGENS" "$CONTAGENS.container")"; then
  echo "$diferencas" | sed 's/^/  /'
  falhou contagens "As contagens não batem. Nada foi apagado: o local está parado e intacto, e o dump em $DUMP."
fi
echo "as ${#TABELAS[@]} tabelas batem"
ok contagens
# Daqui em diante o banco do Docker é o ativo; o local, cópia congelada.
echo "migrado para o Docker em $(date '+%d/%m/%Y %H:%M'); dump $DUMP" >"$CASA_MARCADOR_MIGRACAO"

# --- g. validar ------------------------------------------------------------------
etapa "subindo tudo e validando"
$COMPOSE up -d --build || falhou validar "docker compose up falhou."
MAKE="$MAKE" $MAKE --no-print-directory validar || falhou validar
ok validar

# --- h. sync simulada ----------------------------------------------------------------
etapa "sync da Pluggy em simulação"
$MAKE --no-print-directory sync simular=1 || falhou sync
ok sync

resumo
echo
echo "Migração concluída. O banco local é cópia congelada desde agora (D-17)."
