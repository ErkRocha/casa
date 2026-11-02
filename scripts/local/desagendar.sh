#!/usr/bin/env bash
# Remove as tarefas agendadas criadas pelo agendar.sh.
#
#   bash scripts/local/desagendar.sh
#
# Só as duas do projeto, pelo nome. Tarefa que já não existe é pulada.
# Depois, reinicie a API (parar.sh e subir.sh) para o painel voltar a dizer
# que a atualização é manual.
set -uo pipefail
source "$(dirname "$0")/_config.sh"

for nome in "$CASA_TAREFA_SYNC" "$CASA_TAREFA_RELATORIO"; do
  if schtasks //Query //TN "$nome" >/dev/null 2>&1; then
    schtasks //Delete //TN "$nome" //F >/dev/null && echo "removida: $nome"
  else
    echo "não existia: $nome"
  fi
done
