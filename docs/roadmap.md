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

A Pluggy como fonte única do dia a dia, pelo mesmo caminho de ingestão do
PDF; os parsers de PDF ficam como fallback (D-16, atualizada em 05/10/2026).
Depende dos passos 1 a 5 da Fase 5: staging, revisão, promoção e regras. Não
depende do LLM. Só contas
do usuário nesta fase. As da esposa aguardam a confirmação da Pluggy sobre o
uso pessoal.

Nesta ordem, sem pular:

1. **Schema (subagent `db`)**: as mudanças da lista de pendências abaixo, em
   migration nova. Nada da fase anda antes disso.

   **Feito.** Validado em 05/10/2026 com as etapas do `make validar` rodadas
   à mão contra um Postgres local, sem Docker: backup, migrate 0004 -> 0005,
   roles, lint e os testes de banco, sem nenhum pulado.
2. **Configuração**: `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET` no `.env`, com
   placeholder no `.env.example`. Ausência das variáveis desliga a sync com
   mensagem clara, sem derrubar a API.
3. **Cliente HTTP da Pluggy**: autenticação, listagem de contas de um item e
   transações paginadas por cursor (500 por página). Ele respeita o rate limit:
   em 429, espera e tenta de novo com limite de tentativas. Nunca chama o
   `PATCH /items`. É testado só com respostas mockadas (auth, página única,
   várias páginas, 429, 401, erro 5xx), sem rede no `make test`.

   A primeira resposta real, anonimizada e guardada como fixture, precisa
   responder duas perguntas:
   - se o `billId` vem pelo MeuPluggy (ver passo 5);
   - se o `id` de uma compra de cartão continua o mesmo quando ela passa de
     `PENDING` para `POSTED`. Para saber, anote o id de uma compra em fatura
     aberta e compare depois do fechamento.

   A segunda resposta decide se pendentes podem entrar no futuro. Com id
   estável, o `id_externo` deduplicaria a mesma compra nos dois estados. Com
   id novo, ela entraria duas vezes no staging, e o `id_externo` não teria
   como perceber.
4. **Mapeamento de contas**: comando ou tela simples que lista as contas
   visíveis na Pluggy e liga cada uma a uma `conta`, a uma forma de pagamento
   padrão e à data a partir da qual a Pluggy é a origem daquela conta. Conta
   não mapeada é ignorada e aparece num aviso, nunca adivinhada.

   **Feito.** CRUD em `/contas-pluggy` e `make pluggy-mapear`. Cartão
   (`CREDIT`) espelha o PDF: aponta para a conta corrente que paga a fatura,
   com a forma `credito` daquele cartão, e não para uma conta própria do tipo
   `cartao`. A forma tem que pertencer à conta mapeada. Mapear uma conta com
   transação de PDF depois de `sincronizar_desde` devolve aviso, sem bloquear.
   Consequência do encaixe: o "Pagamento recebido" do lado do cartão vira
   transferência sem conta de destino e é rejeitado na revisão, como o PDF
   já faz com o pagamento.

   **Remapeado em 05/10/2026** com uma conta por banco (Sicredi Conta
   Corrente, Sicredi Poupança, Mercado Pago e Nubank, as duas últimas contas
   pré-pagas). Cada cartão é forma `credito` da conta que paga a fatura; Pix e
   débito ficam na conta do próprio banco. A "Conta Corrente" e as formas do
   seed continuam com as transações antigas: mover a conta delas mudaria o
   significado do que já foi gravado. Os cartões virtuais do Nubank
   Gold são do titular e caem na forma do cartão, sem forma própria.

   `sincronizar_desde`: contas `BANK` no 1º dia do mês 12 meses atrás
   (01/10/2025), ou no mês do primeiro dado que a Pluggy entrega, quando ele
   é mais recente (Sicredi Conta Corrente: 01/01/2026). Cartões no início do
   primeiro ciclo de fatura inteiramente coberto, conferido contra as faturas
   e as transações de cada uma: Mercado Pago 06/10/2025 e Nubank Gold
   11/10/2025. A janela da Pluggy é móvel; se a primeira sync atrasar, o
   início de outubro/2025 sai dela e as datas precisam ser revistas.

   **Cartão Sicredi: mapeamento desativado (06/10/2026, decisão do
   usuário).** A Pluggy entrega esse cartão só como `PENDING` e sem faturas:
   as 14 transações de 12 meses nunca consolidaram, e como só `POSTED` entra,
   a sync não traria nada dele. O mapeamento foi desativado por soft delete
   (fica na auditoria e pode voltar). Pendência: perguntar no Discord da
   Pluggy por que o cartão não consolida. Até lá, as compras dele são
   lançadas à mão.
