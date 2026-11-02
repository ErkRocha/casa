#!/usr/bin/env bash
# O que as tarefas agendadas do Windows rodam (fase 5b, passo 10; fase 6).
#
#   bash scripts/local/tarefa.sh sync         # sync da Pluggy (todo dia, 6h)
#   bash scripts/local/tarefa.sh relatorio    # relatório do mês anterior (dia 1º, 7h)
#
# Quem agenda é o agendar.sh. Pode rodar à mão também: é o mesmo comando.
# Tudo vai para $CASA_DEV_DIR/agendador.log, uma seção por execução.
#
# Sobe o Postgres local se ele tiver caído (suspensão do Windows), com as
# mesmas recusas do subir.sh (D-17): banco do Docker no ar, porta ocupada por
# outro processo ou migração feita. Duas syncs nunca rodam juntas: a trava do
# Postgres recusa a segunda (scripts.pluggy_sync sai com código 3).
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

casa_exportar_ambiente || exit 1
casa_checar_banco_unico || exit 1
casa_subir_postgres || exit 1
# O `claude` do relatório com IA mora em ~/.local/bin; a tarefa do Windows
# não garante esse PATH.
export PATH="$HOME/.local/bin:$PATH"

cd "$CASA_REPO/api" || exit 1
# Só com a credencial de finanças (D-26): nada de administração.
unset DATABASE_ADMIN_URL TEST_DATABASE_URL COMPRAS_DONO_DATABASE_URL PGPASSWORD

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
