# Progresso da execução autônoma (02/11/2026)

Arquivo de retomada: se a sessão cair, leia este arquivo e o `git log`, e
continue da primeira fase que não está "OK" nem "bloqueada".

| Fase | Status | Commit |
|---|---|---|
| 0 — Estado inicial | OK | — |
| 1 — Telas da lista de compras | **bloqueada** | — |
| 2 — Finanças sem superusuário (D-26) | OK | ver abaixo |
| 3 — Identidade pelo Tailscale | **bloqueada** (depende da 1) | — |
| 4 — Sincronização e relatório automáticos | OK | ver abaixo |
| 5 — NFC-e e preços (backend) | pendente | — |
| 6 — Lista pela voz (MCP do vault) | **bloqueada** | — |

## Fase 0

- `git pull`: já atualizado (`d8c4d1d`). Ambiente local no ar; os dois
  `/health` ok.
- Nenhuma das fases 1 a 6 estava feita (nem D-26, nem progresso anterior).

## Fase 1 — bloqueada

`docs/design/COMPRAS.md` não existe. Na raiz do repositório há um
`design-compras.zip` não versionado (8,7 KB, de 02/11/2026 01:23) com
`design/COMPRAS.md` e as pranchetas `ComprasListaCelular`,
`ComprasDespensaCelular` e `ComprasAdicionarCelular`. Ele **não foi
extraído**: a regra da fase 0 manda bloquear sem o arquivo em
`docs/design/`, e pôr o desenho no lugar é decisão do usuário (D-15).
Para destravar: extrair o zip em `docs/` (fica `docs/design/COMPRAS.md` e
`docs/design/telas/Compras*.dc.html`) e rodar a fase 1 de novo.

Consequência: a fase 3 (depende da 1) e a fase 6 (depende da 1 e da 2)
ficam bloqueadas.

## Fase 6 — bloqueada

Além da fase 1, o servidor MCP do vault não existe em
`C:\Users\erikf\segundo-cerebro\servidor`.

## Fase 2 — OK

- Backup antes: `backups/casa_20261102_013146_antes_d26.dump` (3,9 MB, 21
  tabelas com dados, conferido com `pg_restore --list`).
- `api/scripts/aplicar_role_financas.py` aplicado no banco real: 29 objetos
  mudaram de dono para `casa_financas`; a verificação do script (não cria
  role, não altera insights, não escreve em compras, 0 objetos fora de
  posse) passou. `scripts.aplicar_roles` (insights só leitura) e o
  `aplicar_role` do compras (0 objetos fora do schema) também.
- A API sobe como `casa_financas` (conferido em `pg_stat_activity`); os dois
  `/health` ok.
- Nova senha `FINANCAS_DB_PASSWORD` gerada no `.env` (fora do git).
- Testes: finanças 758 passados, 0 pulados (8 novos em
  `tests/test_roles_financas.py`); compras 51, 0 pulados; web typecheck,
  lint e build ok.
- Docker escrito, não executado: `api` com `casa_financas`, serviço
  `api-admin` (perfil ferramentas) para `make roles` e `make financas-role`,
  `make reset` e `make validar` com a role antes das migrations, e o
  `migrar_para_docker.sh` cria os donos do dump antes do restore.

## Fase 4 — OK

- Backup antes da sync real: `backups/casa_20261102_092225_antes_fase4.dump`
  (3,9 MB, 21 tabelas com dados).
- Sync real pelo `scripts/local/tarefa.sh sync`, duas vezes seguidas: as
  duas com código 0 e 0 itens novos (idempotente). Uma terceira disparada
  pelo próprio Agendador do Windows (`schtasks /Run`): código 0.
- Tarefas do Windows criadas no nível do usuário (`scripts/local/agendar.sh`):
  `ControleCasa-Sync` (todo dia 6h, próxima 03/11/2026) e
  `ControleCasa-Relatorio` (dia 1º às 7h, próxima 01/12/2026). Remover:
  `bash scripts/local/desagendar.sh`. Log: `~/.controle-casa-dev/agendador.log`.
- API: `POST /sincronizacao/atualizar` (202, volta em ms; a mesma execução se
  pedir de novo), estado com `proxima_execucao`, `pode_atualizar` e
  `execucao`. Trava `pg_try_advisory_lock` contra sobreposição (CLI, painel,
  agendador). Testado ao vivo pelo painel: terminou "ok".
- Web: botão "Atualizar agora" e "A próxima roda sozinha amanhã às 6h".
- Docker: serviço `agendador` (escrito, não executado).
- Testes: finanças 780 passados, 0 pulados; compras 51; web typecheck, lint
  e build ok. `mypy app` ok (os 3 erros antigos de `scripts/demo_data.py`
  ficam fora do escopo do `make lint`).
