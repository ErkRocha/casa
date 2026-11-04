---
name: migracao-banco
description: Cria ou altera tabela, coluna, índice, enum, view ou trigger no Postgres de finanças ou de compras via migration Alembic. Use ao pedirem mudança de schema, "nova tabela", "nova coluna", "migration" ou "alembic".
---

1. Se a execução for autônoma (sem usuário respondendo): PARE. Registre em notas/progresso.md o que seria preciso e por quê (regra 4 do CLAUDE.md) e siga só com o que não depende disso.
2. Identifique o alvo:
   - finanças: `api/alembic/versions`; `make revision m="..."`; `make migrate`.
   - compras: `compras/alembic/versions`, schema `compras`; não há alvo de revisão no Makefile, use `docker compose run --rm compras alembic revision --autogenerate -m "..."`; aplica com `make compras-migrate`.
3. Confira se o pedido está em docs/modelo-dados.md (finanças) ou docs/compras/modelo-dados.md (compras). Se não estiver, pergunte antes.
4. Rode `make validar` (gera backup em backups/). Não apague nem mova backups/.
5. Gere a revisão e REVISE o autogenerate linha a linha:
   - dinheiro `numeric(12,2)`, quantidade `numeric(12,3)`, nunca float;
   - tabela nova com `deleted_at timestamptz`; `criado_em`/`atualizado_em` em `timestamptz`;
   - id `bigint generated always as identity`;
   - enum nativo do Postgres, espelhado em `enum.StrEnum` no model;
   - nenhum drop que não foi pedido;
   - `downgrade` implementado;
   - grants para a role certa: `casa_financas` (finanças), `casa_compras` (compras) e SELECT para a role read-only de insights (D-11) quando a tabela for de finanças e couber.
6. Nunca edite migration já aplicada: confira com `docker compose run --rm api alembic current` e `history` (em compras, `compras alembic ...`). Corrija sempre com migration nova.
7. Aplique (`make migrate` ou `make compras-migrate`) e rode `make test` (compras: `make compras-test`). Se mexeu em tabela de finanças, rode `make roles` para refazer o SELECT da role de insights.
8. Atualize o doc de modelo de dados correspondente.
9. Faça o commit `feat:` ou `chore:` com a migration e o doc.
