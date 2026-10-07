# Configuração comum do modo local sem Docker (Windows, Git Bash).
#
# Incluído pelos outros scripts desta pasta com `source`; não roda sozinho.
# Lê o `.env` da raiz sem sobrescrever o que já estiver no ambiente, e deriva
# o resto. Nenhuma senha mora aqui: elas vêm do `.env`, que fica fora do git.
#
# Variáveis próprias do modo local (todas opcionais, no `.env` ou no ambiente):
#
#   CASA_DEV_DIR             pasta do ambiente: binários do Postgres, dados,
#                            venv e logs. Padrão: ~/.controle-casa-dev
#   LOCAL_PG_BIN             binários do Postgres. Padrão: $CASA_DEV_DIR/pgsql/bin
#   LOCAL_PG_PORT            porta do Postgres. Padrão: 55432 (não briga com o
#                            5432 de um Postgres instalado ou do Docker)
#   LOCAL_POSTGRES_PASSWORD  senha do usuário dono. Padrão: POSTGRES_PASSWORD
#   LOCAL_INSIGHTS_PASSWORD  senha da role read-only. Padrão: INSIGHTS_PASSWORD
#   LOCAL_API_PORT           padrão: API_PORT, ou 8000
#   LOCAL_WEB_PORT           padrão: WEB_PORT, ou 5173

CASA_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

_casa_ler_env() {
  local arquivo="$CASA_REPO/.env" linha chave valor
  [[ -f "$arquivo" ]] || return 0
  while IFS= read -r linha || [[ -n "$linha" ]]; do
    linha="${linha%$'\r'}"
    [[ "$linha" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    chave="${BASH_REMATCH[1]}"
    valor="${BASH_REMATCH[2]}"
    # Aspas em volta saem; o resto fica como está.
    if [[ "$valor" =~ ^\"(.*)\"$ || "$valor" =~ ^\'(.*)\'$ ]]; then
      valor="${BASH_REMATCH[1]}"
    fi
    # O que já está no ambiente vence o arquivo.
    [[ -z "${!chave+x}" ]] && export "$chave=$valor"
  done <"$arquivo"
}
_casa_ler_env

CASA_DEV_DIR="${CASA_DEV_DIR:-$HOME/.controle-casa-dev}"
PG_BIN="${LOCAL_PG_BIN:-$CASA_DEV_DIR/pgsql/bin}"
PG_DATA="$CASA_DEV_DIR/pgdata"
PG_LOG="$CASA_DEV_DIR/pg.log"
PG_PORT="${LOCAL_PG_PORT:-55432}"
PG_USER="${POSTGRES_USER:-casa}"
PG_DB="${POSTGRES_DB:-casa}"
PG_DB_TESTE="${PG_DB}_test"
PG_SENHA="${LOCAL_POSTGRES_PASSWORD:-${POSTGRES_PASSWORD:-}}"
INSIGHTS_SENHA="${LOCAL_INSIGHTS_PASSWORD:-${INSIGHTS_PASSWORD:-}}"
API_PORTA="${LOCAL_API_PORT:-${API_PORT:-8000}}"
WEB_PORTA="${LOCAL_WEB_PORT:-${WEB_PORT:-5173}}"
VENV="$CASA_DEV_DIR/venv"
PY="$VENV/Scripts/python.exe"

# Node: o do PATH, ou o que o winget instala sem mexer no PATH.
if ! command -v node >/dev/null 2>&1; then
  for _casa_node in "$LOCALAPPDATA"/Microsoft/WinGet/Packages/OpenJS.NodeJS.LTS_*/node-*-win-x64; do
    [[ -x "$_casa_node/node.exe" ]] && export PATH="$_casa_node:$PATH" && break
  done
fi

_casa_urlencode() {
  # Senha com `@`, `:` ou `/` quebraria a URL do banco.
  python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

casa_exportar_ambiente() {
  if [[ -z "$PG_SENHA" ]]; then
    echo "Defina POSTGRES_PASSWORD (ou LOCAL_POSTGRES_PASSWORD) no .env." >&2
    return 1
  fi
  local senha
  senha="$(_casa_urlencode "$PG_SENHA")" || return 1
  export DATABASE_URL="postgresql+psycopg://$PG_USER:$senha@127.0.0.1:$PG_PORT/$PG_DB"
  # Banco truncado entre testes: nunca o de verdade.
  export TEST_DATABASE_URL="postgresql+psycopg://$PG_USER:$senha@127.0.0.1:$PG_PORT/$PG_DB_TESTE"
  export INSIGHTS_PASSWORD="$INSIGHTS_SENHA"
  export PGPASSWORD="$PG_SENHA"
}

casa_pg_pronto() {
  "$PG_BIN/pg_isready.exe" -h 127.0.0.1 -p "$PG_PORT" -q
}

# PID do processo que escuta na porta (netstat do Windows), ou vazio.
casa_pid_da_porta() {
  netstat -ano 2>/dev/null | awk -v porta=":$1" \
    '$4 == "LISTENING" && substr($2, length($2) - length(porta) + 1) == porta { print $5; exit }'
}

# Sobe o Postgres se ele não estiver no ar e espera responder.
casa_subir_postgres() {
  if casa_pg_pronto; then
    echo "    já estava no ar"
    return 0
  fi
  # Em segundo plano e com a saída no log: o processo do servidor herda o
  # terminal, e sem isto o `pg_ctl` prende a janela até o Postgres parar.
  "$PG_BIN/pg_ctl.exe" -D "$PG_DATA" -l "$PG_LOG" \
    -o "-p $PG_PORT -c listen_addresses=127.0.0.1" start >/dev/null 2>&1 &
  for _ in $(seq 1 30); do casa_pg_pronto && break; sleep 1; done
  if ! casa_pg_pronto; then
    echo "    o Postgres não respondeu em 30 s. Fim do log ($PG_LOG):" >&2
    tail -n 15 "$PG_LOG" >&2
    return 1
  fi
  # Subiu depois de uma queda? O log diz; o Postgres se recupera sozinho.
  if tail -n 40 "$PG_LOG" | grep -q "not properly shut down\|não foi desligado corretamente"; then
    echo "    aviso: o Postgres tinha caído sem desligar e se recuperou sozinho (ver $PG_LOG)"
  fi
}
