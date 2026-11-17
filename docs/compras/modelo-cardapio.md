# Modelo de dados — cardápio (D-30)

**Implementado (migration 0004).** Diferenças em relação ao plano no fim
deste arquivo. Módulo do serviço `compras`, no mesmo
schema e com as mesmas convenções de `modelo-dados.md` (role
`casa_compras`, trigger que recusa outras roles, `criado_em`/`atualizado_em`
por trigger, `deleted_em`, auditoria, `*_normalizado`, `numeric`). Aqui fica
só o que é novo. Endpoints em `api-cardapio.md`.

O fluxo que o modelo serve:

```
receitas -> cardápio da semana -> roteiro de preparo -> lista de compras
                (quem come,         (sessões do fim       (soma, converte,
                 quanto)             de semana)            desconta a despensa)
```

## Enums novos

```
tipo_refeicao   : cafe_da_manha | lanche | almoco | janta
unidade_medida  : g | kg | ml | l | un | colher_sopa | colher_cha | xicara | a_gosto
medida_base     : g | ml | un
origem_item     : + cardapio        (valor novo no enum que já existe)
```

---

# Unidades: a forma escolhida

O problema: a receita fala "2 cebolas", "200 g de queijo", "1 colher de
azeite"; o produto é comprado "por kg" (cebola), "por pacote de 500 g"
(queijo ralado) ou "por garrafa de 500 ml" (azeite). A lista precisa dizer
quanto comprar, na unidade em que se compra.

**Duas colunas novas em `produtos` e uma tabela fixa no código.** Nada de
tabela de conversões por produto, nada de densidade.

| coluna nova em `produtos` | tipo | notas |
|---|---|---|
| medida_base | medida_base | em que o produto é medido: `g`, `ml` ou `un`. Nulo = sem conversão |
| medida_por_unidade | numeric(12,3) | quanto de `medida_base` tem **uma unidade** do produto (uma embalagem, ou uma peça). Nulo quando não se aplica |

Exemplos:

| produto | `unidade_padrao` (já existe) | `medida_base` | `medida_por_unidade` |
|---|---|---|---|
| cebola | kg | g | 150 (peso médio de uma cebola) |
| leite integral 1L | un | ml | 1000 |
| queijo ralado 50g | pct | g | 50 |
| ovos | un | un | — |
| azeite 500ml | un | ml | 500 |
| sal | un | — | — (só "a gosto") |

**Conversões fixas, no código** (`unidade_medida` para a base):
`kg` = 1000 g, `l` = 1000 ml, `colher_sopa` = 15 ml, `colher_cha` = 5 ml,
`xicara` = 240 ml. Colher e xícara são volume: "1 colher de azeite" vira
15 ml. `a_gosto` não tem quantidade.

**Da receita para a base do produto:**

1. Mesma dimensão (massa com `g`, volume com `ml`, `un` com `un`): tabela
   fixa.
2. Receita em `un`, produto em `g`/`ml`: multiplica por
   `medida_por_unidade` (2 cebolas = 300 g).
3. Receita em `g`/`ml`, produto em `un`: divide por `medida_por_unidade`
   (100 g de ovo, se alguém escrever assim, com o ovo a 50 g).
4. Massa com volume (colher de farinha num produto em `g`), ou falta o
   dado: **não converte**. O item vai para a lista sem quantidade, com a
   quantidade da receita na observação ("cardápio: 2 colher_sopa"), e a
   geração devolve um aviso "cadastre a medida de farinha". Não bloqueia.

**Da base para a unidade de compra**, pela `unidade_padrao` que o produto
já tem:

- `kg`, `g`, `l`, `ml`: converte direto (300 g de cebola = 0,300 kg).
- `un`, `pct` ou outra: divide por `medida_por_unidade` e **arredonda
  para cima** (1.500 ml de leite = 2 un). Embalagem não se compra pela
  metade.

