# Modelo de dados — notas fiscais, conferência e preços (D-33)

**Plano, não implementado.** Muda o modelo da fase 4 de compras
(`modelo-dados.md`, "Nota fiscal e preços", migration `0002`). Tudo aqui
seria uma migration nova do `compras` (a próxima livre, hoje `0006`), sem
tocar em finanças (D-25). Convenções do serviço em `modelo-dados.md`:
`numeric` para dinheiro e quantidade, soft delete, `*_por text`, auditoria
por trigger, só `casa_compras` escreve.

Legenda: **[existe]** já está no banco desde a `0002`/`0004`; **[novo]**
seria criado; **[muda]** existe e ganha coluna, check ou significado.

## O que muda, em uma frase cada

1. **Variante** entre o produto e o item da nota: o item exato, com marca e
   tamanho. O apelido, o GTIN e o código interno do mercado passam a
   apontar para ela. **[novo]**
2. **Unidade comparável**: cada variante diz quanto tem (1000 ml, 500 g,
   1 un) ou que é pesada na hora; o preço sai em R$/kg, R$/L ou R$/un.
   **[novo]**
3. **Preço cheio, desconto e preço pago** por item, com o desconto da nota
   inteira rateado. **[muda]**
4. **Item da lista <-> item da nota**: a ligação que a conferência grava, e
   o fechamento do item comprado (por nota, sem nota, não comprei).
   **[novo]**
5. **Marco da conferência**: a nota conferida e o que ainda espera nota.
   **[novo]**

## Enums

```
origem_associacao : apelido | gtin | usuario             [existe]
fechamento_item   : nota | sem_nota | nao_comprei         [novo]
origem_item       : + nota                                [muda: valor novo]
medida_base       : g | ml | un                           [existe, D-30]
```

`origem_item = nota` marca o item que a conferência criou: a diferença de
quantidade que volta para a lista. É o mesmo papel do `cardapio` da D-30.

## Validação com nota real (18/11/2026) [respondida]

Uma NFC-e real de supermercado do RS (24 itens, 15/11/2026), lida pela
consulta por chave da SEFAZ-RS, que devolve a página "Consulta Completa da
NFC-e". A amostra anonimizada está em
`compras/tests/amostras/nfce_rs_anonimizada.html`. O layout do QR code
(portal SVRS) ainda não foi visto com nota real; se ele trouxer algo a mais,
entra aqui como diferença.

| pergunta | resposta | ramo escolhido |
|---|---|---|
| código de barras por item? | **não**: só o código interno do mercado (18 dígitos com zeros à esquerda) | **sem código de barras**: variante por `(mercado, código interno)`, com "juntar variantes" |
| desconto por item e da nota? | **só o da nota** ("Valor descontos R$") | **desconto só da nota**: rateado, preço pago marcado como estimativa |
| unidade e quantidade pesada? | **sim**: `KG` com 4 casas (0,5119 kg × 15,90 = 8,14) e `UN` | pesada pela unidade, R$/kg direto |

A página traz também:

- **a forma de pagamento** com o valor ("Cartão de Crédito 398,56"): entra
  na ligação com a despesa;
