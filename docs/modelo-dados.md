# Modelo de dados

Postgres 16. Convenções gerais em `CLAUDE.md`.

Toda tabela tem: `id bigint generated always as identity primary key`,
`criado_em timestamptz not null default now()`, `atualizado_em timestamptz`.
Tabelas de domínio editável têm também `deleted_em timestamptz` (soft delete).

## Enums

```
tipo_transacao      : despesa | receita | transferencia
tipo_conta          : corrente | poupanca | carteira | investimento | cartao
tipo_pagamento      : credito | debito | pix | dinheiro | boleto | transferencia
tipo_pessoa         : individual | conjunta
status_importacao   : processando | aguardando_revisao | concluida | erro | cancelada
status_item         : pendente | aprovado | rejeitado | duplicado
periodicidade       : mensal | bimestral | trimestral | semestral | anual
```

---

# Núcleo (v1)

## `pessoas`
| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| tipo | tipo_pessoa | `conjunta` é opcional; ver decisão D-03 |
| ativo | boolean default true | |

## `contas`
Onde o dinheiro está. Necessária para conciliação de saldo.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | "Conta Itaú", "Carteira" |
| tipo | tipo_conta | |
| titular_id | fk pessoas | null = conjunta |
| saldo_inicial | numeric(12,2) default 0 | |
| ativo | boolean default true | |

## `categorias`
Hierárquica por auto-relacionamento. Profundidade prática: 2 níveis.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| categoria_pai_id | fk categorias | null = categoria raiz |
| tipo | tipo_transacao | despesa ou receita |
| cor | text | usada nos gráficos |
| ativo | boolean default true | |

Unique em `(categoria_pai_id, nome)`. Impedir ciclo por check ou trigger.

## `formas_pagamento`
| coluna | tipo | notas |
|---|---|---|
| apelido | text not null | "Nubank Ana" |
| tipo | tipo_pagamento | |
| conta_id | fk contas | de onde sai o dinheiro |
| titular_id | fk pessoas | null = conjunta |
| dia_fechamento | smallint | só cartão de crédito |
| dia_vencimento | smallint | só cartão de crédito |
| ativo | boolean default true | |

## `locais`
| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| nome_normalizado | text not null | upper + sem acento, para matching |
| cidade | text | |
| cnpj | text | opcional |
| categoria_padrao_id | fk categorias | auto-categorização na ingestão |

Índice em `nome_normalizado`.

## `transacoes`
Coração do sistema. Uma linha por movimento.

| coluna | tipo | notas |
|---|---|---|
| data | date not null | data do fato |
| competencia | date not null | 1º dia do mês de referência; ver D-02 |
| valor | numeric(12,2) not null | sempre positivo; o sinal vem de `tipo` |
| tipo | tipo_transacao not null | |
| descricao | text not null | editável pelo usuário |
| descricao_original | text | texto cru do extrato, imutável |
| pessoa_id | fk pessoas | **null = gasto conjunto** |
| categoria_id | fk categorias | |
| forma_pagamento_id | fk formas_pagamento | |
| conta_id | fk contas | |
| local_id | fk locais | |
| importacao_id | fk importacoes | null = lançamento manual |
| conta_origem_id | fk contas | só quando tipo = transferencia |
| conta_destino_id | fk contas | só quando tipo = transferencia |
| parcela_num | smallint | |
| parcela_total | smallint | |
| grupo_parcelamento_id | uuid | liga as parcelas entre si |
| desconto_total | numeric(12,2) default 0 | cupom aplicado na nota inteira |
| observacao | text | |
| deleted_em | timestamptz | |

**Índices**: `data`, `competencia`, `categoria_id`, `pessoa_id`, `local_id`,
`forma_pagamento_id`, e o único parcial de deduplicação:

```sql
create unique index uq_transacoes_dedup
  on transacoes (hash_dedup) where deleted_em is null;
```

`hash_dedup` é coluna gerada a partir de
`data | valor | descricao_original | forma_pagamento_id | parcela_num`.

**Checks**: `valor > 0`; transferência exige origem e destino preenchidos e
`categoria_id` nulo; despesa/receita exige `conta_origem_id` nulo.