5. **Conversão para `ItemExtraido`**: função pura, testada contra JSON real
   anonimizado em fixture. O sinal do `amount` vira `tipo`, e `valor` fica
   sempre positivo. O pagamento de fatura vira transferência (D-05). O final
   do cartão vai para `cartao_final`. A descrição crua vai para `linha_bruta`.
   O id da Pluggy vira o id externo. Transação pendente é descartada.

   **Competência de cartão (D-02).** Vale a fatura informada pela Pluggy:
   `creditCardMetadata.billId` → `GET /bills` → `dueDate`, e a competência é
   o dia 1º do mês desse vencimento. Esse é o dado que o próprio banco
   declara. O cálculo com `dia_fechamento` e `dia_vencimento` fica só como
   fallback e é uma estimativa: erra quando o banco antecipa o fechamento por
   causa de feriado e quando o dia muda. Ele entra quando `billId` vier vazio
   e a forma mapeada tiver os dois dias. Sem nenhum dos dois, a competência
   sai do mês da data e o item recebe uma observação para revisão.
   `billForecastDate`, a previsão de fatura das compras pendentes, não é
   usado: só vale para pendentes, que a D-16 já descarta, e há relato de que
   o valor oscila entre syncs.

   O `billId` vem documentado como "disponível apenas em conectores Open
   Finance". O MeuPluggy (conector 200) é marcado `isOpenFinance: false`, mas
   repassa conexões Open Finance e há relato de `billId` chegando por ele. Por
   isso, a primeira resposta real do passo 3 confirma se o campo vem, e ela
   vira fixture deste passo. Se não vier, o fallback passa a ser o caminho
   principal, sem mudança de schema.

   **Feito.** `app/conversao_pluggy.py`, fora de `app.pluggy` (que só importa
   a si mesmo) e de `app.ingestao` (que não pode puxar o `httpx`, D-08). O
   `billId` veio em todas as 69 compras de cartão das amostras reais, e as
   faturas existem em `/bills`. O sentido sai de `type`, porque o sinal de
   `amount` inverte entre conta e cartão. `dueDate` é lido como data pura,
   sem conversão de fuso. `ItemExtraido` ganhou `id_externo` e `competencia`
   por item, que o service já grava no staging.

   **Cartão pendente fica fora desta versão (decidido).** Pela documentação da
   Pluggy, compra em fatura aberta vem como `PENDING` e só vira `POSTED`
   quando a fatura fecha. A D-16 continua aceitando só `POSTED`. Por isso a
   compra no cartão chega à revisão depois do fechamento, e não no dia
   seguinte. O atraso foi aceito porque, na fatura fechada, a competência sai
   do `billId`, que é exata. Uma pendente teria competência provisória, sujeita
   a mudar. Rever essa decisão depende da verificação de id do passo 3. A
   visão da fatura aberta, sem gravar nada, está na Fase 7.