- **a hora da emissão** (dd/mm/aaaa hh:mm:ss);
- **o tamanho na descrição** de boa parte dos itens ("IOG GREGO BATAVO TRAD
  450G", "SUCO ... 1,5L", "250ML", "GF1KG"): o leitor sugere a medida da
  variante;
- **o CPF do consumidor**, quando informado no caixa: nunca é lido para o
  modelo nem vai para amostra sem anonimizar.

O que isso muda, em resumo: a identidade da variante sem GTIN é o código do
mercado; o desconto é sempre rateado; a sugestão de medida vem da descrição;
a forma de pagamento ajuda a escolher a despesa.

---

## `produtos` [existe, muda de sentido]

Continua sendo o que a lista, a despensa e o cardápio usam. A D-33 o quer
**genérico** ("leite"), e hoje o modelo pede o contrário: o tamanho faz parte
do nome ("leite integral 1L", `modelo-dados.md`) porque o preço era por
produto. Com a variante, o tamanho e a marca saem do produto.

- **Nenhuma coluna nova.** `medida_base` e `medida_por_unidade` (D-30) ficam
  como "a embalagem de sempre", que o cardápio usa para converter receita em
  unidades de compra. A variante tem a sua própria medida, que é a que vale
  para o preço.
- **Os produtos que já existem não são renomeados pela migration.** Quem tem
  tamanho no nome continua assim até o casal mudar; a primeira nota que
  trouxer aquele produto cria a variante com o tamanho certo. Renomear em
  massa mexeria na lista, nas receitas e na despensa de uma vez, sem ganho
  para o preço.

## `variantes` [novo]

O item exato que se compra. Uma variante pertence a um produto; um produto
tem quantas variantes o casal já comprou.

| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | |
| nome | text not null | "Leite Italac Integral 1L"; nasce da descrição da nota, editável |
| nome_normalizado | text not null | busca |
| marca | text | opcional; a nota raramente separa |
| gtin | text | código de barras (8, 12, 13 ou 14 dígitos); nulo quando a nota não traz, que é o caso da Consulta Completa da SEFAZ-RS |
| medida_base | medida_base | `g`, `ml` ou `un`: em que o preço é comparado |
| conteudo | numeric(12,3) | quanto de `medida_base` tem **uma unidade** da variante (1000 ml, 500 g, 12 un). Nulo na pesada |
| pesada | boolean not null default false | vendida por peso no caixa (hortifrúti, frios, carne): a quantidade da nota já é o peso |
| criado_por | text not null | |
| deleted_em | timestamptz | |

**Checks:** `pesada` exige `medida_base = 'g'` e `conteudo` nulo; não
pesada com `medida_base` preenchida exige `conteudo > 0`. Medida nula é
permitida: a variante existe e associa, só não entra na comparação por
unidade até alguém dizer quanto ela tem (a fila "sem medida", como a do
cardápio).

**Unique parcial** em `gtin` para linha viva: um código de barras, uma
variante. Sem unique no nome: duas marcas podem abreviar igual.

## `variante_codigos` [novo] — ramo "sem código de barras"

A nota real não traz GTIN: traz o **código interno do mercado**, estável
para o mesmo item naquele mercado. Ele é a identidade da variante sem GTIN,
mas só dentro do mercado, e uma variante pode ter um código em cada mercado
onde foi comprada. Por isso fica numa tabela à parte.

| coluna | tipo | notas |
|---|---|---|
| variante_id | fk variantes not null | |
| mercado_id | fk mercados not null | |
| codigo | text not null | sem os zeros à esquerda ("1077397") |
| criado_por | text not null | |
| deleted_em | timestamptz | |

**Unique parcial** em `(mercado_id, codigo)` para linha viva.

**Ordem de casamento** do item da nota: GTIN (quando houver) ->
`(mercado, código)` -> apelido de texto no mesmo mercado -> texto em outros
mercados, só se todos concordam (como hoje). O código ganha do texto porque
o mercado abrevia a mesma coisa de jeitos diferentes ao longo do tempo, e o
código não muda.

**Juntar variantes.** Sem código de barras, o mesmo produto comprado em dois
mercados nasce como **duas variantes**, uma por código. Quando o casal diz
que são a mesma coisa, a ação "juntar variantes" mantém uma, move para ela os
`variante_codigos`, os apelidos e os itens de nota da outra, e apaga a outra
(soft delete). Juntar não mexe na nota nem no preço pago: só no agrupamento.
O "onde é mais barato" depende disso para comparar a variante entre
mercados; até juntar, a comparação entre mercados vem do agregado por
produto, em R$/kg, R$/L ou R$/un.

**Sugestão de medida pela descrição.** Ao criar a variante, o leitor procura
na descrição o tamanho no fim de uma palavra ou sozinho: `450G`, `1KG`,
`1,5L`, `250ML`, `C/12`. Achou um só: sugere `medida_base` e `conteudo`
(450G -> `g`, 450; 1,5L -> `ml`, 1500). Achou nenhum ou mais de um: a
variante nasce sem medida e vai para a fila "sem medida". A sugestão é só
sugestão: quem grava é a associação, com confirmação. Unidade `KG` na nota
marca a variante como pesada, sem perguntar.

**Por que a medida é da variante e não do item da nota.** O tamanho é do
produto na prateleira, não da compra: cadastrado uma vez, vale para todas as
notas seguintes, de qualquer mercado. A nota às vezes traz o tamanho na
descrição ("LEITE INTEG ITALAC 1L"); o leitor pode sugerir, mas quem grava é
a associação, com confirmação.

## `nota_itens` [existe, muda]

Colunas atuais: `linha_num`, `codigo`, `gtin`, `descricao_original`
(imutável), `quantidade`, `unidade`, `valor_unitario`, `valor_total`,
`desconto`, `produto_id`, `origem_associacao`.

| coluna | tipo | situação | notas |
|---|---|---|---|
| variante_id | fk variantes | **novo** | o que a associação decide agora |
| produto_id | fk produtos | **muda** | passa a ser cópia do produto da variante, mantida por trigger; continua existindo para a fila, os índices e a view atual |
| valor_total | numeric(12,2) | **muda de nome no texto, não no banco** | é o **preço cheio** da linha, como a nota mostra (quantidade × unitário) |
| desconto | numeric(12,2) | existe | desconto **da linha**, quando a nota o traz por item |
| item_lista_id | fk itens_lista | **novo** | o item da lista que esta linha atendeu, gravado na confirmação da conferência; nulo = extra (ou ainda não conferida) |

**Checks novos:** `variante_id` nulo implica `produto_id` nulo (um item sem
variante não está associado); a associação antiga, só com produto, é
migrada criando uma variante por `(produto, descrição normalizada, mercado)`
a partir dos itens que já existem.

**Preço pago** não é coluna: `valor_total - desconto - desconto_rateado`,
calculado na view. O `desconto_rateado` é a parte do desconto da nota
inteira (`notas_fiscais.desconto_total`, menos a soma dos descontos de linha)
que cabe ao item, proporcional ao `valor_total`. Fica fora do banco porque
depende da nota inteira e muda se uma linha for corrigida. A soma dos preços
pagos de uma nota é igual ao `valor_total` dela (o resto do arredondamento
vai para a linha de maior valor).

**Ramo "desconto só da nota" (validado em 18/11/2026).** A Consulta
Completa mostra só o desconto da nota inteira. Então o `desconto` de linha
fica zero e o rateio faz todo o trabalho: o preço pago de cada item numa
nota com desconto é uma **estimativa**, e a view diz isso
(`preco_pago_estimado = true` quando o item recebeu parte de um desconto da
nota). Uma promoção de um item só ("leve 3, pague 2") se dilui na nota
inteira; por isso o histórico de preço mostra o preço cheio ao lado do
pago. Se o layout do QR code trouxer desconto por item, a coluna de linha
passa a ser preenchida e o rateio só divide o resto, sem mudar o modelo.

**Quantidade comparável** também é calculada, não guardada:

| variante | unidade na nota | quantidade comparável |
|---|---|---|
| pesada | KG | `quantidade × 1000` g |
| pesada | G | `quantidade` g |
| `conteudo` 1000, `ml` | UN | `quantidade × 1000` ml |
| `conteudo` 12, `un` | UN (a dúzia) | `quantidade × 12` un |
| sem medida | qualquer | nula: não entra no R$/unidade |

O preço comparável é `preço pago / quantidade comparável`, exibido por kg,
por L ou por unidade (× 1000 para g e ml). Calculado em `numeric`, nunca
float.

## `apelidos` [existe, muda]

Passa a apontar para a variante. A ordem de casamento ganha o código do
mercado: GTIN, `(mercado, código)` (`variante_codigos`), texto no mesmo
mercado, texto em qualquer mercado (`api.md`, "Associação automática").

| coluna | situação | notas |
|---|---|---|
| variante_id | **novo**, not null depois da migração | o alvo do apelido |
| produto_id | **muda** | cópia do produto da variante, mantida por trigger, para não quebrar o que lê produto |
| gtin | **muda** | o apelido de GTIN deixa de ser necessário: o GTIN mora na variante. Os existentes são migrados para `variantes.gtin` e apagados (soft delete) |

"Pergunta uma vez e aprende": a primeira associação manual de um texto grava
o apelido (como hoje); a próxima nota com o mesmo texto no mesmo mercado já
vem com a variante.

## `notas_fiscais` [existe, muda]

| coluna | tipo | situação | notas |
|---|---|---|---|
| conferida_em | timestamptz | **novo** | quando a conferência foi confirmada; nulo = ainda não |
| conferida_por | text | **novo** | |
| transacao_id | bigint | existe | sem FK (D-25); confirmado pelo usuário, ou preenchido sozinho quando a pendente ligada consolida |
| pendente_id_externo | text | **novo** | o id da Pluggy da compra **pendente** do cartão (D-28) a que o usuário ligou a nota; nulo quando ligada direto a uma transação ou sem ligação |
| forma_pagamento_nota | text | **novo** | a forma como a página mostra ("Cartão de Crédito", "Pix", "Dinheiro"); com mais de uma, a de maior valor. Só ajuda a ligação; não é a forma de finanças |
| despesa_lancada_pela_nota | boolean not null default false | **novo** | a transação ligada foi criada por "lançar despesa pela nota" |

**Ligação com a pendente.** A compra do cartão lida no mesmo dia quase
sempre ainda é pendente, e a pendente não tem id em `transacoes`: tem o id
da Pluggy, e a D-28 garante que ela consolida com o **mesmo** id. Por isso a
nota guarda esse id e a ligação se completa sozinha:

- confirmar uma pendente grava `pendente_id_externo` e deixa
  `transacao_id` nulo;
- quando finanças tiver uma transação com aquele id, o `compras` preenche
  `transacao_id` e limpa `pendente_id_externo`, sem perguntar;
- se a pendente sumir de finanças sem virar transação (cancelada, ou
  recriada com outro id), a ligação é desfeita e a nota volta para a fila
  "sem despesa", com a sugestão por data e valor. É o único caso em que se
  pergunta de novo.

**Check:** `transacao_id` e `pendente_id_externo` nunca preenchidos juntos.

**Forma de pagamento na ligação.** A sugestão de despesa ordena primeiro as
candidatas cuja forma é do mesmo tipo que a da nota (cartão de crédito com
cartão de crédito, Pix com Pix), depois pelo dia mais próximo. Não filtra:
o mercado às vezes registra débito como crédito.

**Nota sem despesa: "lançar despesa pela nota".** Caso real (18/11/2026):
compra paga com um cartão que não está ligado à Pluggy, então nenhuma
despesa vai chegar sozinha. A nota sem ligação oferece criar a transação em
finanças, com o que o usuário escolhe:

- **valor** e **data**: os da nota (total e dia da emissão), editáveis;
- **estabelecimento**: o mercado da nota (vira o local e a descrição);
- **pessoa**: quem pagou, ou conjunto;
- **forma de pagamento**: uma forma cadastrada em finanças, por exemplo
  "Cartão da Laura". Cadastrar a forma é com o usuário, na tela de Contas e
  cartões; a ação só lista as que existem;
- **categoria**: sugerida pelos itens. Cada seção do `compras` tem uma
  categoria de finanças (`secoes.categoria_id_financas`, bigint sem FK,
  D-25, nulo = sem sugestão); a sugestão é a categoria com mais valor entre
  os itens associados. Sem item associado, a categoria da última despesa
  ligada a uma nota do mesmo mercado. O usuário confirma.

Quem grava é **finanças**, pelo endpoint de lançamento manual que já existe
(`POST /api/transacoes`, `importacao_id` nulo), com uma marca nova
`transacoes.lancada_pela_nota boolean` (migration de finanças). A transação
nasce ligada à nota, com `despesa_lancada_pela_nota = true`.

**Quando a mesma compra chega depois pela Pluggy** (a dona do cartão conecta
a conta, por exemplo): um item da Pluggy com **a mesma data, o mesmo valor e
a mesma forma de pagamento** de uma transação `lancada_pela_nota` viva não é
promovido sozinho (D-21, "sem suspeita de duplicata"): vai para a revisão
como **possível duplicata**, com a observação "lançada pela nota". Na
revisão:

- **juntar**: fica a transação **do banco** (a promovida do item da Pluggy),
  a lançada pela nota é apagada (soft delete) com
  `transacoes.substituida_por_id` apontando para a do banco (migration de
  finanças), e a ligação da nota passa para ela. Quem move a ligação é o
  `POST /notas/consolidar-ligacoes` (nota cuja transação foi substituída
  segue o `substituida_por_id`), sem perguntar de novo;
- **são duas**: as duas ficam, como hoje na revisão de duplicata.

O casamento pela forma só funciona se, ao conectar a conta, o cartão da
Pluggy for mapeado para a **mesma** forma que o usuário cadastrou ("Cartão
da Laura"), e não para uma nova. A tela de mapeamento oferece as formas que
já existem.

`mercados` continua com esse nome para farmácia e posto: é "o
estabelecimento". Renomear a tabela não compra nada.

## `itens_lista` [existe, muda]

O estado "comprado, aguardando nota" **não é uma situação nova**: é
`situacao = comprado` com `fechamento` nulo. Assim o pendente único, os
checks e o `/mudancas` continuam iguais, e a lista o mostra pelo que já tem.

| coluna | tipo | situação | notas |
|---|---|---|---|
| fechamento | fechamento_item | **novo** | nulo enquanto aguarda nota; `nota` quando uma nota o confirmou; `sem_nota` com "comprei sem nota"; `nao_comprei` quando voltou para a lista |
| fechado_em | timestamptz | **novo** | |
| fechado_por | text | **novo** | quem respondeu, ou `leitura_nfce` quando a nota fechou |
| perguntado_em | timestamptz | **novo** | quando a pergunta dos 7 dias foi mostrada e respondida ou dispensada; nunca pergunta de novo |

**"Não comprei"** é o desfazer de hoje: o item volta a `pendente`, sem
`comprado_por`/`comprado_em` e sem fechamento. Se outro pendente do mesmo
produto já existir (alguém o pôs de novo na lista nesse meio-tempo), o
pendente único manda: este item é removido (soft delete) com
`fechamento = nao_comprei`, e o outro fica.

**Checks:** `fechamento` em `nota` ou `sem_nota` exige `situacao =
comprado`; `nao_comprei` só em linha apagada. `fechamento` preenchido exige
`fechado_em` e `fechado_por`.

**Migração dos comprados antigos.** Todo item comprado antes da D-33 recebe
`fechamento = sem_nota` com `fechado_por = migracao`. Sem isso, o histórico
inteiro apareceria como "aguardando nota" no dia seguinte.

**Desfazer a compra** (`POST /lista/itens/{id}/desfazer`) continua valendo
para o item aguardando nota e limpa o fechamento. Item já fechado por nota
não se desfaz por ali: a nota é a fonte da verdade (409).

## O marco da conferência [novo, sem tabela]

A D-33 fala em "os marcados como comprados desde a última nota lida". No
modelo, o marco é **o próprio fechamento**: entram na conferência os
pendentes e os comprados com `fechamento` nulo. É o mesmo conjunto no caso
comum (o que se marcou desde a última nota é o que ainda não fechou) e não
quebra nos casos que uma data quebraria:

- uma nota antiga lida depois de uma nova não "volta o relógio";
- duas notas do mesmo dia (mercado e padaria) conferem o mesmo conjunto, e
  o que a primeira fechou não aparece na segunda;
- o item que espera nota há 5 dias continua entrando em toda conferência
  até fechar, que é o "confirmado sozinho em qualquer nota seguinte".

Uma regra de data protege contra o engano oposto: o comprado só casa com
nota **emitida depois de `comprado_em` menos 1 dia**. Sem ela, ler uma nota
velha esquecida confirmaria o leite marcado hoje.

## Casamento entre lista e nota [novo, regra do service]

Lista pede produto; nota traz variante. Casam pelo **produto** da variante.

| item da lista | na nota? | efeito na confirmação |
|---|---|---|
| comprado, aguardando | sim | `fechamento = nota`; a linha da nota leva `item_lista_id` |
| pendente | sim | marca comprado (`comprado_por = quem conferiu`, `comprado_em = emitida_em`), fecha por nota, **avisa** |
| — | sim, fora da lista | extra: a linha fica com `item_lista_id` nulo e a nota conferida |
| pendente | não | continua pendente |
| comprado, aguardando | não | continua aguardando; aos 7 dias, a pergunta |
| qualquer | sim, quantidade menor | pergunta; "volta" cria um pendente com a diferença (`origem = nota`), ou soma ao pendente que já existir |
| — | item sem variante | pergunta (associar); sem resposta, a linha fica na fila e fora da conferência |

**Quantidade menor** só se compara quando as unidades batem (a lista em
`un` e a nota em `UN`, ou a lista em `kg` e a variante pesada). Item da lista
sem quantidade ("o de sempre") nunca é "menor". Duas linhas da nota com o
mesmo produto somam antes de comparar.

## Despensa [existe, regra muda]

A linha da nota com variante leva o produto para `tem` **só se** a
despensa já acompanha o produto **ou** a linha atendeu um item da lista
(`item_lista_id`). Neste último caso vale o que acontece hoje ao marcar
comprado: o produto acompanhado vai para `tem`; o não acompanhado continua
sem linha.

O **extra** de um produto que a despensa não acompanha fica só no histórico
de preço. A conferência o mostra com a ação "acompanhar na despensa", que é
o `PUT /despensa/{produto_id}` de hoje com `tem`. Assim a despensa não passa
a acompanhar, sem ninguém pedir, tudo o que já se comprou na farmácia e no
posto.

**Proteção da nota lida com atraso:** a nota só muda a despensa se
`emitida_em` for depois do `estado_em` atual. Uma nota lida com atraso não
desfaz um "acabou" marcado depois da compra.

O item "aguardando nota" não mexe na despensa (já está em `tem` desde a
marcação). "Não comprei" leva para `acabou`, como o desfazer de hoje.

## Views

- **`vw_preco_variante`** [novo]: uma linha por item de nota lida e
  associada: variante, produto, mercado, data, quantidade, unidade, preço
  cheio, desconto (linha + rateado), preço pago, quantidade comparável e
  preço comparável (por kg, L ou un). Base de todas as consultas de preço.
- **`vw_preco_produto`** [muda]: hoje agrega `nota_itens` por produto,
  mercado e unidade da nota. Passa a agregar `vw_preco_variante` por
  produto, mercado e `medida_base`: último preço comparável e a variante
  dele, mínimo, máximo, média e contagem. As linhas sem quantidade
  comparável ficam de fora da agregação e aparecem numa contagem à parte.

Continuam views comuns: o volume de uma casa não pede materializada.

## O que não muda

- `notas_fiscais.conteudo_original`, `leitor_versao`, a deduplicação pela
  chave e o `reler`.
- O `transacao_id` sem FK e resolvido pela API de finanças (D-25).
- Em finanças, a nota só cria transação por pedido explícito ("lançar
  despesa pela nota"), pela API de finanças, e nunca altera nem apaga uma.

## Fora deste modelo, de propósito

- **Quantidade na despensa.** Continua sem (D-30): "tem" é "tem".
- **Preço na lista.** Estimar o total da lista é consulta sobre
  `vw_preco_produto`, não coluna.
- **Abastecimento.** Direção (D-33): nota de posto (litros = quantidade,
  R$/L = preço comparável de uma variante `ml`) mais a quilometragem
  informada. A quilometragem é a única coisa que a nota não traz e pede uma
  tabela própria; fica para o bloco dele.
