# Controle de Casa

Sistema local de controle e análise financeira de uma casa. Roda inteiro em
Docker na máquina do usuário — não é multi-tenant, não vai pra internet, não
tem autenticação complexa.

A documentação viva está em [`docs/`](docs/): leia
[`CLAUDE.md`](docs/CLAUDE.md), [`modelo-dados.md`](docs/modelo-dados.md),
[`decisoes.md`](docs/decisoes.md) e [`roadmap.md`](docs/roadmap.md) **antes**
de mexer em qualquer coisa. As decisões já estão tomadas.

---

## Subindo

```bash
cp .env.example .env      # ajuste as senhas
make up                   # db + api + web
make migrate              # aplica o schema
make roles                # role read-only do agente de insights (D-11)
make seed                 # pessoas, contas, categorias, formas de pagamento
make demo                 # opcional: 12 meses de lançamentos falsos para ver as telas
```

- Painel: http://127.0.0.1:5173
- API e `/docs` do FastAPI: http://127.0.0.1:8000/docs

`make roles` é idempotente e **prova** o que faz: cria a role, tenta escrever
com ela e aborta se a escrita passar. Rode uma vez em banco que já existia
antes da fase 6 — o `init_roles.sql` só roda sozinho no primeiro boot do
volume, então um banco anterior nunca o viu.

`make demo` é só para olhar a interface — os gráficos abrem vazios num banco
recém-criado. `make demo-limpar` desfaz (soft delete, como tudo aqui).

`make help` lista o resto. Use sempre o Makefile, nunca comandos soltos.

### Validando depois de puxar mudanças de schema

```bash
make validar
```

Roda em ordem e para no primeiro erro, dizendo qual etapa falhou:

1. backup do banco atual em `backups/casa_<data>_<hora>.dump`, sobe só o `db`
   se ele estiver parado;
2. rebuild e subida dos containers;
3. espera o `/health` responder com banco `ok`, por até 120 s
   (`VALIDAR_TIMEOUT=300 make validar` muda o limite);
4. `make migrate`, `make roles`, `make lint` e `make test`.

O `make lint` cobre a API (ruff e mypy, também no pre-commit). O web tem lint
próprio, fora do pre-commit: `cd web && npm run lint` (ESLint, só regras de
correção), junto de `npm run typecheck` e `npm run build`.

No fim imprime cada etapa com OK ou FALHOU, quantos testes passaram e o
caminho do backup. `backups/` está no `.gitignore`: é o banco inteiro, dado
financeiro pessoal, e não entra no git.

#### Restaurando o backup

Se a migration der problema, volte o banco ao estado do dump, usando o caminho
que o `make validar` imprimiu:

```bash
docker compose stop api web     # ninguém conectado ao banco durante a troca
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backups/casa_AAAAMMDD_HHMMSS.dump
docker compose start api web
```

Use aspas simples, como acima: assim `$POSTGRES_USER` e `$POSTGRES_DB` são
lidos de dentro do container, e não do seu terminal. O dump traz o schema, os
dados e a versão do Alembic, então depois de restaurar `make migrate` volta a
ver a migration nova como pendente. A role `casa_insights` é do servidor, não
do banco, e sobrevive ao `dropdb`. Os `GRANT` dela vêm dentro do dump.

Antes de aplicar a migration de novo, corrija a causa: código e migration
voltam pelo git, o banco volta pelo dump.

### Fechando o mês

```bash
make relatorio m=2026-07        # texto escrito pelo Claude Code local
make relatorio-seco m=2026-07   # mesmo relatório, só com os números
make dossie m=2026-07           # o JSON que o modelo recebeu
```

O relatório com IA usa o **CLI do Claude Code** (a assinatura), não a API — não
há chave para configurar. Para trocar para a API, `INSIGHTS_BACKEND=api` mais
`ANTHROPIC_API_KEY` no `.env`. Nos dois casos o modelo só escreve texto: quem
soma é o Postgres (regra 7) e quem grava é o service (D-11). `make dossie`
imprime exatamente os números que ele recebeu, para conferir qualquer
afirmação do texto.

### Diagnóstico da Pluggy (fase 5b)

Antes da sync existir, este comando confere o que a Pluggy entrega de verdade.
Ele é somente leitura e não precisa de Docker:

```bash
# PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no .env
make pluggy-diagnostico item=<id do item MeuPluggy>
# sem make: python api/scripts/pluggy_diagnostico.py --item <id>
```

O JSON bruto de cada resposta vai para `pluggy_amostras/<data_hora>/`, que
está fora do git porque é dado pessoal. O terminal mostra só contagens, tipos
e ids, e responde se as compras de cartão trazem `billId` e quais transações
estão `PENDING`. Rode de novo depois do fechamento da fatura: o script compara
com a execução anterior e diz se as pendentes viraram `POSTED` com o mesmo id.

---

## Estrutura

```
api/                 FastAPI + SQLAlchemy 2.x + Alembic
  alembic/versions/  migrations — schema só muda por aqui
  app/
    models.py        models do núcleo v1
    views.py         declaração Core das views de leitura
    enums.py         espelho Python dos enums do Postgres
    schemas/         Pydantic v2: entrada e saída da API
    services/        regra de negócio e toda escrita
    routers/         validação de entrada e nada mais
    ingestao/        parsers de PDF — determinísticos, sem LLM
    insights/        tools SQL read-only, detecções e o harness do modelo
      prompts/       prompts versionados (regra 9)
    seed.py          dados iniciais, idempotente
  scripts/           aplicar_roles, relatorio, demo_data
  tests/             pytest + testcontainers (Postgres de verdade)
web/                 React + Vite + TS + Tailwind v4 + shadcn/ui + Recharts
  src/styles/        design tokens vindos do Claude Design
  src/features/      transacoes, analytics, filters, cadastros, ingestao, regras
docs/                a documentação que manda no projeto
faturas/             seus PDFs (fora do git)
```