## `orcamentos`
| coluna | tipo | notas |
|---|---|---|
| categoria_id | fk categorias not null | |
| competencia | date not null | mês de referência |
| valor_meta | numeric(12,2) not null | |

Unique em `(categoria_id, competencia)`.

## `auditoria`
Preenchida por trigger, nunca por aplicação.

| coluna | tipo | notas |
|---|---|---|
| tabela | text not null | |
| registro_id | bigint not null | |
| acao | text not null | INSERT / UPDATE / DELETE |
| dados_antes | jsonb | |
| dados_depois | jsonb | |
| autor | text not null | usuário ou nome do agente |
| ocorrido_em | timestamptz default now() | |

O autor vem de `current_setting('app.autor', true)`, setado por sessão.

---

# Ingestão (fase 5)

## `importacoes`
| coluna | tipo | notas |
|---|---|---|
| arquivo_nome | text not null | |
| hash_arquivo | text not null unique | SHA-256; barra reimportação |
| origem | text | "nubank_fatura", "itau_extrato", "pluggy" |
| periodo_inicio / periodo_fim | date | |
| status | status_importacao | |
| parser_usado | text | determinístico ou llm |
| prompt_versao | text | |
| total_itens / itens_aprovados | int | |
| custo_tokens | jsonb | entrada, saída, custo estimado |

## `importacao_itens`
Staging. Nada aqui afeta relatórios.

| coluna | tipo | notas |
|---|---|---|
| importacao_id | fk importacoes not null | |
| linha_bruta | text not null | a linha exata do PDF, para conferência |
| linha_num | int | ordem em que apareceu no arquivo |
| data / valor / descricao_original | | extraídos |
| tipo_sugerido | tipo_transacao | necessário para promover; ver nota |
| competencia_sugerida | date | idem — na fatura é o mês do vencimento |
| categoria_sugerida_id | fk categorias | |
| local_sugerido_id | fk locais | |
| pessoa_sugerida_id | fk pessoas | |
| forma_pagamento_sugerida_id | fk formas_pagamento | distingue cartão de débito em conta |
| confianca | numeric(3,2) | 0.00 a 1.00 |
| origem_sugestao | text | parser / regra / alias / llm |
| status | status_item | |
| transacao_id | fk transacoes | preenchido ao aprovar |
| motivo_rejeicao | text | |
| id_externo | text | id da transação na Pluggy; nulo para PDF (0005) |
| observacao | text | nota do parser ou da sync para a revisão: duplicata possível, encargo, competência estimada (0006) |

`id_externo` tem único parcial, **em qualquer status**:

```sql
create unique index uq_importacao_itens_id_externo
  on importacao_itens (id_externo)
  where id_externo is not null and deleted_em is null;
```

É a deduplicação no staging da D-16: a sync roda todo dia sobre uma janela
que se sobrepõe à anterior, e sem essa barreira empilharia de novo os mesmos
itens aguardando revisão. Item rejeitado continua bloqueando, para não voltar
na sync seguinte. Itens de PDF ficam com `NULL` e não se esbarram.

As três colunas `*_sugerido*` de tipo, competência e forma de pagamento foram
acrescentadas na migration 0002: sem elas não há como promover um item, porque
`transacoes` exige `tipo` e `competencia`, e a forma de pagamento é o que
separa compra no cartão de débito em conta.

**Check**: item com `status = 'aprovado'` tem que apontar para uma transação;
item em qualquer outro status não pode apontar para nenhuma.

## `regras_categorizacao`
| coluna | tipo | notas |
|---|---|---|
| padrao | text not null | texto ou regex |
| tipo_match | text | contem / regex / exato |
| categoria_id / local_id / pessoa_id | fk | o que aplicar |
| prioridade | int default 100 | menor roda primeiro |
| criada_por | text | usuario / correcao_automatica |
| ativo | boolean default true | |

Toda correção manual do usuário na tela de revisão gera ou reforça uma regra.

## `contas_pluggy`
Mapeamento de uma conta da Pluggy para uma `conta` daqui (D-16, migration
0005). Conta da Pluggy sem mapeamento é ignorada pela sync, nunca adivinhada.

