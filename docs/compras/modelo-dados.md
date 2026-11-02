# Modelo de dados — `compras`

Implementado (D-25): migrations `0001` (lista e despensa) e `0002` (nota
fiscal e preços), em `compras/alembic/versions/`. Postgres 16, schema `compras`, no
mesmo banco de finanças. Convenções gerais em `docs/CLAUDE.md`; aqui ficam
as do serviço e o que muda em relação a `docs/modelo-dados.md`.

## Convenções

- **Schema e role.** Todas as tabelas, enums, views e triggers ficam no
  schema `compras`, criadas pela role `casa_compras`, dona do schema. Ela
  não tem privilégio em `public`. As migrations são do próprio serviço
  (Alembic, `version_table_schema = 'compras'`).
- **Só `casa_compras` escreve.** Um trigger por comando em cada tabela do
  schema recusa INSERT, UPDATE, DELETE e TRUNCATE de qualquer outra role,
  com 42501. Existe por causa da role de finanças, que é superusuária e
  passa por cima de qualquer GRANT. É barreira contra engano: um
  superusuário ainda pode desligar o trigger, de propósito.
- **Ids.** `id bigint generated always as identity primary key`, como em
  finanças.
- **Id do cliente.** As tabelas que o celular cria (`itens_lista`,
  `produtos`) têm também `id_cliente uuid`, gerado no aparelho e único. É a
  idempotência do `POST`: no mercado, com sinal ruim, o celular reenvia o
  mesmo pedido sem saber se o primeiro chegou, e o segundo devolve o que o
  primeiro criou em vez de duplicar. Não substitui o `id`.
- **Timestamps.** `criado_em timestamptz not null default now()`,
  `atualizado_em timestamptz not null default now()`, atualizado por trigger
  em todo UPDATE. **Diferença em relação a finanças**, onde `atualizado_em`
  é nulo até o primeiro UPDATE: aqui ele é o relógio das mudanças que o
  celular busca (`GET /mudancas`, ver `api.md`) e precisa existir desde o
  INSERT. Índice em `atualizado_em` em toda tabela que o celular sincroniza.
- **Soft delete.** `deleted_em timestamptz` em toda tabela editável. Nenhum
  DELETE físico. Além de ser regra (CLAUDE.md, regra 2), é o que faz a
  remoção chegar ao outro celular: a linha apagada continua aparecendo nas
  mudanças, com `deleted_em` preenchido.
- **Auditoria.** Tabela `compras.auditoria`, no mesmo formato da de
  finanças, preenchida por trigger. O autor vem de
  `current_setting('app.autor', true)`, que o serviço seta por requisição
  com o "quem" (ou `leitura_nfce` na leitura da nota).
- **Quem.** Colunas `*_por text`. Por enquanto é texto livre, enviado pelo
  celular. Na fase de uso compartilhado passa a vir da identidade do
  Tailscale, posta pelo proxy (roadmap, "Lista de compras"). Não é
  `pessoa_id`: "quem" é quem está com o celular, e nada aqui precisa ligar
  isso a uma pessoa de finanças. Se um dia precisar, vira id simples, sem FK
  (D-25).
- **Texto normalizado.** `*_normalizado` é `upper`, sem acento e com
  espaços colapsados, para busca e casamento, como `locais.nome_normalizado`.
- **Quantidade** `numeric(12,3)`, **dinheiro** `numeric(12,2)`, **preço
  unitário** `numeric(12,4)` (a nota traz até 4 casas).

## Enums

```
situacao_item     : pendente | comprado
estado_despensa   : tem | acabando | acabou
origem_item       : manual | despensa | voz
origem_associacao : apelido | gtin | usuario
status_nota       : lida | erro
```

---

# Lista e despensa (fase 1)

## `secoes`
Seção do mercado: hortifrúti, padaria, frios, carnes, mercearia, bebidas,
limpeza, higiene. A lista sai ordenada pela `ordem`, que é o caminho que o
casal faz no mercado.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| ordem | int not null | posição no percurso; menor primeiro |
| deleted_em | timestamptz | |

Unique parcial em `nome` para linha viva. Uma seção "Sem seção", criada no
seed, com a maior `ordem`: é para onde vai o produto criado às pressas.

Uma ordem só, não uma por mercado. Se o percurso mudar muito entre
mercados, entra depois uma tabela `mercado_secoes(mercado_id, secao_id,
ordem)`, sem mexer nesta.

## `produtos`
O produto canônico, como o casal fala dele: "leite integral 1L", "papel
higiênico 12 rolos". Sem marca no nome: a marca muda de uma compra para a
outra, e o que se compara é o produto. O tamanho faz parte do nome porque
muda o preço.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| nome_normalizado | text not null | busca e unicidade |
| secao_id | fk secoes not null | |
| unidade_padrao | text | un / kg / L / pct; sugestão ao adicionar |
| id_cliente | uuid | único; produto criado pelo celular |
| deleted_em | timestamptz | |

