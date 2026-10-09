# Sistema Financeiro Pessoal — Guia do Projeto

Sistema local de controle e análise financeira, uso doméstico de um casal.
Roda inteiro em Docker na máquina do usuário. Não é multi-tenant, não vai
pra internet, não tem autenticação complexa.

Leia `docs/modelo-dados.md`, `docs/decisoes.md` e `docs/roadmap.md` antes de
começar qualquer tarefa. As decisões já estão tomadas — se algo parecer
faltando, pergunte, não invente.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Banco | PostgreSQL 16 (container) |
| API | FastAPI + SQLAlchemy 2.x + Pydantic v2 |
| Migrations | Alembic |
| Front | React + Vite + TypeScript + TanStack Query + shadcn/ui + Recharts |
| Agentes | Python, reaproveitando os models da API |
| Testes | pytest + testcontainers |
| Qualidade | ruff + mypy no pre-commit |
| Orquestração | Docker Compose |

---

## Regras invioláveis

Estas não são preferências. Violar qualquer uma delas é bug.

1. **Dinheiro é `numeric(12,2)`.** Nunca `float`, `real` ou `double precision`.
   Quantidade é `numeric(12,3)` (cobre 1,250 kg e 42,318 L).
2. **Não existe DELETE físico.** Toda remoção é `deleted_at = now()`. Toda
   query de leitura filtra `deleted_at IS NULL`.
3. **`pessoa_id NULL` significa gasto conjunto.** Nunca crie tabela N:N entre
   transação e pessoa — é isso que duplicaria o valor nos relatórios. Uma
   transação tem exatamente uma atribuição.
4. **Schema só muda por migration nova.** Nunca edite uma migration já
   aplicada. Nunca use `create_all()` fora de teste.
5. **O agente de ingestão nunca escreve em `transacoes`.** Ele grava em
   `importacao_itens` (staging) e o usuário promove pelo painel. **Exceção
   única (D-21):** a sync da Pluggy promove sozinha o item *limpo* — leitura
   1.00, sem observação, sem suspeita de duplicata, com categoria —, pelo
   mesmo `aprovar()` da revisão, com autor `sync_pluggy`. PDF e LLM nunca.
   Qualquer outra origem que queira promover sozinha precisa de decisão nova.
6. **O agente de insights usa role read-only do Postgres.** Sem exceção.
7. **LLM não calcula.** Toda soma, média e comparação sai de SQL agregado. O
   modelo apenas interpreta números que já vieram prontos.
8. **Saída de LLM é structured output validado com Pydantic.** Nada de parse
   de texto livre ou regex em resposta de modelo.
9. **Prompts moram em arquivos versionados** (`prompts/nome_vN.md`), nunca
   hardcoded. A versão usada é gravada na tabela `importacoes`.
10. **Filtro e agregação acontecem no banco.** O front recebe dados prontos e
    desenha. Nunca `.filter()` em array grande no navegador.
11. **`descricao_original` é imutável.** É o texto cru do extrato. Edições do
    usuário vão em `descricao`.
12. **Escrita passa por service.** Router valida entrada e chama service.
    Regra de negócio não mora em router nem em model.

---

## Convenções

- **Idioma**: tabelas, colunas e nomes de domínio em português (`transacoes`,
  `valor`, `pessoa_id`). Palavras-chave técnicas em inglês, como de praxe.
  UI 100% em pt-BR, moeda BRL, datas DD/MM/AAAA.
- **Datas**: `date` para data da transação e competência. `timestamptz` para
  `criado_em` / `atualizado_em` / `deleted_em`.
- **IDs**: `bigint generated always as identity`.
- **Enums**: tipos nativos do Postgres, espelhados em `enum.StrEnum` no Python.
- **Paginação**: cursor ou limit/offset com total. Toda listagem é paginada.
- **Commits**: conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`).

---

## Comandos

Use sempre o Makefile, nunca comandos soltos:

```
make up          # sobe todos os containers
make down        # derruba
make migrate     # aplica migrations pendentes
make revision    # cria nova migration (autogenerate)
make seed        # popula dados iniciais
make test        # roda pytest
make lint        # ruff + mypy
make eval        # roda os evals dos agentes
```

---

## Subagents por domínio

Cada um tem escopo fechado. Se uma tarefa cruzar a fronteira, pare e peça o
domínio certo em vez de invadir.

| Subagent | Domínio | Não toca |
|---|---|---|
| `db` | Models SQLAlchemy, migrations, índices, triggers, views | Routers, front |
| `api` | Routers, services, schemas Pydantic, regra de negócio | Schema do banco |
| `web` | Componentes React, formulários, tabelas, estado | Banco direto |
| `analytics` | Queries agregadas, endpoints de gráfico, Recharts | Qualquer escrita |
| `ingestao` | Parsers de PDF, prompts de extração, harness, staging | `transacoes` |
| `insights` | Tools SQL read-only, prompts de análise, relatórios | Qualquer escrita |
| `qa` | pytest, fixtures, testcontainers, evals | Código de produção |

**Somente o `db` altera schema.** Qualquer outro que precise de coluna nova
solicita ao `db` em vez de criar por conta própria.

---

## Antes de codar, pergunte se

- a tarefa exige mudar o modelo de dados de um jeito não previsto em
  `docs/modelo-dados.md`;
- a solução mais simples exigiria violar alguma regra acima;
- há ambiguidade sobre a qual fase do roadmap a tarefa pertence.

Em execução autônoma (sem o usuário para responder), **mudança de schema é
motivo de PARADA**, não de decisão própria: pare a etapa, registre o que
seria preciso mudar e por quê, e siga só para o que não depende disso.
Decidido pelo usuário em 06/10/2026, depois da migration 0006.