6. **Service de sync**: para cada conta mapeada, busca a partir do último sync
   (com folga de alguns dias de sobreposição), descarta ids já presentes no
   staging, converte e grava pelo mesmo caminho de `IngestaoService`.
   Enriquecimento igual ao do PDF, com `pessoa_sugerida_id` caindo no
   `contas.titular_id` quando regra e cartão não resolvem. Sem item novo, não
   cria `importacao` vazia. A sessão roda com `app.autor = 'sync_pluggy'`
   (D-06).

   **Aviso de origem na importação de PDF (D-16, uma origem por conta e
   período).** `importacoes` não tem conta. Por isso, ao importar um PDF, o
   service olha as formas de pagamento sugeridas nos itens e chega à conta
   por `formas_pagamento.conta_id` ou por `contas_pluggy.forma_pagamento_id`.
   Depois verifica se alguma dessas contas tem `contas_pluggy` ativa e se o
   período do documento (`periodo_inicio`/`periodo_fim`) passa de
   `sincronizar_desde`.
   Se passar, a tela de revisão mostra um aviso: "Esta conta é sincronizada
   pela Pluggy desde DD/MM/AAAA; itens deste período podem já estar no
   staging com outra descrição, e o `hash_dedup` não os reconhece". É só
   aviso, não bloqueio: o PDF é justamente o fallback para quando a Pluggy
   falha. O aviso vai em `importacoes.erro_mensagem`, como as divergências de
   total já vão, sem coluna nova.

   **Possível duplicata vinda da Pluggy (D-16).** Caso real confirmado: dois
   "Pagamento recebido" de mesmo valor, no mesmo dia, no cartão Nubank, com
   ids diferentes, onde o app do banco mostra um só. Itens da mesma conta da
   Pluggy com a mesma data, valor e descrição e `id_externo` diferente — no
   mesmo lote ou contra o que já está no staging — recebem observação com o
   id do gêmeo e confiança reduzida (abaixo de 0.80, que a revisão
   destaca). Nunca são descartados automaticamente: duas compras iguais no
   mesmo dia também acontecem, e quem decide é o usuário.

   **Encargos de fatura (decisão do usuário, 06/10/2026).** No cartão
   Mercado Pago, o total de várias faturas passa da soma das compras: são
   juros, multa e IOF de atraso, que a Pluggy não entrega como transação.
   Para cada fatura fechada e inteiramente dentro do corte, se o total
   passa da soma das transações `POSTED` dela (pagamentos fora da soma), a
   sync cria um item de despesa "Encargos da fatura MM/AAAA" com a
   diferença, na competência da fatura, com confiança 0.70, observação
   explicando a conta e `id_externo = bill:<billId>:encargos`, que impede a
   repetição. Diferença abaixo de um centavo é arredondamento (a Pluggy
   manda totais com 4 casas). Se as compras passam do total, só aviso.
   Pagamento conta pela operação `PAGAMENTO_FATURA` **ou** pela categoria
   `Credit card payment`: os pagamentos antigos do Nubank vêm com operação
   `PAGAMENTO`. A regra vale para qualquer cartão, Nubank inclusive
   (decisão do usuário, 06/10/2026). O item sugere a categoria "Juros e
   encargos" (raiz de despesa, criada como dado em 06/10/2026), que vence
   regra de texto; sem ela cadastrada, o item vai sem categoria.

   **Feito.** `app/services/sync_pluggy.py` e `scripts/pluggy_sync.py
   --simular`. A observação do item ganhou coluna própria
   (`importacao_itens.observacao`, migration 0006): sem ela, a nota da
   duplicata, do encargo e da competência estimada se perdia antes da tela.
7. **Limpeza dos dados de PDF dentro da janela da Pluggy**, pré-requisito da
   primeira sync. Sem ela, o mesmo gasto apareceria duas vezes: uma pelo PDF,
   outra pela Pluggy, com descrições diferentes que o `hash_dedup` não une.
   - **Escopo:** só o que veio de PDF (importação com origem diferente de
     `pluggy`) e com data igual ou posterior ao `sincronizar_desde` da conta
     da Pluggy correspondente. O que é anterior fica: é o único registro
     daquele período.
   - **Como achar a conta:** pela origem do parser, não pela conta da
     transação. O PDF gravou nas formas do seed ("Cartão de crédito - Erik",
     da "Conta Corrente"), não nas contas novas. `nubank_fatura` corresponde
     ao mapeamento do Nubank Gold; `nubank_extrato`, ao da conta Nubank. Um
     parser sem mapeamento correspondente não é tocado.
   - **O quê:** soft delete (`deleted_em`) das transações promovidas e dos
     itens de staging no escopo, com `app.autor = 'limpeza_pdf'`, para a
     auditoria registrar cada linha (D-06). A `importacao` fica, marcada
     `cancelada`, com o PDF guardado: o comprovante não some.
   - **Como rodar:** comando com simulação por padrão, que só conta; grava
     apenas com confirmação explícita. Rodar duas vezes não muda nada na
     segunda.
   - **Hoje (05/10/2026):** 2 transações e 75 itens de staging (73
     pendentes e 2 aprovados, os que viraram aquelas 2 transações), em 3
     importações do Nubank. Todos estão dentro da janela; nenhum fica fora.

   **Feito (06/10/2026).** `scripts/limpeza_pdf.py --origem
   nubank_fatura=<id> --origem nubank_extrato=<id> --executar`, com a origem
   ligada ao id do mapeamento por argumento (sem id da Pluggy no código).
   Executado depois de backup: 2 transações e 75 itens com soft delete,
   auditados como `limpeza_pdf`; as 3 importações ficaram `cancelada`, com o
   PDF guardado. Uma segunda execução encontra 0 e 0.
