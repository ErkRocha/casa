#!/usr/bin/env bash
# Remove as tarefas agendadas criadas pelo agendar.sh.
#
#   bash scripts/local/desagendar.sh            # as duas
#   bash scripts/local/desagendar.sh sync       # só a sync (depois da migração
#                                               # para o Docker, D-17)
#   bash scripts/local/desagendar.sh relatorio  # só o relatório
#
# Só as do projeto, pelo nome. Tarefa que já não existe é pulada.
set -uo pipefail
source "$(dirname "$0")/_config.sh"

case "${1:-todas}" in
  todas) NOMES=("$CASA_TAREFA_SYNC" "$CASA_TAREFA_RELATORIO") ;;
  sync) NOMES=("$CASA_TAREFA_SYNC") ;;
  relatorio) NOMES=("$CASA_TAREFA_RELATORIO") ;;
  *) echo "uso: desagendar.sh [sync|relatorio]" >&2; exit 2 ;;
esac

for nome in "${NOMES[@]}"; do
  if schtasks //Query //TN "$nome" >/dev/null 2>&1; then
    schtasks //Delete //TN "$nome" //F >/dev/null && echo "removida: $nome"
  else
    echo "não existia: $nome"
  fi
done
