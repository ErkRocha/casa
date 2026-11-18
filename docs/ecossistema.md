# Ecossistema da casa

Referência compartilhada entre `controle-casa` e `mcp-servidor`. Ao mudar
container, porta, rota ou quem chama quem, atualize este arquivo.

## Repositórios

| Repo | Caminho | O que é |
|---|---|---|
| controle-casa | `C:\Users\erikf\dev\casa\controle-casa` | finanças + compras + painel (Docker) |
| mcp-servidor | `C:\Users\erikf\dev\casa\mcp-servidor` | servidor MCP de voz/vault (antes em `C:\Users\erikf\servidor`) |

Vault: `C:\Users\erikf\vault` (configurável por `VAULT_MCP_PATH` no
mcp-servidor).

## Containers (compose `name: controle-casa`)

Todas as portas publicadas só em `127.0.0.1`. Volume do banco:
`controle-casa_db_data`.

| Serviço | Container | Porta host | Observação |
|---|---|---|---|
| db | casa_db | `${POSTGRES_PORT:-5432}` | postgres:16-alpine; roles via `api/scripts/init_roles.sql` |
| api | casa_api | `${API_PORT:-8000}` | FastAPI de finanças |
| web | casa_web | `${WEB_PORT:-5173}` | nginx com o build do React |
| compras | casa_compras | `${COMPRAS_PORT:-8001}` | serviço da lista de compras (D-25) |
| agendador | casa_agendador | — | `python -m scripts.agendador`, sync Pluggy às 06:00 |
| api-admin | — | — | perfil `ferramentas`, credencial de superusuário |
| compras-role | — | — | perfil `ferramentas` |

`docker-compose.dev.yml`: `--reload` em api e compras; web vira o Vite.

## Rotas do nginx (casa_web)

- `/api` → `api:8000`
- `/api/compras` → `compras:8000`

## Quem chama quem

- **mcp-servidor → compras**: HTTP em `http://127.0.0.1:5173/api/compras`
  (`COMPRAS_API_URL`), header `X-Quem: voz`, `origem: voz`. Ferramentas:
  `ver_lista_compras`, `adicionar_na_lista`, `marcar_comprado`,
  `marcar_acabou`; cardápio: `cardapio`,
  `definir_refeicoes`, `preparo`, `cardapio_para_lista`, `receitas`. O mcp-servidor roda na porta 8765.
- **MCP de finanças (D-20)** — outro servidor, deste repo: stdio no Claude
  Desktop, `docker exec -i casa_api python -m app.mcp`. Não confundir com o
  mcp-servidor.
- Acesso remoto pela Tailscale (D-18).

## Qual base cada tela do financeiro usa (D-31, D-32)

Um gasto no cartão tem duas datas: a da compra e a da fatura em que caiu
(competência, D-02). O **Início** responde "quanto a gente gastou este mês?"
pela **data da compra**: gasto até hoje, comparação com o mês anterior,
receitas, sobra, orçamento, avisos de orçamento, quem gastou e por categoria
(as partes somam o gasto). No cartão, o Início conta a **fatura atual**
de cada cartão, desde o último fechamento, com as compras ainda pendentes no
banco (D-32), e diz quanto do número é pendente; Pix, débito e boleto vão
pela data, no mês. É a única tela que soma pendentes. O bloco **"O que sai da conta"** do Início (faturas
a pagar, já saiu da conta, previsão de fechamento) é a outra base, a do caixa
(D-27): competência, com a fatura no dia em que sai da conta; faturas
abertas e os dois gráficos seguem a D-27/D-29. As **Análises** têm o seletor,
com "pela data da compra" como padrão; o orçamento delas segue o seletor. O
**relatório mensal** e o MCP de finanças são por **competência**, e o
relatório diz isso no fim do texto. Faixas de orçamento (80% atenção, 100%
estourado) e a média mensal (sem os meses sem lançamento) são as mesmas em
todas as telas: `api/app/faixas_orcamento.py` e `api/app/medias.py`.

## Roles do Postgres

- `casa_financas` — API de finanças (sem superusuário, D-26)
- `casa_compras` — serviço de compras, schema `compras`
- role read-only de insights (D-11)