8. **`make sync`**: execução manual, que imprime contas lidas, itens novos,
   ignorados por id repetido e avisos. Rodar duas vezes seguidas não gera
   item novo na segunda.

   **Feito (06/10/2026).** `make sync` (ou `python -m scripts.pluggy_sync`)
   grava; `make sync simular=1` só lê. Primeira sync real, depois de backup
   e da limpeza do passo 7: importação #4, 747 itens (15 Sicredi Conta
   Corrente, 73 Mercado Pago conta, 102 Mercado Pago crédito, 348 Nubank
   Gold, 209 Nubank conta), com 8 encargos de fatura e 4 possíveis
   duplicatas marcadas. A segunda execução, logo em seguida, criou zero
   itens e zero importações.
9. **Revisão no painel**: a importação de origem `pluggy` aparece na mesma
   tela de revisão, sem o botão de reabrir PDF. Transferência segue a regra
   atual: o usuário escolhe as contas ou rejeita.
   **Tarefa separada: configurar eslint no web. Feita em 07/10/2026**
   (`chore(web): configura eslint`): ESLint 9, flat config, só regras de
   correção. O portão do web passa a ser lint, typecheck e build.
10. **Execução agendada**, só depois de algumas semanas de `make sync` manual
   sem surpresa: uma vez por dia, depois da atualização da Pluggy. Falha vira
   log e aviso no painel, não retentativa infinita.
   **Feito em 02/11/2026** (`feat: sincronização e relatório automáticos`),
   depois de quase um mês de sync manual desde 06/10. Todo dia às 6h: serviço
   `agendador` no Docker, tarefa do Windows no modo local
   (`scripts/local/agendar.sh`). Uma trava do Postgres impede duas syncs ao
   mesmo tempo. O painel ganhou "Atualizar agora" (`POST
   /sincronizacao/atualizar`, em segundo plano) e mostra a próxima execução.
11. **Ingestão mais direta (D-21, 09/10/2026).** Escrito, com testes de banco
   que ainda não rodaram: a máquina onde foi feito não tem Docker nem
   Postgres. Rodaram lint, mypy (SQLAlchemy 2.0 e 2.1), os testes sem banco e
   lint, typecheck e build do web.
   - forma de pagamento da conta corrente pela operação da Pluggy, na própria
     conta mapeada, criando a que faltar;
   - tabela `categorias_pluggy` (migration 0007), CRUD em
     `/categorias-pluggy`, enriquecimento regra > Pluggy > local, e
     `make pluggy-categorias` com a proposta inicial e as ambíguas;
   - editar categoria na tela de transações ensina regra (D-09);
   - a sync promove sozinha o item limpo, pelo `aprovar()` da revisão;
   - desfazer importação na tela de importações;
   - forma de pagamento em destaque na revisão e nas transações;
   - `make pluggy-diagnostico-importacao` e `make pluggy-reprocessar`
     (simulação por padrão) para a importação da primeira sync.

   **Pendente, no PC de casa, nesta ordem:** `make validar` (aplica a 0007 e
   roda a suíte inteira); o diagnóstico da importação #4; a proposta de
   categorias, revisada antes de `aplicar=1`; a simulação do reprocessamento,
   com e sem `proposta=1`. O reprocessamento real (`executar=1`) só depois de
   o usuário ler a simulação.

**Pronto quando**:
- as transações de conta (débito, Pix, transferência) aparecem na tela de
  revisão no dia seguinte, sem ninguém baixar PDF;
- as compras no cartão aparecem depois do fechamento da fatura, já com a
  competência certa;
- rodar a sync de novo não duplica nada, nem no staging nem em `transacoes`.

### Pendências de schema para o subagent `db`

Implementadas na migration 0005 e já descritas em `docs/modelo-dados.md`. Na
importação sem arquivo, valeu a opção (b), que não exigiu mudança de schema.
Ficam registradas aqui como histórico da decisão:

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
- [x] Tela de relatórios no painel — só leitura: meses à esquerda, o texto
  (Markdown sem HTML, conteúdo não confiável) e ao lado os números do dossiê
  gravado em `dados_base`; com IA ou seco e a versão do prompt. Mês sem
  relatório mostra o `make relatorio m=AAAA-MM`; gerar continua pelo CLI.