---

## Onde o roadmap está

| Fase | O que é | Estado |
|---|---|---|
| 0 | Fundação: compose, Makefile, pre-commit, `/health` | feito |
| 1 | Schema v1: enums, tabelas, triggers, índices, views, seed | feito |
| 2 | API CRUD de todos os recursos, listagem filtrada e paginada | feito |
| 3 | Painel CRUD: tela de transações | feito |
| 4 | Analytics: cinco painéis, filtros compartilhados | feito |
| 5 | Ingestão de PDF: staging, parsers Nubank, regras que aprendem | feito |
| 6 | Insights: tools SQL read-only, detecções, relatório mensal | feito |
| 7 | v2: itens, produtos, tags, recorrências, anexos | **não iniciado** |

A fase 5 usa **parser determinístico**, não LLM: os PDFs do Nubank foram lidos
uma vez e viraram código em `api/app/ingestao/`, e os três extratos reconciliam
exato. O LLM como fallback para banco desconhecido (passo 6 da fase) ficou de
fora de propósito — só pagaria a si mesmo com muitos bancos diferentes.

Da fase 6 falta a tela de relatórios no painel, o chat sob demanda e o
agendamento; hoje o fechamento é o comando `make relatorio`. Detalhes em
[`docs/roadmap.md`](docs/roadmap.md).

---

## Rodando sem Docker (Windows)

Para máquina sem Docker ou sem privilégio de administrador: Postgres em
binários portáteis, a API num venv e o painel com o Node da máquina. Tudo em
`scripts/local/`, para rodar no Git Bash. Nenhuma senha mora nos scripts:
elas vêm do `.env`.

**Uma vez só:**

1. Python 3.12 e Node 20+ (o do winget serve, mesmo fora do PATH).
2. Binários do PostgreSQL 16 em zip, sem instalação:
   <https://www.enterprisedb.com/download-postgresql-binaries>. Extraia a pasta
   `pgsql` em `~/.controle-casa-dev` (ou aponte `LOCAL_PG_BIN` para o `bin`).
3. `.env` copiado do `.env.example`. Se o Postgres local usar senhas
   diferentes das do Docker, preencha `LOCAL_POSTGRES_PASSWORD` e
   `LOCAL_INSIGHTS_PASSWORD`; as outras variáveis `LOCAL_*` têm padrão.
4. `bash scripts/local/instalar.sh` — cria o cluster, os bancos (o de verdade
   e o `_test`), o venv, instala API e web, aplica migrations, cria a role
   read-only e roda o seed. Pode rodar de novo: o que existe é mantido.

**No dia a dia:**

```bash
bash scripts/local/subir.sh      # Postgres :55432, API :8000, painel :5173
bash scripts/local/parar.sh      # encerra só os processos dessas portas
source scripts/local/ambiente.sh # exporta DATABASE_URL, TEST_DATABASE_URL e INSIGHTS_PASSWORD
```

O `ambiente.sh` vai com `source`, não com `bash`: é o que deixa as variáveis
no terminal, para `cd api && pytest`, `python -m scripts.relatorio` e os
scripts da Pluggy acharem o banco local e a senha da role read-only. Sem ele,
eles tentam o host `db` do Docker e falham. Os alvos do Makefile que usam
`docker compose` não funcionam neste modo; rode o comando Python
correspondente com o ambiente exportado.

Os testes usam o banco `_test` do `TEST_DATABASE_URL`, que **é truncado entre
testes** — nunca aponte para dados que importam.

Logs em `~/.controle-casa-dev/{pg,api,web}.log`. O `subir.sh` avisa quando o
Postgres tinha caído sem desligar (suspensão ou desligamento do Windows) e se
recuperou sozinho.

Se o Controle de Aplicativo Inteligente do Windows bloquear uma DLL de pacote
recém-instalado ("Uma política de Controle de Aplicativo bloqueou este
arquivo"), rode de novo: o bloqueio costuma ser só na primeira carga. O mypy
compilado é bloqueado sempre; troque pela versão em Python puro:
`MYPY_USE_MYPYC=0 pip install --no-binary mypy "mypy<2"`.

Os scripts antigos em `~/.controle-casa-dev/subir.sh` e `parar.sh` continuam
funcionando. O `parar.sh` antigo encerra **todo** `python` e `node` da máquina;
o de `scripts/local/` não.

---

## Duas coisas que valem saber

**A role read-only do agente de insights existe e é verificada.**
`api/scripts/init_roles.sql` cria `casa_insights` com `SELECT` e mais nada
(D-11). O `make roles` aplica esse arquivo, troca a senha pela de
`INSIGHTS_PASSWORD` e então **tenta escrever com a role** — se conseguir, o
script aborta. Garantia que ninguém verifica não é garantia.

**`CLAUDE.md` está em `docs/`, não na raiz.** O Claude Code carrega
automaticamente só o da raiz. Se quiser que ele leia sem você pedir, mova ou
crie um `CLAUDE.md` na raiz apontando para `docs/CLAUDE.md`.

**`hash_dedup` usa md5, não sha256.** Coluna gerada no Postgres exige
expressão IMMUTABLE, e a única ponte text→bytea (`convert_to`) é STABLE — não
há como calcular sha256 de texto ali dentro. `md5(text)` é IMMUTABLE e resolve.
É impressão digital de deduplicação num banco doméstico, não fronteira de
segurança. A explicação completa está no comentário da migration 0001.
