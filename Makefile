.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: test-db help up dev down logs migrate revision seed test lint fmt shell psql reset roles relatorio relatorio-seco dossie validar pluggy-diagnostico pluggy-mapear sync pluggy-categorias pluggy-diagnostico-importacao pluggy-reprocessar pluggy-retroativo pluggy-remover-abertas pluggy-resgates compras-role compras-migrate compras-seed compras-test compras-lint financas-role conferir

help: ## Lista os comandos
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

up: ## Sobe tudo em modo produção: painel compilado no nginx (D-19)
	$(COMPOSE) up -d --build
	@echo "painel -> http://127.0.0.1:$${WEB_PORT:-5173}"
	@echo "api    -> http://127.0.0.1:$${WEB_PORT:-5173}/api/docs (pelo painel)"

# Override por cima do compose: o painel volta a ser o Vite com recarga e o
# código montado. `make up` volta à produção.
dev: ## Sobe em modo desenvolvimento: Vite com recarga no lugar do nginx
	$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up -d --build
	@echo "painel (dev, com recarga) -> http://127.0.0.1:$${WEB_PORT:-5173}"

down: ## Derruba os containers (mantém o volume do banco)
	$(COMPOSE) down

logs: ## Segue o log de todos os serviços
	$(COMPOSE) logs -f

migrate: ## Aplica as migrations pendentes
	$(COMPOSE) run --rm api alembic upgrade head

revision: ## Cria migration nova por autogenerate — use: make revision m="mensagem"
	@test -n "$(m)" || (echo "uso: make revision m=\"mensagem\"" && exit 1)
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

seed: ## Popula os dados iniciais (idempotente)
	$(COMPOSE) run --rm api python -m app.seed

demo: ## Gera 12 meses de lançamentos falsos para testar as telas
	$(COMPOSE) run --rm api python -m scripts.demo_data

demo-limpar: ## Remove os lançamentos de demonstração
	$(COMPOSE) run --rm api python -m scripts.demo_data --limpar

# Administração (D-26): rodam no `api-admin`, com a credencial do
# superusuário, que a api não tem.
roles: ## Cria/repara a role read-only do agente de insights (D-11)
	$(COMPOSE) run --rm api-admin python -m scripts.aplicar_roles

financas-role: ## Cria/repara a role casa_financas e passa a ela os objetos de finanças (D-26)
	$(COMPOSE) run --rm api-admin python -m scripts.aplicar_role_financas

# O relatório com IA roda o `claude` do host, não do container: o CLI usa a
# credencial já logada na sua máquina, que não existe dentro da imagem.
relatorio: ## Fecha o mês com o Claude Code — use: make relatorio m=2026-07
	@cd api && python -m scripts.relatorio $(if $(m),--competencia $(m),)

# Também no host: lê as credenciais do .env da raiz e grava as amostras em
# pluggy_amostras/, sem depender de Docker. Só leitura, na Pluggy e no disco.
pluggy-diagnostico: ## Lê a Pluggy e grava amostras brutas — use: make pluggy-diagnostico [item=ID]
	@cd api && python -m scripts.pluggy_diagnostico $(if $(item),--item $(item),)

# No container, como `roles`: precisa do banco além da Pluggy. Só leitura.
pluggy-mapear: ## Lista as contas da Pluggy ainda sem mapeamento — use: make pluggy-mapear [item=ID]
	$(COMPOSE) run --rm api python -m scripts.pluggy_mapear $(if $(item),--item $(item),)

# Grava no staging; só o item limpo entra em `transacoes` sozinho (D-21).
sync: ## Sincroniza a Pluggy: limpos promovidos, resto na revisão — use: make sync [simular=1]
	$(COMPOSE) run --rm api python -m scripts.pluggy_sync $(if $(simular),--simular,)

# Lê os comprovantes das importações da Pluggy; só grava com aplicar=1.
pluggy-categorias: ## Proposta de mapeamento das categorias da Pluggy — use: make pluggy-categorias [aplicar=1]
	$(COMPOSE) run --rm api python -m scripts.pluggy_categorias $(if $(aplicar),--aplicar,)

# Só lê: formas, categorias e operações de uma importação da Pluggy (D-21).
pluggy-diagnostico-importacao: ## Diagnóstico de uma importação da Pluggy — use: make pluggy-diagnostico-importacao [i=4]
	$(COMPOSE) run --rm api python -m scripts.pluggy_diagnostico_importacao $(if $(i),--importacao $(i),)

# Simula por padrão; grava e promove os limpos só com executar=1 (D-21).
pluggy-reprocessar: ## Reprocessa os pendentes de uma importação da Pluggy — use: make pluggy-reprocessar [i=4] [proposta=1] [executar=1]
	$(COMPOSE) run --rm api python -m scripts.pluggy_reprocessar $(if $(i),--importacao $(i),) $(if $(proposta),--com-proposta,) $(if $(executar),--executar,)

