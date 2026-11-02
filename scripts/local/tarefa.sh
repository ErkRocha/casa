#!/usr/bin/env bash
# O que as tarefas agendadas do Windows rodam (fase 5b, passo 10; fase 6).
#
#   bash scripts/local/tarefa.sh relatorio    # relatório do mês anterior (dia 1º, 7h)
#   bash scripts/local/tarefa.sh sync         # sync da Pluggy (só no modo local)
#
# Quem agenda é o agendar.sh. Pode rodar à mão também: é o mesmo comando.
# Tudo vai para $CASA_DEV_DIR/agendador.log, uma seção por execução.
#
# Depois da migração para o Docker (D-17, marcador em $CASA_MARCADOR_MIGRACAO):
#   - relatorio: roda no host (usa o `claude` logado na máquina) contra o banco
#     do Docker, pela URL que scripts/_host.py monta com o .env (127.0.0.1 e a
#     porta publicada do compose). Nada do banco local é tocado.
#   - sync: recusada. A sync diária é do serviço `agendador` do compose.
#
# No modo local (antes da migração), sobe o Postgres local se ele tiver caído,
# com as mesmas recusas do subir.sh.
set -uo pipefail
source "$(dirname "$0")/_config.sh"

TAREFA="${1:-}"
LOG="$CASA_DEV_DIR/agendador.log"
mkdir -p "$CASA_DEV_DIR"
exec >>"$LOG" 2>&1
echo
echo "== $(date '+%d/%m/%Y %H:%M:%S') tarefa: ${TAREFA:-(nenhuma)} =="

case "$TAREFA" in
  sync | relatorio) ;;
  *)
    echo "uso: tarefa.sh sync|relatorio"
    exit 2
    ;;
esac

# O `claude` do relatório com IA mora em ~/.local/bin; a tarefa do Windows
# não garante esse PATH.
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$CASA_MARCADOR_MIGRACAO" ]]; then
  # --- modo Docker (D-17) ---------------------------------------------------
  if [[ "$TAREFA" == "sync" ]]; then
    echo "RECUSADO: depois da migração a sync diária é do serviço 'agendador' do compose."
    echo "Remova esta tarefa: bash scripts/local/desagendar.sh sync"
    exit 1
  fi
  rodando="$(docker ps --filter "name=^casa_db$" --filter status=running --format '{{.Names}}' 2>/dev/null)"
  if [[ -z "$rodando" ]]; then
    echo "o container do banco (casa_db) não está rodando: abra o Docker Desktop."
    exit 1
  fi
  # Sem nada do modo local no ambiente: a URL sai do .env, para o Docker.
  unset DATABASE_URL DATABASE_ADMIN_URL TEST_DATABASE_URL PGPASSWORD
else
  # --- modo local --------------------------------------------------------------
  casa_exportar_ambiente || exit 1
  casa_checar_banco_unico || exit 1
  casa_subir_postgres || exit 1
  # Só com a credencial de finanças (D-26): nada de administração.
  unset DATABASE_ADMIN_URL TEST_DATABASE_URL COMPRAS_DONO_DATABASE_URL PGPASSWORD
fi

cd "$CASA_REPO/api" || exit 1

case "$TAREFA" in
  sync)
    "$PY" -m scripts.pluggy_sync
    ;;
  relatorio)
    # O mês anterior ao de hoje: no dia 1º, o mês que acabou de fechar.
    competencia="$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m)"
    echo "relatório de $competencia (claude: $(command -v claude || echo 'não encontrado'))"
    "$PY" -m scripts.relatorio --competencia "$competencia"
    ;;
esac
codigo=$?
echo "== fim: código $codigo =="
exit "$codigo"