| coluna | tipo | notas |
|---|---|---|
| pluggy_item_id | text not null | a conexão na Pluggy; uma conexão tem várias contas |
| pluggy_account_id | text not null | único entre linhas vivas |
| conta_id | fk contas not null | |
| forma_pagamento_id | fk formas_pagamento not null | a padrão dos itens desta conta |
| sincronizar_desde | date not null | a partir daqui a Pluggy é a origem; antes, o PDF |
| ultimo_sync_em | timestamptz | |
| ativo | boolean not null default true | |
| deleted_em | timestamptz | |

Unique parcial em `pluggy_account_id` `where deleted_em is null`; índices em
`conta_id` e `forma_pagamento_id`. Triggers de auditoria e `atualizado_em`
como as demais tabelas.

**Não tem `pessoa_id`.** A pessoa sai de `contas.titular_id` (conta conjunta
sugere `NULL`, regra 3). Por isso incluir depois contas de outro titular é só
cadastrar o mapeamento de outra conexão — a estrutura não muda.

**`forma_pagamento_id` é obrigatória** porque entra no `hash_dedup` de
`transacoes`, a segunda barreira de deduplicação, e é o que separa compra no
cartão de débito em conta. Um mapeamento sem forma geraria itens sem forma,
resolvidos à mão um a um na revisão. O cartão adicional continua resolvido
pelo final do cartão, por cima desta padrão.

## Rastro do documento

`importacoes` guarda o arquivo inteiro em `arquivo_conteudo` (bytea) desde a
migration 0004, junto de `arquivo_tipo`. Nome e hash provam *qual* arquivo
originou a linha; o conteúdo permite reabri-lo. São ~200 KB por fatura, e o
backup do banco leva o comprovante junto — guardar só o caminho para o disco
deixaria o histórico apontando para o nada no dia em que a pasta mudasse.

O vínculo vai nos dois sentidos e é obrigatório por CHECK:

- `transacoes.importacao_id` → de qual arquivo a linha nasceu (nulo = digitada
  à mão, que é informação, não ausência);
- `importacao_itens.transacao_id` → em que transação o item virou, com
  `CHECK (status = 'aprovado') = (transacao_id IS NOT NULL)`.

`vw_transacoes_completa` expõe `importacao_id`, `importacao_arquivo`,
`importacao_em` e `importacao_tem_arquivo`.

**Importação da Pluggy** (`origem = 'pluggy'`) guarda como "arquivo" o JSON
bruto recebido: `arquivo_tipo = 'application/json'`, o JSON em
`arquivo_conteudo`, `hash_arquivo` = SHA-256 desse conteúdo e `arquivo_nome`
padronizado com origem e timestamp. É a opção (b) da Fase 5b, e não exige
mudança de schema: `arquivo_tipo` e `origem` são `text` sem CHECK e
`arquivo_conteudo` é `bytea`. Preserva o comprovante como já se faz com o PDF.

## Deduplicação

Três camadas, com propósitos diferentes:

| Onde | O quê | Quando |
|---|---|---|
| `uq_importacoes_hash_arquivo` | SHA-256 do arquivo | recusa reimportar o mesmo PDF (ou o mesmo JSON) |
| `uq_importacao_itens_id_externo` | id da transação na Pluggy | recusa o mesmo item no staging, em qualquer status |
| `uq_transacoes_dedup` | `hash_dedup` | recusa a mesma linha, na promoção |

O `id_externo` só existe para itens da Pluggy. Ele é necessário além do
`hash_dedup` porque a sync diária reapresenta a mesma transação antes de ela
ser promovida — e item rejeitado nunca chega a `transacoes`, então só o
staging consegue barrá-lo. Ele **não** pega a mesma compra vinda pelo PDF e
pela Pluggy (o texto da descrição difere); isso é evitado por
`contas_pluggy.sincronizar_desde`, uma origem por conta e período.

`hash_dedup` é gerado pelo banco a partir de `data`, `valor`,
`descricao_original`, `forma_pagamento_id` e `parcela_num`. **`forma_pagamento_id`
fazer parte do hash tem consequência**: qualquer coisa que faça a mesma linha
receber uma forma diferente entre duas importações desliga a deduplicação sem
erro nenhum. É por isso que `_ContextoEnriquecimento.carregar` ordena
explicitamente e `credito_padrao` é o de menor id — sem critério fixo, a ordem
física da tabela decidiria, e ela muda a cada UPDATE.