Por que assim: o casal cadastra um número por produto, uma vez, e só nos
produtos que aparecem em receita. A tabela fixa cobre a cozinha comum; o
que ela não cobre cai no caso 4, que é visível e não trava nada. Densidade
(colher de farinha em gramas) e uma tabela de conversões por produto ficam
para quando o caso 4 aparecer de verdade.

---

# Pessoas e perfil

## `pessoas`
Quem come. Não é `pessoa_id` de finanças (D-25: sem FK, e nada aqui precisa
de finanças). Liga-se à identidade que o serviço já tem
(`identidades_tailscale`), quando há uma.

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | "Erik", "Laura"; único entre linhas vivas |
| identidade_id | fk identidades_tailscale | nulo = pessoa sem login (visita, criança); única entre linhas vivas |
| porcao_padrao | numeric(4,2) not null default 1 | multiplicador: 1 = uma porção da receita; 1,5 = uma e meia |
| deleted_em | timestamptz | |

**Check:** `porcao_padrao > 0`.

A FK aponta de `pessoas` para a identidade, e não o contrário, para não
mexer em `identidades_tailscale` e porque pode haver pessoa sem login. O
uso na v1 é só a tela: "eu" (pelo `/eu`) aparece primeiro.

**Metas nutricionais (futuro, sem coluna na v1).** Previstas como colunas
nulas de `pessoas`: `meta_kcal int`, `meta_proteina_g numeric(6,1)`,
`meta_carboidrato_g numeric(6,1)`, `meta_gordura_g numeric(6,1)`, por dia.
Entram na migration da subfase de nutrientes, junto com o que as usa.
Ver "Nutrientes", abaixo.

---

# Receitas

## `receitas`

| coluna | tipo | notas |
|---|---|---|
| nome | text not null | |
| nome_normalizado | text not null | busca; único entre linhas vivas |
| tipo | tipo_refeicao not null | o tipo habitual; filtro e sugestão, não restringe onde entra |
| rendimento_porcoes | numeric(6,2) not null | quantas porções a receita, como escrita, rende |
| tempo_preparo_min | int | ativo + forno; ordena o roteiro |
| modo_preparo | text | texto livre |
| pode_antecipar | boolean not null default false | pode ser feita antes (no fim de semana) |
| dura_dias | int | dias que dura pronta, na geladeira; exigido se `pode_antecipar` |
| pode_congelar | boolean not null default false | |
| id_cliente | uuid | único; criada pelo celular |
| deleted_em | timestamptz | |

**Checks:** `rendimento_porcoes > 0`; `pode_antecipar` exige
`dura_dias >= 1`; `tempo_preparo_min >= 0`.

Uma receita de lanche pode ir no café da manhã: o tipo da receita é o
habitual, o da refeição é onde ela foi posta.

## `receita_ingredientes`

| coluna | tipo | notas |
|---|---|---|
| receita_id | fk receitas not null | |
| produto_id | fk produtos not null | o mesmo cadastro da lista e da despensa |
| quantidade | numeric(12,3) | nula só com `unidade = a_gosto` |
| unidade | unidade_medida not null | |
| observacao | text | "picada", "para a cobertura" |
| ordem | int not null | a ordem na receita |
| deleted_em | timestamptz | |

**Check:** `(unidade = 'a_gosto') = (quantidade is null)`; `quantidade > 0`.

Sem unique em `(receita_id, produto_id)`: açúcar na massa e na cobertura
são duas linhas, e a lista soma. Ingrediente sempre tem produto, pelo mesmo
motivo do item da lista: sem produto não há despensa nem lista. Digitar um
nome novo cria o produto em "Sem seção", como no `POST /lista/itens`.

Editar uma receita afeta só as semanas atuais e futuras (D-30): a edição
nunca muda um ingrediente no lugar, apaga (soft delete) e cria outro. Uma
semana passada lê os ingredientes vivos no fim dela (`criado_em` até o
domingo, `deleted_em` nulo ou depois). Os campos da própria receita não
têm histórico na v1.

