# Roadmap

Regra que guia a ordem: **nada de agente antes do banco e do painel estarem de
pé**. É preciso conseguir ver e corrigir dados na mão antes de deixar um LLM
escrever neles.

Cada fase termina com algo funcionando. Não avance com a anterior pela metade.

---

## Fase 0 — Fundação

- Repositório com a estrutura de pastas definida
- `docker-compose.yml`: `db`, `api`, `web`
- `Makefile` com os comandos padrão
- pre-commit com ruff e mypy
- `CLAUDE.md` e os três arquivos de `docs/`
- `.env.example` e config por variável de ambiente

**Pronto quando**: `make up` sobe tudo e a API responde no `/health`.

---

## Fase 1 — Schema v1

- Migration inicial: enums, `pessoas`, `contas`, `categorias`,
  `formas_pagamento`, `locais`, `transacoes`, `orcamentos`, `auditoria`
- Triggers de auditoria e de `atualizado_em`
- Índices, checks e o único parcial de `hash_dedup`
- Seed: as duas pessoas, contas, formas de pagamento, árvore inicial de
  categorias
- Views `vw_transacoes_completa` e `vw_gasto_por_pessoa`

**Pronto quando**: `make migrate && make seed` roda limpo do zero.

---

## Fase 2 — API CRUD

- Endpoints de todos os recursos do v1
- Listagem de `transacoes` com todos os filtros e paginação
- Camada de service separada dos routers
- Testes com testcontainers desde o primeiro endpoint

**Pronto quando**: dá para operar o sistema inteiro pelo `/docs` do FastAPI.

---

## Fase 3 — Painel CRUD

- Tela de transações primeiro: tabela densa, filtros combináveis, edição
  inline de categoria e pessoa, seleção múltipla e ação em lote
- Depois as telas de cadastro
- Design vindo do Claude Design

**Pronto quando**: o usuário consegue lançar e corrigir gasto na mão. A partir
daqui o sistema já é útil mesmo sem nenhum agente.

---

## Fase 4 — Analytics

- Evolução mensal, composição por categoria com drill-down, comparativo entre
  pessoas e conjunto, progresso de orçamento, comparação com períodos
  anteriores
- Filtros compartilhados com a tela de transações
- Transferências excluídas de todo cálculo de gasto

**Pronto quando**: os gráficos respondem aos filtros sem recarregar a página.

---

## Fase 5 — Ingestão

Nesta ordem, sem pular:

1. `importacoes` e `importacao_itens`
2. Extração com `pdfplumber` de **um** banco só
3. Parser determinístico desse banco
4. Tela de revisão e promoção para `transacoes`
5. `regras_categorizacao` e o aprendizado por correção
6. Só então o LLM como fallback, com harness completo
7. Evals com PDFs reais

**Pronto quando**: uma fatura vira transações revisadas sem digitação manual.

---

## Fase 6 — Insights

- [x] Role read-only no Postgres — `make roles`, com prova de que não escreve
- [x] Tools SQL determinísticas — `app/insights/tools.py`
- [x] Detecções que não usam LLM (reajuste, orçamento estourado, gasto atípico)
- [x] Relatório mensal salvo em `relatorios` — `make relatorio`
- [ ] Tela de relatórios no painel
- [ ] Chat sob demanda no painel
- [ ] Agendamento (hoje o fechamento é um comando que você roda)

**Pronto quando**: o fechamento do mês gera texto ancorado em números reais.

O modelo entra por um de dois caminhos, escolhidos em `INSIGHTS_BACKEND`: o
CLI do Claude Code (usa a assinatura, sem chave de API) ou a API da Anthropic.
Em ambos ele recebe o dossiê pronto e só escreve — quem soma é o Postgres
(regra 7) e quem grava é o service (D-11). `--sem-ia` gera o mesmo relatório
sem modelo nenhum, o que mantém o fechamento disponível quando o CLI não
estiver instalado.

---

## Fase 7 — v2

Tudo aditivo, sem quebrar o que existe:

- `itens_transacao`, `produtos`, `produto_aliases`
- `mv_historico_preco` e a tela de histórico de preço por produto
- `tags` e `transacao_tags`
- `recorrencias`
- `anexos`
- Campos de moeda estrangeira, **se** houver compra internacional

---

## Fora de escopo

Registrado para não ser reintroduzido por engano:

- Rateio ou divisão de despesas entre as duas pessoas (D-03)
- Multiusuário, autenticação complexa, deploy em nuvem
- Integração com Open Finance ou API de banco
- App mobile nativo
