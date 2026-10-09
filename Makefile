.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up dev down logs migrate revision seed test lint fmt shell psql reset roles relatorio relatorio-seco dossie validar pluggy-diagnostico pluggy-mapear sync pluggy-categorias

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

roles: ## Cria/repara a role read-only do agente de insights (D-11)
	$(COMPOSE) run --rm api python -m scripts.aplicar_roles

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

relatorio-seco: ## Mesmo relatório, só com os números (sem chamar modelo)
	$(COMPOSE) run --rm api python -m scripts.relatorio --sem-ia $(if $(m),--competencia $(m),)

dossie: ## Imprime os números do mês em JSON, sem gerar relatório
	$(COMPOSE) run --rm api python -m scripts.relatorio --dossie $(if $(m),--competencia $(m),)

test: ## Roda o pytest
	$(COMPOSE) run --rm api pytest -q

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

# A lógica mora em scripts/validar.sh (etapas com resumo ficam ilegíveis em
# receita de make). O MAKE vai junto para as etapas chamarem os alvos daqui.
validar: ## Backup do banco, rebuild, /health, migrate, roles, lint e test — para no 1º erro
	@MAKE="$(MAKE)" bash scripts/validar.sh

reset: ## APAGA o volume do banco e recria do zero
	$(COMPOSE) down -v
	$(COMPOSE) up -d db
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) run --rm api python -m app.seed