---

# Semana

## `semanas`
Um cardápio por semana, de segunda a domingo.

| coluna | tipo | notas |
|---|---|---|
| inicio | date not null | sempre segunda-feira; única entre linhas vivas |
| observacao | text | |
| deleted_em | timestamptz | |

**Check:** `extract(isodow from inicio) = 1`.

## `refeicoes`
Um prato num dia e tipo de refeição.

| coluna | tipo | notas |
|---|---|---|
| semana_id | fk semanas not null | |
| dia | date not null | dentro da semana |
| tipo | tipo_refeicao not null | |
| receita_id | fk receitas | nula = sem receita ("jantar fora", "sobras"), com `observacao` |
| observacao | text | |
| ordem | int not null default 0 | ordem dos pratos no mesmo dia e tipo |
| deleted_em | timestamptz | |

**Checks:** `dia between inicio and inicio + 6` (por trigger, que lê a
semana); `receita_id` ou `observacao` preenchido.

Sem unique em `(semana_id, dia, tipo)`: o almoço pode ser arroz, feijão e
frango, três receitas no mesmo horário. Cada linha é um prato.

## `refeicao_pessoas`
Quem come aquele prato, e quanto.

| coluna | tipo | notas |
|---|---|---|
| refeicao_id | fk refeicoes not null | |
| pessoa_id | fk pessoas not null | |
| porcoes | numeric(4,2) | nulo = `porcao_padrao` da pessoa; preenchido = ajuste desta refeição |
| deleted_em | timestamptz | |

Unique parcial em `(refeicao_id, pessoa_id)` para linha viva. **Check:**
`porcoes > 0`.

Nulo como "o padrão" faz uma mudança no perfil valer para todas as
refeições não ajustadas, inclusive as já planejadas. Ao criar uma
refeição sem dizer quem come, entram todas as pessoas vivas, com nulo.

**Porções da refeição** = soma, para cada pessoa, de
`coalesce(porcoes, porcao_padrao)`. **Fator da receita** = porções da
refeição / `rendimento_porcoes`. Cada ingrediente entra na lista com
`quantidade × fator`.

## Copiar uma semana
Cria a semana destino (ou usa a vazia que já existe) e copia as refeições
vivas da origem, com `dia` deslocado pela diferença entre os inícios, com
as `refeicao_pessoas` e os ajustes. Destino com refeição viva: recusa (409),
para não misturar duas semanas. Refeição cuja receita foi apagada é copiada
sem receita, com a observação "receita apagada: <nome>", e volta como
aviso. As sessões de preparo da origem são copiadas pelo mesmo
deslocamento.

---

# Preparo

## `sessoes_preparo`
Quando se cozinha antes. A semana nasce com uma, no **domingo anterior**
(`inicio - 1`); o casal pode mudar o dia (sábado) ou acrescentar outra no
meio da semana (quarta à noite).

| coluna | tipo | notas |
|---|---|---|
| semana_id | fk semanas not null | |
| data | date not null | de `inicio - 2` (sábado anterior) até o domingo da semana |
| rotulo | text | "domingo", "quarta à noite" |
| deleted_em | timestamptz | |

Unique parcial em `(semana_id, data)` para linha viva.

## O roteiro: calculado, não guardado
`GET /semanas/{id}/preparo` monta o roteiro na hora, a partir das
refeições, das receitas e das sessões. Não há tabela de roteiro: tudo o que
ele diz sai do que já está gravado, e guardar uma cópia só criaria o
trabalho de mantê-la igual. Se um dia o casal quiser marcar "feito" em cada
passo, entra uma tabela própria.

Regras, em ordem:

1. **Quem entra.** Refeições com receita e `pode_antecipar = true`. As
   outras vão para a parte "no dia", por dia, com o tempo de preparo.