- [x] Chat sob demanda — servidor MCP local no Claude Desktop (D-20), só
  leitura pela role da D-11: `python -m app.mcp`. Sem tela de chat no painel
  por enquanto.
- [x] Agendamento — dia 1º às 7h, o relatório do mês anterior: tarefa do
  Windows no modo local (`scripts/local/agendar.sh`, 02/11/2026). No Docker
  o relatório com IA depende do `claude` do host e continua pelo
  `make relatorio`.

**Pronto quando**: o fechamento do mês gera texto ancorado em números reais.

O modelo entra por um de dois caminhos, escolhidos em `INSIGHTS_BACKEND`: o
CLI do Claude Code (usa a assinatura, sem chave de API) ou a API da Anthropic.
Em ambos ele recebe o dossiê pronto e só escreve — quem soma é o Postgres
(regra 7) e quem grava é o service (D-11). `--sem-ia` gera o mesmo relatório
sem modelo nenhum, o que mantém o fechamento disponível quando o CLI não
estiver instalado.

---

## Redesenho do painel (D-24)

Feito na branch `redesign-front`, um commit por fase, sem schema novo, e
mesclado na `main` em 01/11/2026.

- [x] Base visual e Início
- [x] Lançamentos e Revisar
- [x] Análises e Relatórios
- [x] Configurações: contas e cartões, categorias, sincronização
- [x] Aprovado pelo usuário e mesclado na `main` (01/11/2026)
- [ ] Busca e filtro por data na Revisar (a tela antiga de importações tinha)

Pendências que o redesenho encontrou e não resolve sem mudar o schema:

- **Duas compras idênticas no mesmo dia.** Mesma data, valor, descrição
  original e forma de pagamento dão o mesmo `hash_dedup`, e só uma entra
  (D-07). A revisão não oferece "são dois" nesse caso. Resolver pede um
  desempate no hash (o id externo, por exemplo), decisão do subagent `db`.

Pendências fora do schema:

- ~~**"Atualizar agora" na Sincronização.**~~ Feito em 02/11/2026: `POST
  /sincronizacao/atualizar` roda em segundo plano e a tela acompanha.
- ~~**"A próxima roda sozinha amanhã às 6h".**~~ Feito em 02/11/2026, com o
  agendamento (Fase 5b, passo 10).
- **"Já existiam" no resumo da sincronização.** A sync não grava quantas
  transações pulou por já estarem no banco; a tela mostra só o que entrou e
  o que espera revisão.

---

## Fase 7 — v2

Tudo aditivo, sem quebrar o que existe:

- `tags` e `transacao_tags`
- `recorrencias`
- `anexos`
- Campos de moeda estrangeira, **se** houver compra internacional
- Tela **somente leitura** de "fatura aberta": as compras de cartão `PENDING`,
  lidas direto da Pluggy na hora de abrir a tela. Não grava em
  `importacao_itens` nem em `transacoes`, então não fere a regra 5 nem a
  D-16. Responde "quanto já gastei nesta fatura" sem esperar o fechamento. O
  dado oficial continua entrando pela sync, depois do fechamento (Fase 5b).

**Produtos, itens da nota e histórico de preço saíram desta fase (D-25).**
`itens_transacao`, `produtos`, `produto_aliases` e `mv_historico_preco`
moram só no serviço `compras` (Lista de compras, fase 4). Finanças consulta
a API dele quando precisar do detalhe de uma compra.

---

## Lista de compras (D-25)

Serviço próprio, `compras`: API, schema e role de banco próprios, sem FK
para finanças, no mesmo compose e atrás do mesmo nginx, em `/api/compras/`.
Usado pelo casal pelo celular, dentro do mercado, os dois editando. Modelo
em `docs/compras/modelo-dados.md`, endpoints em `docs/compras/api.md`.

Nesta ordem, sem pular:

1. **Serviço: lista e despensa.**
   - `compras/` com `pyproject`, Dockerfile, Alembic próprio (tabela de
     versão no schema `compras`) e testes com testcontainers.
   - Role `casa_compras`, dona do schema `compras`, criada como a de
     insights (script de init e `make roles`), com a senha no `.env`.
   - Tabelas `secoes`, `produtos`, `itens_lista`, `despensa`, `auditoria`;
     seed das seções.
   - Endpoints de `docs/compras/api.md`, com o ciclo lista e despensa no
     service, e `GET /mudancas` com cursor.
   - Container `compras` no compose, `location /api/compras/` no nginx, e o
     mesmo caminho no proxy do Vite e no `scripts/local/subir.sh`.
   - Alvos no Makefile para migrar e testar o serviço.

   **Pronto quando:** `make up` sobe o serviço e `/api/compras/health`
   responde pelo painel; dá para operar lista e despensa inteiras pelo
   `/api/compras/docs`; um teste prova que a role `casa_compras` não lê nem
   escreve em nenhuma tabela de finanças; outro prova que duas sessões
   escrevendo veem as mudanças uma da outra por `/mudancas`, sem perder
   nenhuma e sem duplicar item.

   **Feito (02/11/2026)**, validado no modo local: 51 testes com banco, sem
   nenhum pulado, ruff e mypy. O compose e o nginx estão escritos mas não
   rodaram (a máquina não tem Docker). Diferenças em relação ao plano:
   - a role de finanças é superusuária e passa por cima de GRANT; quem a
     impede de escrever em `compras` é um trigger por comando nas tabelas
     do schema, que recusa qualquer role que não seja `casa_compras` (42501);
   - a busca de produto é `LIKE` no nome normalizado, sem `pg_trgm`: a
     extensão exige superusuário para instalar e não faz falta com dezenas
     de produtos;
   - o `GET /lista` traz também as sugestões ("acabando" sem item na lista).
2. **Telas.** Desenhadas no Claude Design antes de qualquer código (D-15),
   pensadas para o celular em pé, com uma mão, dentro do mercado: lista por
   seção, marcar comprado com um toque, adicionar com busca, despensa.
   Entram no painel atual ou como página própria servida pelo mesmo nginx;
   o desenho decide. Sem app nativo (fora de escopo).

   **Feito (02/11/2026):** desenho aprovado (`docs/design/COMPRAS.md`) e
   implementado na seção Compras do painel (D-25, "Telas aprovadas"). Falta
   o "pronto quando" abaixo, que só o casal faz.

   **Pronto quando:** o casal faz uma compra real do começo ao fim pelos
   dois celulares, cada um vendo o que o outro marcou em poucos segundos.
3. **Uso compartilhado: identidade pelo Tailscale.** O "quem" deixa de ser
   texto digitado. O `tailscale serve` (D-18) informa o usuário da tailnet
   em cada requisição; o nginx passa esse valor no `X-Quem` e descarta o
   que o celular mandar. Cada pessoa entra na tailnet com a **própria
   conta** do Tailscale (decidido, D-25: o usuário convida a esposa); com a
   mesma conta nos dois, a identidade não distinguiria ninguém. Sem
   identidade do Tailscale (em casa, pelo localhost), o aparelho pergunta
   uma vez "quem é você?" e envia a resposta no `X-Quem`.

   **Preparado (02/11/2026):** tabela `identidades_tailscale` (migration
   `compras/0003`), `GET /eu` e `/identidades`; nginx e Vite põem
   `Tailscale-User-Login` no `X-Quem` e descartam o do celular (conferido
   com a imagem real do nginx e pelo Vite); o front só pergunta "quem é
   você?" sem identidade. O login do usuário já está cadastrado como
   "Erik". **Falta, do usuário:** ligar o `tailscale serve` (README,
   "Acessando fora de casa") e convidar a esposa, cadastrando o login dela
   (README, "Convidando outra pessoa").

   **Pronto quando:** "adicionado por" e "comprado por" aparecem com o nome
   certo sem ninguém digitar, e um `X-Quem` forjado pelo celular é ignorado
   (teste no nginx).