# Simula por padrão; grava só com executar=1, e nunca onde o usuário editou (D-21).
pluggy-retroativo: ## Categoria e forma retroativas nas transações da Pluggy — use: make pluggy-retroativo [executar=1]
	$(COMPOSE) run --rm api python -m scripts.pluggy_retroativo $(if $(executar),--executar,)

# D-28: tira do staging e de transacoes as compras em aberto da D-23. Simula por
# padrão; grava só com executar=1, e deixa a transação que o usuário editou.
pluggy-remover-abertas: ## Remove as compras em aberto da D-23 (D-28) — use: make pluggy-remover-abertas [executar=1]
	$(COMPOSE) run --rm api python -m scripts.remover_abertas_d28 $(if $(executar),--executar,)

# Só lê: aplicações e resgates da Pluggy, contraparte no mesmo dia e conclusão.
pluggy-resgates: ## Investiga os resgates e aplicações da Pluggy (somente leitura)
	$(COMPOSE) run --rm api python -m scripts.pluggy_resgates

relatorio-seco: ## Mesmo relatório, só com os números (sem chamar modelo)
	$(COMPOSE) run --rm api python -m scripts.relatorio --sem-ia $(if $(m),--competencia $(m),)

dossie: ## Imprime os números do mês em JSON, sem gerar relatório
	$(COMPOSE) run --rm api python -m scripts.relatorio --dossie $(if $(m),--competencia $(m),)

# Os testes rodam no banco casa_test do próprio Postgres do compose (truncado
# entre testes), com a credencial de administração: dentro do container não há
# Docker para o testcontainers. As senhas das roles vêm do .env (api-admin e
# compras-role já as têm): a role é do cluster, e uma senha de teste trocaria
# a da produção (D-26).
test-db:
	@$(COMPOSE) exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '"'"'casa_test'"'"'" | grep -q 1 || createdb -U "$$POSTGRES_USER" casa_test'

test: test-db ## Roda o pytest (no banco casa_test)
	$(COMPOSE) run --rm api-admin sh -c 'TEST_DATABASE_URL="$${DATABASE_ADMIN_URL%/*}/casa_test" pytest'

lint: ## ruff + mypy
	$(COMPOSE) run --rm api ruff check .
	$(COMPOSE) run --rm api ruff format --check .
	$(COMPOSE) run --rm api mypy app

fmt: ## Formata com ruff
	$(COMPOSE) run --rm api ruff format .
	$(COMPOSE) run --rm api ruff check --fix .

shell: ## Shell dentro do container da api
	$(COMPOSE) run --rm api bash

psql: ## psql no banco
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-casa} -d $${POSTGRES_DB:-casa}

# --- Lista de compras (D-25) ------------------------------------------------
# Primeira vez: compras-role, compras-migrate, compras-seed.
compras-role: ## Cria/repara a role casa_compras e o schema compras (D-25)
	$(COMPOSE) run --rm compras-role

compras-migrate: ## Aplica as migrations do serviço de compras
	$(COMPOSE) run --rm compras alembic upgrade head

compras-seed: ## Seções do mercado e produtos comuns (idempotente)
	$(COMPOSE) run --rm compras python -m compras.seed

compras-test: test-db ## Roda o pytest do serviço de compras (no banco casa_test)
	$(COMPOSE) run --rm compras-role sh -c 'TEST_DATABASE_URL="$${COMPRAS_DONO_DATABASE_URL%/*}/casa_test" pytest'

compras-lint: ## ruff + mypy do serviço de compras
	$(COMPOSE) run --rm compras ruff check .
	$(COMPOSE) run --rm compras ruff format --check .
	$(COMPOSE) run --rm compras mypy compras scripts tests

# A lógica mora em scripts/validar.sh (etapas com resumo ficam ilegíveis em
# receita de make). O MAKE vai junto para as etapas chamarem os alvos daqui.
validar: ## Backup do banco, rebuild, /health, migrate, roles, lint e test — para no 1º erro
	@MAKE="$(MAKE)" bash scripts/validar.sh

# Só lê e mostra (OK/AVISO/FALHA por linha); não sobe nem para nada.
conferir: ## Confere containers, health, agendador, MCP, ngrok e tailscale serve (só leitura)
	@bash scripts/conferir.sh

reset: ## APAGA o volume do banco e recria do zero
	$(COMPOSE) down -v
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm api-admin python -m scripts.aplicar_roles
	$(COMPOSE) run --rm api-admin python -m scripts.aplicar_role_financas
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) run --rm api-admin python -m scripts.aplicar_roles
	$(COMPOSE) run --rm api python -m app.seed