2. **Sessão de cada refeição.** A sessão mais recente com
   `data <= dia` da refeição (a sessão do próprio dia vale: a janta de
   quarta sai da sessão de quarta). Sem sessão até o dia: vai para "no
   dia".
3. **Agrupamento.** Na sessão, um passo por receita: a soma das porções de
   todas as refeições dela atribuídas à sessão, e o fator total
   ("fazer 1,5 receita: 6 porções"). Cozinha-se uma vez.
4. **Validade.** Para cada refeição do grupo, `dias = dia - data da sessão`.
   - `dias <= dura_dias`: **geladeira**.
   - passou e `pode_congelar`: **congelador**, com "tirar do congelador"
     no dia anterior à refeição.
   - passou e não congela: **aviso** "não dura até <dia>", sugerindo uma
     sessão mais perto ou preparar no dia. A refeição continua no passo
     (o casal decide).
5. **Ordem dos passos na sessão.** Maior `tempo_preparo_min` primeiro (o
   que demora começa antes); empate pelo nome.
6. **Porções por destino.** Cada passo diz quantas porções vão para a
   geladeira e quantas para o congelador, e para que dia é cada uma.

O roteiro não arredonda para receitas inteiras: 1,5 receita é 1,5 receita.
A lista soma os ingredientes pela mesma conta, então os dois batem.

---

# Geração da lista

`POST /semanas/{id}/lista` grava; `GET /semanas/{id}/lista` é a prévia,
com o mesmo cálculo, sem gravar nada. Período da v1: a semana inteira.
**Semana que já passou** (domingo antes de hoje, São Paulo) recusa as duas
(409): vira histórico (D-30).

## `itens_lista_cardapio`
O quanto cada semana pediu de cada item da lista. É o que torna a geração
repetível e o registro da origem "cardápio" num item que já existia.

| coluna | tipo | notas |
|---|---|---|
| item_lista_id | fk itens_lista not null | |
| semana_id | fk semanas not null | |
| quantidade | numeric(12,3) | na `unidade` do item; nula se não converteu |
| unidade | text | |
| gerado_por | text not null | quem pediu a geração (`X-Quem`) |
| deleted_em | timestamptz | |

Unique parcial em `(item_lista_id, semana_id)` para linha viva.

## Regras

1. **Soma.** Para cada refeição viva da semana com receita, cada
   ingrediente vivo: `quantidade × fator`, convertida para a base do
   produto (ver "Unidades"). Soma por produto, na base.
2. **Unidade de compra.** O total por produto vai para a `unidade_padrao`
   (direto, ou dividido pela embalagem e arredondado para cima). Isso é o
   **pedido da semana** para o produto. `a_gosto` e o que não converte
   dão pedido sem quantidade.
3. **Despensa.** A despensa não tem quantidade, então ela não desconta:
   ela classifica.
   - `tem`: o produto **não** vai para a lista. Volta em `confira`:
     "provavelmente já tem, confira", com o pedido da semana. Se o casal
     vir que não tem, marca `acabou` (o ciclo da despensa põe na lista) e
     gera de novo, ou adiciona à mão.
   - `acabando`, `acabou` ou produto não acompanhado: entra na lista.
   - Exceção: se já existe item pendente do produto, ele é ajustado mesmo
     com a despensa em `tem` (já está na lista; o casal já decidiu).
4. **Pendente único (D-25).** Produto que já tem item pendente não ganha
   outro: o item recebe a quantidade do cardápio somada à que tinha, e uma
   linha em `itens_lista_cardapio`. O `origem` do item não muda (quem pôs
   primeiro continua valendo); a origem "cardápio" fica registrada na
   tabela nova e aparece na tela ("e +500 g do cardápio"). Sem item
   pendente: cria um, com `origem = cardapio` e `adicionado_por` = quem
   gerou.
   - Item existente sem quantidade ("o de sempre"): continua sem; a linha
     do cardápio guarda o pedido, e a tela mostra.
   - Item existente numa unidade que não converte para a do pedido: não
     soma; a linha guarda o pedido, e a tela mostra os dois.