4. **Nota fiscal e preços.** Ler o QR code da NFC-e, buscar os itens na
   consulta pública da SEFAZ-RS e gravar `mercados`, `notas_fiscais` e
   `nota_itens`, com o conteúdo original guardado. Associação a produto por
   GTIN e `apelidos`, aprendidos com a correção do usuário (D-09). Histórico
   de preço por produto e mercado (`vw_preco_produto`). Item comprado na
   lista e item da nota se encontram pelo produto.

   **Backend feito (02/11/2026)**, sem telas (D-15) e **sem validação com
   nota real**: não havia nenhuma disponível. Migration `0002`, leitura pela
   URL do QR code ou pela chave (dígito verificador, UF e CNPJ), consulta da
   SEFAZ-RS com a resposta guardada inteira, leitor isolado atrás de
   `LeitorNota`, associação GTIN > apelido > sem produto com aprendizado na
   correção, `vw_preco_produto` e a sugestão de transação de finanças pela
   API dela. Endpoints em `docs/compras/api.md`.
   **Pendente do usuário:** uma NFC-e real do RS, para validar o leitor
   (layout presumido do portal SVRS) e a URL montada só com a chave. Como
   fornecer, anonimizada: `compras/tests/amostras/README.md`. Até lá o
   teste da amostra fica pulado.

   **Pronto quando:** a nota de uma compra real vira itens com o total
   batendo com o da nota; ler o mesmo QR code de novo não cria outra nota;
   a segunda nota do mesmo mercado já vem com os itens associados pelo que a
   primeira ensinou; o preço de um produto aparece comparado entre dois
   mercados.
5. **Acesso por voz pelo MCP do vault.** Fora do escopo do serviço por
   enquanto: o servidor MCP do vault seria cliente da API do `compras`
   ("põe leite na lista", "o que falta comprar?"), sem acesso ao banco.

   **Feito (02/11/2026)** no servidor MCP do vault (`C:\Users\erikf\servidor`,
   fora deste repositório): `ver_lista_compras`, `adicionar_na_lista` (vários
   de uma vez, pelo nome, com quantidade opcional; acha o produto pela busca
   e cria se não existir), `marcar_comprado` e `marcar_acabou`. Falam com a
   API em `127.0.0.1` (`COMPRAS_API_URL`, padrão a porta 8001), com
   `X-Quem: voz` e `origem: voz`. Nenhuma apaga nada; nada de finanças.
   Testadas numa instância à parte (clone do vault e banco de teste); as
   ferramentas antigas e as recusas de segurança continuam iguais.

   **Pronto quando:** um pedido por voz cria o item na lista com a origem
   `voz`, e ele aparece nos dois celulares como qualquer outro.

### Riscos em aberto

Registrados para decidir na fase em que aparecem, sem solução escolhida.

- **Sinal ruim dentro do mercado.** O uso é justamente onde o celular pega
  mal. Sem resposta, marcar comprado falha ou trava a tela. O modelo já tem
  `id_cliente` para o reenvio não duplicar e o `/mudancas` para voltar a se
  atualizar, mas falta decidir: fila de escritas no aparelho (e o que fazer
  quando duas escritas offline se contradizem), cópia local da lista para
  abrir sem rede, service worker. Afeta as fases 1 e 2.
- **Leitura da NFC-e do RS.** O QR code traz a URL da consulta pública da
  SEFAZ-RS com a chave de acesso. Não há API pública para baixar o XML
  completo sem certificado digital: o caminho provável é ler a página da
  consulta, que é HTML feito para gente. Em aberto: se a página traz GTIN
  ou só o código interno do mercado; se há captcha ou limite de consultas;
  por quanto tempo a nota fica consultável; e o que fazer quando o formato
  mudar (o conteúdo original guardado permite reler, mas a leitura nova
  quebra até o leitor ser corrigido). Afeta a fase 4.
- **Ligação da nota com a transação do cartão vinda da Pluggy.** A
  `notas_fiscais.transacao_id` é um id simples de finanças, resolvido pela
  API (D-25). Em aberto: como achar a transação (valor e data, com a data
  da Pluggy podendo variar um dia na compra pendente, D-23); o nome do
  estabelecimento na fatura raramente é a razão social da nota; pagamento
  dividido, troco e desconto; a compra que ainda não chegou da Pluggy; e o
  id que deixa de valer quando a D-23 cancela e recria uma transação. Afeta
  a fase 4.

---

## Fora de escopo

Registrado para não ser reintroduzido por engano:

- Rateio ou divisão de despesas entre as duas pessoas (D-03)
- Multiusuário, autenticação complexa, deploy em nuvem
- Integração direta com API de cada banco. A sincronização via Pluggy saiu
  daqui: ver D-16 e Fase 5b
- App mobile nativo
