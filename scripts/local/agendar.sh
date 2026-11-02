#!/usr/bin/env bash
# Cria as tarefas agendadas do Windows do modo local (fase 5b, passo 10; fase 6).
#
#   bash scripts/local/agendar.sh            # cria ou atualiza as duas tarefas
#   bash scripts/local/agendar.sh --listar   # só mostra como estão
#
# No nível do usuário, sem administrador: o `schtasks` sem /RU cria a tarefa
# para quem está logado, e ela roda com o usuário logado (o PC de casa fica
# ligado e com a sessão aberta, D-17). Rodar de novo atualiza (/F).
#
#   ControleCasa-Sync       todo dia às 06:00 (SYNC_AGENDA): sync da Pluggy,
#                           só no modo local (no Docker é o serviço `agendador`)
#   ControleCasa-Relatorio  todo dia 1º às 07:00: relatório do mês anterior
#
# Para remover as duas: bash scripts/local/desagendar.sh
# O log das execuções: ~/.controle-casa-dev/agendador.log
set -uo pipefail
source "$(dirname "$0")/_config.sh"

listar() {
  for nome in "$CASA_TAREFA_SYNC" "$CASA_TAREFA_RELATORIO"; do
    echo "--- $nome"
    schtasks //Query //TN "$nome" //V //FO LIST 2>&1 \
      | grep -E "^(Nome da tarefa|TaskName|Hora da próxima|Next Run|Status|Tarefa a ser executada|Task To Run|Tipo de agendamento|Schedule Type|Hora de início|Start Time)" \
      || echo "    (não existe)"
  done
}

if [[ "${1:-}" == "--listar" ]]; then
  listar
  exit 0
fi

# O bash.exe do Git for Windows (a raiz "/" do Git Bash é a pasta do Git).
BASH_EXE="$(cygpath -w /)bin\\bash.exe"
[[ -f "$(cygpath -u "$BASH_EXE")" ]] || { echo "bash.exe não encontrado em $BASH_EXE" >&2; exit 1; }
TAREFA="$(cygpath -w "$CASA_REPO/scripts/local/tarefa.sh")"
comando() { printf '"%s" -l "%s" %s' "$BASH_EXE" "$TAREFA" "$1"; }

# O /TR do schtasks aceita no máximo 261 caracteres.
for t in sync relatorio; do
  cmd="$(comando "$t")"
  if (( ${#cmd} > 261 )); then
    echo "O caminho do repositório é longo demais para a tarefa: $cmd" >&2
    exit 1
  fi
done

# Depois da migração para o Docker (D-17), a sync é do serviço `agendador` do
# compose: aqui fica só o relatório, que usa o `claude` do host.
if [[ -f "$CASA_MARCADOR_MIGRACAO" ]]; then
  echo "Modo Docker: a sync diária é do serviço 'agendador'; só o relatório é agendado aqui."
else
  schtasks //Create //F //TN "$CASA_TAREFA_SYNC" //SC DAILY //ST "$CASA_SYNC_HORA" \
    //TR "$(comando sync)" || { echo "não consegui criar $CASA_TAREFA_SYNC" >&2; exit 1; }
fi
schtasks //Create //F //TN "$CASA_TAREFA_RELATORIO" //SC MONTHLY //D 1 //ST 07:00 \
  //TR "$(comando relatorio)" || { echo "não consegui criar $CASA_TAREFA_RELATORIO" >&2; exit 1; }

echo
listar
echo
echo "Pronto. O painel mostra a próxima sync depois de reiniciar a API (parar.sh e subir.sh)."