5. **Gerar de novo não duplica.** O que entra é a **diferença** entre o
   pedido atual da semana e o que essa semana já pôs, em todos os itens do
   produto (pendentes, comprados ou removidos):
   - diferença zero: nada muda;
   - positiva (pôs mais uma refeição): soma no pendente, ou cria um se não
     houver (o anterior já foi comprado);
   - negativa (tirou uma refeição): subtrai do pendente, no máximo o que
     essa semana pôs nele; se o item era só do cardápio e a quantidade
     chega a zero, sai da lista (soft delete). Comprado não se desfaz.
   - Item que o casal removeu à mão conta como atendido: gerar de novo não
     o traz de volta, a não ser que o pedido aumente.
6. **Concorrência.** A geração trava a linha da semana (`select ... for
   update`) e roda numa transação só, com o ciclo da despensa no mesmo
   service. Os dois apertando "gerar lista" ao mesmo tempo dão o mesmo
   resultado de um só. Os itens chegam aos celulares pelo `/mudancas`,
   como qualquer outro.

**Resposta** (prévia e gravação): `criados`, `ajustados`, `sem_mudanca`,
`confira` (despensa `tem`) e `avisos` (sem conversão, receita apagada),
cada um com produto, pedido da semana e de quais receitas veio.

---

# Nutrientes (futuro)

Sem uso na v1 e sem tabela na v1. Previsto assim, para a subfase de
nutrientes:

## `produto_nutrientes`
Um por produto, **por 100 g** do produto (ou 100 ml, para líquido, com a
nota de que a tabela de referência dá por grama).

| coluna | tipo | notas |
|---|---|---|
| produto_id | fk produtos not null | único entre linhas vivas |
| kcal | numeric(7,2) | |
| proteina_g | numeric(7,2) | |
| carboidrato_g | numeric(7,2) | |
| gordura_g | numeric(7,2) | |
| fibra_g | numeric(7,2) | |
| fonte | text | de onde veio: tabela e versão, ou "rótulo" |
| fonte_codigo | text | o código do alimento na tabela |

Tabela à parte, e não colunas em `produtos`, porque nem todo produto terá
(papel higiênico), e porque a fonte vem junto. A conta da refeição usa a
mesma conversão das unidades: o ingrediente vira gramas pela `medida_base`
(e `medida_por_unidade`); produto em `ml` vai precisar de densidade ou de
aceitar ml = g para líquidos, a decidir ali.

**Candidata a fonte: Tabela TACO** (Tabela Brasileira de Composição de
Alimentos, NEPA/Unicamp), por 100 g de parte comestível, com alimentos
brasileiros crus e preparados. Não escolhida: a decisão fica para a
subfase, quando se souber quantos produtos precisam de valor e se a TACO
cobre os industrializados (que provavelmente pedem o rótulo).

---

# O que não existe aqui, de propósito

- **FK para finanças** (D-25). `pessoas` é do `compras`.
- **Quantidade na despensa.** A despensa continua com três estados; a
  lista só classifica por eles. "Baixar da despensa o que foi comido" é
  subfase própria (roadmap).
- **Roteiro gravado.** É calculado na leitura.
- **Densidade e conversões por produto.** Ver "Unidades".
- **Histórico dos campos da receita** (rendimento, validade). Só os
  ingredientes têm, pelo soft delete.
- **Metas e nutrientes como colunas.** Entram com a subfase que as usa.

---

# Diferenças em relação ao plano (17/11/2026)

A migration `0004_cardapio.py` tem o que está acima, sem tabela nem coluna a
mais. O que a implementação decidiu onde o modelo deixava aberto:

- **Triggers de data.** `refeicoes.dia` dentro da semana e
  `sessoes_preparo.data` de `inicio - 2` a `inicio + 6` são conferidos por
  trigger (`fn_refeicao_dia_na_semana`, `fn_sessao_data_na_semana`), com
  `check_violation` (23514). O service confere antes e responde 422.
- **Nome único** de `pessoas` é `lower(nome)` entre linhas vivas;
  `receitas.id_cliente` é único em qualquer estado, como o de `produtos`.
- **Downgrade.** O Postgres não remove valor de enum: a `0004` recria
  `origem_item` sem `cardapio` (item que veio do cardápio vira `manual`).
- **Unidade do que a semana pôs.** `itens_lista_cardapio.unidade` guarda a
  unidade do **pedido**, e é com ela que se compara na próxima geração e se
  decide se uma subtração mexe na quantidade do item. Item de outra unidade
  (a mão, "3 un" de cebola que o cardápio pede em kg) não é somado; só a
  linha da semana guarda o pedido.
- **A soma é do banco só nas porções.** As porções da refeição
  (`coalesce(porcoes, porcao_padrao)`) são somadas em SQL (`numeric`); a
  conversão de cada ingrediente e o arredondamento da embalagem são em
  Python, com `Decimal`, porque a tabela de unidades mora no código.
  Divisão de fração (1/3 de receita) é arredondada a 6 casas antes do
  "para cima", para um resíduo de 1e-28 não custar uma embalagem.
- **Pedido misto.** Se parte das linhas de um produto converte e parte não
  (2 cebolas e 1 colher de sopa de cebola em pó num produto em `g`), o
  pedido leva a parte que converte e o resto vai para a observação
  ("cardápio: 1 colher_sopa") e para os avisos. `a_gosto` sozinho cria o
  item sem quantidade, com a observação "cardápio: a gosto".
- **Item que o cardápio zera.** Só sai da lista (soft delete) o item de
  `origem = cardapio` cuja quantidade chega a zero (ou, sem quantidade, que
  não tem mais linha de nenhuma semana). Item de outra origem que chegaria a
  zero fica sem quantidade ("o de sempre"). A linha da semana em
  `itens_lista_cardapio` leva soft delete quando zera.
- **`tem` depois de comprar.** Produto acompanhado na despensa volta a `tem`
  ao ser comprado. Se o pedido da semana aumentar depois, e não houver
  pendente, ele aparece em `confira`, não como item novo: a regra da
  despensa vale antes da diferença.
- **Cópia de semana.** Destino novo nasce sem a sessão padrão (leva as da
  origem, deslocadas); destino vazio que já existe mantém as suas e só
  recebe as sessões de datas livres. A observação da refeição de receita
  apagada é "receita apagada: <nome>", seguida de "; <observação original>"
  se havia.
- **Refeição nova** entra no fim da ordem do mesmo dia e tipo
  (`ordem = max + 1`).
- **Apagar pessoa** apaga também as linhas dela em `refeicao_pessoas` das
  refeições de hoje em diante (as passadas mantêm); apagar semana apaga as
  refeições, as linhas de pessoas e as sessões dela.
- **Hoje e a semana passada.** `compras/tempo.py`: `hoje()` em São Paulo é
  a única fonte da data (trocável nos testes); `passou(inicio)` é
  `inicio + 6 < hoje()`.
- **Carga inicial.** `python -m compras.carga_cardapio` (`make
  compras-carga-cardapio`): Erik (1,5) e Laura (1,0), 25 produtos com
  medidas e 15 receitas de 1 porção, estimadas. Não há coluna "revisar": a
  marca `[REVISAR QUANTIDADES] Quantidades estimadas pela carga inicial.` é
  a primeira linha do `modo_preparo`. Os ovos usam o "Ovos 12 un" do seed,
  com `medida_base = un` e `medida_por_unidade = 12` (a unidade de compra é a
  caixa).