Unique parcial em `nome_normalizado` para linha viva. A busca enquanto se
digita é `LIKE` no `nome_normalizado` (contém o texto; quem começa com ele
vem antes). Sem `pg_trgm` por enquanto: instalar a extensão exige
superusuário, e com dezenas de produtos ela não faz diferença.

## `itens_lista`
Uma lista só, a da casa. Sem tabela `listas`: lista de farmácia ou de festa
não foi pedida, e entra depois como coluna nova com valor padrão.

| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | |
| quantidade | numeric(12,3) | nula = "o de sempre" |
| unidade | text | |
| observacao | text | "o da caixa azul", "se tiver em promoção" |
| situacao | situacao_item not null default 'pendente' | |
| origem | origem_item not null default 'manual' | |
| adicionado_por | text not null | |
| comprado_por | text | |
| comprado_em | timestamptz | |
| id_cliente | uuid | único |
| deleted_em | timestamptz | remover da lista |

**Checks:** `situacao = 'comprado'` exige `comprado_por` e `comprado_em`;
`pendente` exige os dois nulos.

**Um pendente por produto:** unique parcial em `produto_id`
`where situacao = 'pendente' and deleted_em is null`. Os dois pondo "leite"
na lista ao mesmo tempo não viram dois itens: o segundo recebe o que já
existe (ver `api.md`). Depois de comprado, o mesmo produto pode voltar.

Item sempre tem produto. Digitar um nome que não existe cria o produto na
hora, em "Sem seção", na mesma requisição. Um item de texto solto, sem
produto, deixaria a lista sem ordem e a despensa sem ciclo.

Comprado não é apagado: fica como histórico (frequência de compra, base de
uma sugestão futura). A lista mostra os pendentes e os comprados recentes.

## `despensa`
O estado de cada produto em casa. Só os produtos que o casal quer
acompanhar têm linha; o resto não precisa de despensa.

| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | |
| estado | estado_despensa not null | |
| estado_por | text not null | quem mudou por último |
| estado_em | timestamptz not null | |
| deleted_em | timestamptz | parar de acompanhar |

Unique parcial em `produto_id` para linha viva.

**O ciclo com a lista**, sempre no service e na mesma transação:

| Acontece | Efeito |
|---|---|
| item da lista marcado como comprado | despensa do produto vai para `tem`, se o produto é acompanhado |
| despensa vai para `acabou` | cria item pendente, `origem = 'despensa'`, se não houver um |
| despensa vai para `acabando` | nada na lista; aparece como sugestão ("acabando em casa") |
| compra desfeita (comprado volta a pendente) | despensa volta para `acabou` |
| item removido da lista | despensa não muda |

"Acabando" não põe na lista sozinho: é o aviso de que vai acabar, e quem
decide se compra agora é o casal. "Acabou" põe, porque é o ciclo pedido
(acabou, volta para a lista).

---

# Nota fiscal e preços (fase 4)

## `mercados`
O estabelecimento, para comparar preço. Sai da nota: CNPJ, razão social e
endereço vêm nela.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | como o casal chama: "Zaffari da Ipiranga" |
| razao_social | text | como vem na nota |
| cnpj | text | 14 dígitos, sem máscara; único entre linhas vivas |
| endereco | text | |
| cidade | text | |
| deleted_em | timestamptz | |

Não reaproveita `locais` de finanças: seria FK entre schemas (D-25). Os dois
podem divergir; se um dia precisarem conversar, o CNPJ é a chave natural.

## `notas_fiscais`
Uma NFC-e lida. É o comprovante, como `importacoes` é o do extrato: guarda
inteiro o que veio da SEFAZ.

| coluna | tipo | notas |
|---|---|---|
| chave_acesso | text not null | 44 dígitos |
| mercado_id | fk mercados | nula se a leitura falhou antes de achar o emitente |
| emitida_em | timestamptz | |
| valor_total | numeric(12,2) | o "valor a pagar" da nota |
| desconto_total | numeric(12,2) not null default 0 | |
| url_consulta | text not null | a URL do QR code |
| conteudo_original | bytea | a resposta da consulta pública, inteira |
| conteudo_tipo | text | `text/html`, `application/xml` |
| leitor_versao | text | qual versão do leitor interpretou o conteúdo |
| status | status_nota not null | |
| erro_mensagem | text | |
| transacao_id | bigint | **id simples, sem FK** (D-25): a compra em finanças |
| lida_por | text not null | |
| deleted_em | timestamptz | |