A importação ainda marca como `duplicado`, já no staging, o item cuja
transação gêmea já existe. Isso é aviso para a tela de revisão mostrar o que é
novo; a garantia continua sendo o índice único.

---

# Insights (fase 6)

## `relatorios`
| coluna | tipo | notas |
|---|---|---|
| competencia | date not null | dia 1º |
| tipo | text not null | mensal / anual / avulso |
| conteudo | text not null | markdown gerado |
| dados_base | jsonb not null | números que alimentaram o texto |
| periodo_dados | daterange | janela considerada, `[inicio, fim)` |
| prompt_versao | text not null | ex. `relatorio_mensal_v1` |
| execucao | jsonb not null | backend, modelo, tentativas, duração (D-12) |

Unique parcial em `(competencia, tipo)` para linha viva. Regerar o mês faz
soft delete do anterior e insere o novo — as duas versões ficam comparáveis.

`dados_base` é cópia, não cache: as transações continuam editáveis depois do
relatório escrito, então recalcular não reproduz o que o modelo viu. Sem a
cópia, conferir uma afirmação do texto seria impossível.

`periodo_dados` guarda o que "meses anteriores" queria dizer naquela execução
— o texto cita a média da janela, e só `competencia` não diz qual janela era.

---

# v2 — itens e produtos

## `itens_transacao`
| coluna | tipo | notas |
|---|---|---|
| transacao_id | fk transacoes not null | |
| produto_id | fk produtos | null enquanto não reconhecido |
| descricao | text not null | como veio na nota |
| quantidade | numeric(12,3) not null default 1 | |
| unidade | text | un / kg / L |
| valor_unitario | numeric(12,4) | 4 casas: combustível |
| valor_bruto | numeric(12,2) not null | |
| desconto | numeric(12,2) default 0 | |
| valor_liquido | numeric(12,2) not null | |
| categoria_id | fk categorias | opcional, mais fino que a transação |

A soma dos `valor_liquido` não é forçada a bater com o valor da transação —
notas parciais são comuns. Mostre a diferença na UI, não bloqueie.

## `produtos`
| coluna | tipo | notas |
|---|---|---|
| nome | text not null | nome canônico |
| marca | text | |
| unidade_padrao | text | |
| categoria_id | fk categorias | |

## `produto_aliases`
| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | |
| texto | text not null | como aparece na nota |
| local_id | fk locais | opcional |

Unique em `(texto, local_id)`. É o que faz "COCA COLA 2L" e
"REFRIG COCA 2000ML" convergirem para o mesmo produto.

## `mv_historico_preco` (view materializada)
Agrupada por `produto_id, local_id`: preço médio, mínimo, máximo, último
preço, data do último, contagem. `REFRESH` após cada importação aprovada.

## `tags` / `transacao_tags`
Corte transversal à categoria: "Viagem Gramado", "Reforma", nome de cada pet.
`tags(nome, cor)` e `transacao_tags(transacao_id, tag_id)` com PK composta.

## `recorrencias`
| coluna | tipo | notas |
|---|---|---|
| descricao | text not null | |
| categoria_id / forma_pagamento_id | fk | |
| valor_esperado | numeric(12,2) | |
| periodicidade | periodicidade | |
| dia_referencia | smallint | |
| ativo | boolean default true | |

Permite detectar reajuste de assinatura e cobrança que não veio.

## `anexos`
Guarda o PDF original vinculado à importação, para reprocessamento.
Arquivo em disco no volume, caminho e hash na tabela.

---

# Views de leitura sugeridas

- `vw_transacoes_completa` — transação com nomes já resolvidos por join,
  usada pela listagem e pelos filtros.
- `vw_gasto_por_pessoa` — três baldes que somam o total:
  `COALESCE(pessoa_id::text, 'conjunto')`. Transferências ficam de fora.
- `vw_orcamento_mes` — meta contra realizado por categoria.

**Regra de ouro do analytics**: `tipo = 'transferencia'` é excluído de todo
cálculo de gasto. Pagar fatura não é despesa nova.
