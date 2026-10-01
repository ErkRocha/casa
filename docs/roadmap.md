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

## Fase 5b — Sincronização Pluggy

Mais uma origem de ingestão, ao lado do PDF (D-16). Depende dos passos 1 a 5
da Fase 5: staging, revisão, promoção e regras. Não depende do LLM. Só contas
do usuário nesta fase. As da esposa aguardam a confirmação da Pluggy sobre o
uso pessoal.

Nesta ordem, sem pular:

1. **Schema (subagent `db`)**: as mudanças da lista de pendências abaixo, em
   migration nova. Nada da fase anda antes disso.
2. **Configuração**: `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET` no `.env`, com
   placeholder no `.env.example`. Ausência das variáveis desliga a sync com
   mensagem clara, sem derrubar a API.
3. **Cliente HTTP da Pluggy**: autenticação, listagem de contas de um item e
   transações paginadas por cursor (500 por página). Ele respeita o rate limit:
   em 429, espera e tenta de novo com limite de tentativas. Nunca chama o
   `PATCH /items`. É testado só com respostas mockadas (auth, página única,
   várias páginas, 429, 401, erro 5xx), sem rede no `make test`.
4. **Mapeamento de contas**: comando ou tela simples que lista as contas
   visíveis na Pluggy e liga cada uma a uma `conta`, a uma forma de pagamento
   padrão e à data a partir da qual a Pluggy é a origem daquela conta. Conta
   não mapeada é ignorada e aparece num aviso, nunca adivinhada.
5. **Conversão para `ItemExtraido`**: função pura, testada contra JSON real
   anonimizado em fixture. O sinal do `amount` vira `tipo`, e `valor` fica
   sempre positivo. O pagamento de fatura vira transferência (D-05). O final
   do cartão vai para `cartao_final`. A descrição crua vai para `linha_bruta`.
   O id da Pluggy vira o id externo. Transação pendente é descartada.
6. **Service de sync**: para cada conta mapeada, busca a partir do último sync
   (com folga de alguns dias de sobreposição), descarta ids já presentes no
   staging, converte e grava pelo mesmo caminho de `IngestaoService`.
   Enriquecimento igual ao do PDF, com `pessoa_sugerida_id` caindo no
   `contas.titular_id` quando regra e cartão não resolvem. Sem item novo, não
   cria `importacao` vazia. A sessão roda com `app.autor = 'sync_pluggy'`
   (D-06).
7. **`make sync`**: execução manual, que imprime contas lidas, itens novos,
   ignorados por id repetido e avisos. Rodar duas vezes seguidas não gera
   item novo na segunda.
8. **Revisão no painel**: a importação de origem `pluggy` aparece na mesma
   tela de revisão, sem o botão de reabrir PDF. Transferência segue a regra
   atual: o usuário escolhe as contas ou rejeita.
9. **Execução agendada**, só depois de algumas semanas de `make sync` manual
   sem surpresa: uma vez por dia, depois da atualização da Pluggy. Falha vira
   log e aviso no painel, não retentativa infinita.

**Pronto quando**: uma compra no cartão aparece na tela de revisão no dia
seguinte sem ninguém baixar PDF. Rodar a sync de novo não duplica nada, nem no
staging nem em `transacoes`.

### Pendências de schema para o subagent `db`

Não previstas em `docs/modelo-dados.md`. Ficam como proposta até o `db`
desenhar a migration e atualizar o modelo:

- **`importacao_itens.id_externo text`** (nulo para PDF), com único parcial
  `(id_externo) where id_externo is not null and deleted_em is null`, em
  qualquer status. É a deduplicação no staging da D-16. Item rejeitado
  continua bloqueando, para não voltar na sync seguinte.
- **Importação sem arquivo**: hoje `importacoes.arquivo_nome` e `hash_arquivo`
  são `not null` e `hash_arquivo` é único. Há duas opções para o `db`
  escolher:
  (a) tornar os dois nuláveis, com CHECK de que origem diferente de `pluggy`
  exige arquivo;
  (b) manter o rastro do documento gravando como "arquivo" o JSON bruto
  recebido (`arquivo_tipo = 'application/json'`), com hash dele. A opção (b)
  preserva o comprovante, como já é feito com o PDF.
- **Tabela de mapeamento Pluggy → `contas`** (ex. `contas_pluggy`):
  `pluggy_item_id`, `pluggy_account_id` (único), `conta_id` fk,
  `forma_pagamento_id` fk (a padrão daquela conta), `sincronizar_desde date`,
  `ultimo_sync_em timestamptz`, `ativo`, `deleted_em`. A pessoa sai de
  `contas.titular_id`, não é coluna aqui. Por isso incluir contas de outro
  titular depois não muda a estrutura.

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
- Integração direta com API de cada banco. A sincronização via Pluggy saiu
  daqui: ver D-16 e Fase 5b
- App mobile nativo
