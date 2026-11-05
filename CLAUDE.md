# controle-casa — finanças e compras da casa

Sistema local (Docker, uso de um casal, sem internet nem multi-tenant).
Decisões já tomadas estão em docs/decisoes.md (D-01..D-26): se algo parecer
faltando, pergunte, não invente. Containers, portas e mcp-servidor:
docs/ecossistema.md.

## Comandos (sempre via Makefile, nunca comandos soltos)

```
make up | dev | down | logs          # dev = --reload + Vite
make migrate | revision m="..."      # finanças (api/alembic)
make compras-migrate | compras-test | compras-lint
make test | lint | fmt               # test sobe casa_test via api-admin
make validar                         # backup + rebuild + migrate + lint + test
make conferir                        # só lê: containers, health, agendador, MCP, ngrok, tailscale
make psql | shell
web/: npm run dev | build | typecheck | lint
```

## Dados reais — riscos

- O banco tem dados financeiros REAIS do casal. Nunca rode `make reset`,
  `down -v`, DROP/TRUNCATE, `pg_restore` ou scripts com `--executar`,
  `executar=1` ou `aplicar=1` sem pedir. Sem a flag eles simulam: rode
  primeiro sem.
- `backups/` e `faturas/` são intocáveis: não apagar, não mover, não commitar.
- Antes de migration ou de script que grava no banco: `make validar` (gera
  backup).

## Regras invioláveis (violar é bug)

1. Dinheiro é `numeric(12,2)`; quantidade `numeric(12,3)`. Nunca float.
2. Sem DELETE físico: `deleted_at = now()`; toda leitura filtra
   `deleted_at IS NULL`.
3. `pessoa_id NULL` = gasto conjunto. Nunca N:N entre transação e pessoa.
4. Schema só muda por migration nova. Nunca editar migration aplicada, nunca
   `create_all()` fora de teste. Em execução autônoma, mudança de schema é
   motivo de PARADA: registre o que seria preciso e por quê, e siga só com o
   que não depende disso (decidido em 06/10/2026).
5. Ingestão grava em `importacao_itens`, nunca em `transacoes`. Exceções
   únicas: a sync Pluggy promove o item limpo (D-21) e rejeita pagamento de
   fatura e dinheiro entre contas da casa (D-22), sempre via
   `aprovar()`/`rejeitar()` da revisão. PDF e LLM nunca. Nova origem
   automática exige decisão nova.
6. O agente de insights usa role read-only do Postgres. Sem exceção.
7. Filtro e agregação acontecem no banco; o front recebe pronto e desenha.
8. `descricao_original` é imutável; edições do usuário vão em `descricao`.
9. Escrita passa por service; router só valida e chama. Regra de negócio não
   mora em router nem em model.

## Convenções fora do padrão

- Domínio em português (`transacoes`, `valor`, `pessoa_id`); UI pt-BR, BRL,
  DD/MM/AAAA.
- `date` para data da transação e competência; `timestamptz` para
  `criado_em`/`atualizado_em`/`deleted_em`.
- IDs `bigint generated always as identity`. Enums nativos do Postgres
  espelhados em `enum.StrEnum`.
- Toda listagem é paginada (cursor ou limit/offset com total).

## Pergunte antes se

- o modelo de dados muda de um jeito não previsto em docs/modelo-dados.md;
- a solução mais simples violaria uma regra acima;
- não está claro a que fase do roadmap a tarefa pertence.

## Mapa

```
api/       FastAPI de finanças (app/, alembic/, scripts/, tests/, tests_sem_banco/)
compras/   serviço da lista de compras (D-25), schema e alembic próprios
web/       React + Vite, servido por nginx
scripts/   validar.sh; local/ = modo antigo CONGELADO, não usar
docs/      ver "Consultar quando"
backups/ faturas/ pluggy_amostras/   dados reais, fora do git
```

## Consultar quando (ler só o trecho necessário)

- schema de finanças → docs/modelo-dados.md
- decisão D-xx → docs/decisoes.md (índice no topo; `grep "## D-"`)
- fase ou escopo → docs/roadmap.md
- ingestão ou insights com LLM → docs/llm.md
- compras → docs/compras/api.md, docs/compras/modelo-dados.md
- telas → docs/design/README.md, docs/design/COMPRAS.md
- progresso → notas/progresso.md