Unique parcial em `chave_acesso` para linha viva, em qualquer status. É a
deduplicação da nota: ler o mesmo QR code duas vezes devolve a nota que já
existe, inclusive a que deu erro (reler é uma ação própria, não um segundo
cadastro).

O conteúdo original fica pelo mesmo motivo do PDF em `importacoes`: se o
leitor tiver um erro, ou a SEFAZ mudar o formato, dá para reinterpretar a
nota mesmo depois de ela sair da consulta pública. `leitor_versao` diz
quais notas reler.

## `nota_itens`

| coluna | tipo | notas |
|---|---|---|
| nota_fiscal_id | fk notas_fiscais not null | |
| linha_num | int not null | a ordem na nota |
| codigo | text | o código do produto no mercado |
| gtin | text | o código de barras, quando a nota traz |
| descricao_original | text not null | **imutável**: "LEITE INTEG ITALAC 1L" |
| quantidade | numeric(12,3) not null | |
| unidade | text | como vem: UN, KG, LT |
| valor_unitario | numeric(12,4) | |
| valor_total | numeric(12,2) not null | |
| desconto | numeric(12,2) not null default 0 | |
| produto_id | fk produtos | nulo enquanto não associado |
| origem_associacao | origem_associacao | o que decidiu o produto |

Unique em `(nota_fiscal_id, linha_num)`. `descricao_original` segue a regra
11 de finanças: é o texto cru, e a correção vai em `produto_id`.

Item sem produto não é erro: aparece numa fila de "associar", e o preço só
entra no histórico depois. A soma dos itens não é forçada a bater com o
total (há desconto na nota inteira); a diferença aparece, não bloqueia.

## `apelidos`
O texto da nota apontando para o produto. É a D-09 aplicada a produto:
cada associação feita à mão grava ou reforça um apelido, e a próxima nota
com o mesmo texto já vem associada.

| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | |
| texto_normalizado | text | o `descricao_original` normalizado |
| gtin | text | quando existe, casa antes do texto |
| mercado_id | fk mercados | nulo = vale em qualquer mercado |
| acertos | int not null default 1 | quantas correções reforçaram |
| criado_por | text not null | `usuario` ou `correcao` |
| deleted_em | timestamptz | |

**Checks:** `texto_normalizado` ou `gtin` preenchido. Unique parcial em
`(texto_normalizado, mercado_id) nulls not distinct` e em `gtin`, para
linha viva.

**Ordem no casamento:** GTIN, depois texto no mesmo mercado, depois texto em
qualquer mercado. O GTIN é o mesmo em toda loja; o texto, não: cada mercado
abrevia do seu jeito, por isso o apelido pode ficar preso a um mercado.

### O que a migration 0002 acrescentou ao que está acima

- `nota_itens` também tem `criado_em`, `atualizado_em` e `deleted_em`, como
  toda tabela editável, e um trigger que recusa mudar `descricao_original`.
- Checks: `produto_id` e `origem_associacao` nulos juntos; nota com
  `status = erro` tem `erro_mensagem`; `chave_acesso` com 44 dígitos e
  `cnpj` com 14; `apelidos.criado_por` em `usuario` ou `correcao`.
- O apelido aprendido de uma correção é gravado em duas linhas quando o item
  tem GTIN: uma do texto (presa ao mercado da nota) e uma do GTIN (sem
  mercado). Assim os dois índices únicos não brigam.
- O mercado nasce do CNPJ da chave, antes da consulta: uma nota com erro já
  tem `mercado_id`. O nome provisório é o CNPJ formatado, trocado pela
  razão social quando a nota é lida (e nunca por cima de um nome dado pelo
  casal).

## `vw_preco_produto` (view)
Por `produto_id` e `mercado_id`: último preço unitário e a data dele,
mínimo, máximo, média e contagem, a partir dos `nota_itens` associados de
notas vivas. View comum, não materializada: o volume de uma casa não pede
mais. Vira materializada se ficar lenta, com `REFRESH` ao ler uma nota.

Só entram notas com `status = lida` e com mercado. Sem o unitário na nota,
vale `valor_total / quantidade`. Unidade vazia conta como `UN`.

O preço comparado é o unitário de `nota_itens`, na unidade em que veio. Se
o mesmo produto aparecer em unidades diferentes (KG e UN), a view separa
por unidade em vez de juntar o que não é comparável.

---

# O que não existe aqui, de propósito

- **FK para qualquer tabela de finanças** (D-25).
- **Dinheiro na lista.** O preço só existe a partir da nota. Estimar o
  total da lista pelo histórico é uma consulta sobre `vw_preco_produto`,
  não uma coluna.
- **Fila offline no banco.** O uso sem sinal é risco em aberto (roadmap); o
  `id_cliente` é o que o modelo adianta para ele.
