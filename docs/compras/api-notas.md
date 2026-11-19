# API — notas fiscais, conferência e preços (D-33)

**Implementado: variantes, preços, ligação à despesa, conferência da lista e
"aguardando nota"** (seções "Reconhecer os itens (variantes)", "Preços",
"Ligação à despesa", "Conferência" e "Comprado, aguardando nota", com os
ajustes anotados nelas). Amplia a seção "Nota fiscal e preços" de
`api.md`, que continua valendo onde este documento não diz o contrário.
Modelo em `modelo-notas.md`. Convenções de `api.md`: caminhos sem o prefixo
`/api/compras`, toda escrita exige `X-Quem`, dinheiro e quantidade como
texto decimal, resposta de escrita traz a linha inteira, o que a leitura
grava sozinha vai para a auditoria com o autor `leitura_nfce`.

O fluxo da D-33 e o endpoint de cada passo:

| passo | endpoint |
|---|---|
| ler a nota | `POST /notas` [existe; ganhou `proximos`] |
| ligar à despesa | `GET /notas/{id}/sugestoes-transacao` [muda], `PUT /notas/{id}/transacao` [existe], `POST /notas/{id}/lancar-despesa` [novo] |
| reconhecer os itens | `PUT /notas/{id}/itens/{item_id}/variante` [novo] |
| conferir a lista | `GET` (prévia) e `POST` (confirmação) `/notas/{id}/conferencia` [implementado] |
| atualizar a despensa | na confirmação da conferência |
| registrar os preços | nada a chamar: a view lê as notas conferidas ou não |

Os passos não se bloqueiam: dá para conferir a lista sem ter ligado a
despesa (a compra do cartão pode ainda não ter chegado da Pluggy) e ligar a
despesa dias depois.

## Leitura

| Método | Caminho | O que faz |
|---|---|---|
| POST | `/notas` | Como hoje. A resposta ganha `proximos`: `{"ligar_despesa": bool, "itens_sem_variante": n, "conferencia": "pendente" \| "sem_lista" \| "feita"}`, para a tela saber o que oferecer |
| GET | `/notas?conferida=&com_transacao=&limite=&offset=` | Paginada com total. Os filtros servem às filas "notas sem despesa" e "notas sem conferência" |
| GET | `/notas/{id}` | Como hoje, e cada item traz a variante, o preço cheio, o desconto (linha e rateado), o preço pago e o preço comparável (`"por": "kg" \| "l" \| "un"`) |

## Ligação à despesa

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/notas/{id}/sugestoes-transacao` | **Muda:** hoje é o mesmo dia e o mesmo valor. Passa a procurar de um dia antes a um dia depois da emissão (a data da Pluggy varia, D-23), com o valor exato, **nas transações e nas compras pendentes do cartão** (D-28). Cada sugestão diz o tipo, `{"tipo": "transacao", "transacao_id": 123}` ou `{"tipo": "pendente", "id_externo": "..."}`, com data, valor, descrição e cartão; ordena pelo dia mais próximo. Continua só sugestão |
| PUT | `/notas/{id}/transacao` | **Muda:** `{"transacao_id": 123}` ou `{"pendente_id_externo": "..."}` confirma (um dos dois); nulo nos dois desfaz. A transação ou a pendente precisa existir em finanças |
| POST | `/notas/consolidar-ligacoes` | Idempotente. Para cada nota ligada a uma pendente, pergunta a finanças se já há transação com aquele id: se há, preenche `transacao_id` sozinho; pendente sumida sem transação desfaz a ligação (a nota volta à fila). Para cada nota ligada a uma transação apagada com `substituida_por_id` (a lançada pela nota que a revisão juntou com a do banco), passa a ligação para a substituta. Chamado pela tela de notas ao abrir e, sem bloquear nada, pelo agendador de finanças depois da sync diária |
| GET | `/notas/{id}/lancar-despesa` | **Novo.** A prévia do lançamento: valor e data da nota, o mercado, a forma da página (`forma_pagamento_nota`), a categoria sugerida pelos itens e as formas de pagamento de finanças para escolher. Nota já ligada: 409 |
| POST | `/notas/{id}/lancar-despesa` | **Novo.** `{"data", "valor", "descricao", "pessoa_id", "forma_pagamento_id", "categoria_id"}`, tudo escolhido ou confirmado pelo usuário. Cria a transação em finanças pelo `POST /api/transacoes` com `lancada_pela_nota = true`, liga a nota a ela e grava `despesa_lancada_pela_nota`. Nota já ligada: 409. Finanças fora do ar: 503, nada gravado |

**Ligar não é obrigatório.** A nota sem ligação fica na fila "sem despesa"
(`GET /notas?com_transacao=false`) e não bloqueia a conferência nem os
preços. A compra do cartão lida no mesmo dia quase sempre ainda é
pendente: ela aparece na sugestão, e a ligação vira ligação com a transação
quando a compra consolidar (`modelo-notas.md`, "Ligação com a pendente").

**Sugestão e forma de pagamento.** A página traz a forma ("Cartão de
Crédito", "Pix"); a sugestão põe primeiro as candidatas do mesmo tipo de
forma e depois ordena pelo dia mais próximo. Não filtra.

**Nota sem despesa que não vai chegar** (cartão fora da Pluggy):
"lançar despesa pela nota" cria a transação com o que o usuário escolher
(`modelo-notas.md`, "Nota sem despesa"). A forma de pagamento, como "Cartão
da Laura", precisa estar cadastrada em Contas e cartões; a ação não cria
forma.

**Do lado de finanças**, dois endpoints de leitura novos, sem schema novo (a
API de finanças é a dona desses dados, D-25): as compras pendentes do cartão
por data e valor, e a transação pelo id da Pluggy (pelo item de staging que
a promoveu). Para o lançamento pela nota, finanças ganha uma migration:
`transacoes.lancada_pela_nota` e `transacoes.substituida_por_id`. O
`POST /api/transacoes` aceita a marca, a leitura de uma transação apagada
devolve o `substituida_por_id`, e a sync põe na revisão, como possível
duplicata, o item da Pluggy com a mesma data, valor e forma de uma transação
lançada pela nota. "Juntar" na revisão de duplicata mantém a do banco.

**Como ficou (ligação à despesa).**

- `GET /notas/{id}/sugestoes-transacao` devolve uma lista de `{tipo,
  transacao_id | id_externo, data, valor, descricao, cartao, forma_tipo,
  forma_combina, lancada_pela_nota}`. Mapa da forma da página para o tipo de
  forma de finanças: Cartão de Crédito -> `credito`, Cartão de Débito ->
  `debito`, Pix -> `pix`, Dinheiro -> `dinheiro`; qualquer outra, sem
  preferência. A ordem é `forma_combina` primeiro, depois a distância em
  dias, transações antes de pendentes no empate.
- `PUT /notas/{id}/transacao` aceita `{"transacao_id": n}` ou
  `{"pendente_id_externo": "..."}`; os dois juntos: 422; os dois nulos (ou
  corpo vazio) desfazem. Trocar de uma para a outra limpa a anterior e
  `despesa_lancada_pela_nota`. O que se liga precisa existir em finanças (422).
- `POST /notas/consolidar-ligacoes` não exige `X-Quem` (quem chama é a
  finanças, depois da sync, ou a tela) e grava com o autor `leitura_nfce`.
  Resposta: `{"verificadas", "consolidadas", "desfeitas", "movidas"}`.
  Finanças fora do ar: 502, nada muda. A finanças o chama em
  `COMPRAS_API_URL` (no compose, `http://compras:8000`, sem o prefixo do
  nginx), com 5 s de limite, e só registra em log se falhar.
- `GET /notas/{id}/lancar-despesa` devolve `{valor, data, descricao,
  forma_pagamento_nota, forma_pagamento_id_sugerida, categoria_id_sugerida,
  categoria_origem ("itens" | "ultima_do_mercado" | null),
  formas_pagamento}`. `POST` devolve a nota. Finanças fora do ar: 503 (nos
  dois), nada gravado; finanças recusar o lançamento (forma inexistente,
  duplicata): 422. A categoria enviada precisa ser de despesa (422).
- `PATCH /secoes/{id}` aceita `categoria_id_financas` (nulo limpa), conferida
  em `GET /categorias/{id}` de finanças (precisa ser de despesa e ativa).
- Finanças ganhou, para isto: `GET /transacoes/candidatas-nota`, `GET
  /transacoes/pendentes-cartao` (e `/{id_externo}`), `GET
  /transacoes/por-pluggy/{id_externo}` e `GET /transacoes/{id}/situacao` (a
  transação apagada continua legível, com `substituida_por_id`). Na revisão,
  `GET /revisar/duplicatas` traz `lancadas_pela_nota` por grupo e `POST
  /revisar/duplicatas/resolver` aceita `juntar_lancada_pela_nota_id`.

## Reconhecer os itens (variantes)

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/variantes?produto_id=&gtin=&busca=&sem_medida=&limite=` | Busca para associar; `sem_medida=true` é a fila de variantes sem `conteudo` |
| POST | `/variantes` | `{produto_id, nome, marca?, gtin?, medida_base?, conteudo?, pesada?}`. GTIN repetido: 409 com a variante que já tem |
| PATCH | `/variantes/{id}` | Nome, marca, medida, `pesada`, e trocar de produto (os itens e apelidos vão juntos) |
| DELETE | `/variantes/{id}` | Soft delete; recusa (409) se há item de nota ligado |
| PUT | `/notas/{id}/itens/{item_id}/variante` | `{"variante_id": 9}` ou `{"produto_id": 7, "nova": {nome?, medida_base?, conteudo?, pesada?}}` (cria a variante com o nome da nota por padrão e o GTIN do item). Grava o apelido do texto no mercado da nota (D-09). Se a nota já foi conferida, aplica a despensa a este item e o casa com um "aguardando nota" do mesmo produto, se houver |
| PUT | `/notas/{id}/itens/{item_id}/produto` | **Existe**, fica por compatibilidade: equivale ao anterior com `{"produto_id": ..., "nova": {}}` |
| GET | `/notas/itens-sem-produto` | Existe; vira "sem variante" (os dois coincidem depois da migração) |

**Como ficou:** `GET /variantes` busca (`busca`) pelo nome da variante, do
produto ou do mercado onde ela tem código, e aceita `offset`; há também
`GET /variantes/{id}`. `POST /variantes/{id}/juntar` recebe `{"outra_id": n}`
(fica a da URL; produtos ou GTINs diferentes: 422). O `PUT .../variante`
devolve o item com `sugestao_medida` (lida na descrição, só vale depois do
`PATCH /variantes/{id}`), `variante_id`, preço cheio, desconto rateado, preço
pago, `preco_pago_estimado` e `comparavel` (`{"valor", "por"}`); `GET
/notas/{id}` traz os mesmos campos em cada item. `PUT
/notas/{id}/itens/{item_id}/produto` continua.

**Associação automática** na leitura, na ordem: GTIN da variante > `(mercado,
código)` da variante > apelido
do texto no mesmo mercado > apelido sem mercado > apelido de outro mercado,
só se todos concordam. O leitor pode sugerir medida e "pesada" pela
descrição e pela unidade (`KG`), mas só grava ao criar uma variante nova.

## Conferência

O padrão é o da lista do cardápio (`api-cardapio.md`): uma **prévia** que
não grava, e a **confirmação** com as respostas às perguntas, aplicada numa
transação, com o mesmo plano da prévia.

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/notas/{id}/conferencia` | **Prévia.** Só nota lida. Usa os pendentes e os comprados aguardando nota (`modelo-notas.md`, "O marco da conferência") |
| POST | `/notas/{id}/conferencia` | **Confirmação.** Corpo: `{"diferencas": [{"item_lista_id": 41, "volta": true}]}`, uma resposta por pergunta de quantidade. Pergunta sem resposta: 422 com a lista do que falta. Grava `item_lista_id` nas linhas, fecha os itens, cria os pendentes da diferença, atualiza a despensa e marca `conferida_em` |

Resposta das duas, igual:

```json
{
  "confirmados": [{"item_lista_id": 41, "produto": "Leite", "linhas": [3],
                   "estava": "aguardando_nota"}],
  "marcados":    [{"item_lista_id": 52, "produto": "Pão", "linhas": [7],
                   "aviso": "não estava marcado; marcado como comprado pela nota"}],
  "extras":      [{"linha": 9, "produto": "Chocolate", "variante": "Chocolate Garoto 90g",
                   "acompanhado": false, "acao": "acompanhar_na_despensa"}],
  "continuam_pendentes": [{"item_lista_id": 60, "produto": "Café"}],
  "aguardando_nota":     [{"item_lista_id": 33, "produto": "Detergente",
                           "comprado_em": "2026-11-15T10:12:00-03:00", "dias": 3}],
  "diferencas":  [{"item_lista_id": 44, "produto": "Banana", "pedido": "6", "veio": "4",
                   "unidade": "un", "pergunta": "Os 2 un que faltaram voltam para a lista?"}],
  "nao_reconhecidos": [{"linha": 11, "descricao_original": "BISC REC CHOC 120G"}],
  "despensa":    [{"produto": "Leite", "antes": "acabou", "depois": "tem"}]
}
```

- **Sem lista que bata** (farmácia, posto): a prévia vem só com `extras`,
  `nao_reconhecidos` e `despensa`, e `"conferencia": "sem_lista"`. A
  confirmação continua existindo, porque a despensa e a marca de nota
  conferida precisam de uma escrita; a tela pode fazê-la sem mostrar a
  conferência.
- **Não reconhecidos** não bloqueiam a confirmação: as linhas ficam na fila
  de associar e fora da lista e da despensa até alguém associar (que então
  aplica o efeito, ver `PUT .../variante`). A tela pergunta uma vez, antes da
  confirmação, pelo `PUT .../variante`.
- **Confirmar de novo** a mesma nota: 200 sem mudança, com a resposta do que
  foi aplicado. Uma conferência não se desfaz em bloco; cada item se corrige
  na lista.
- **Concorrência**: a confirmação trava os itens da lista envolvidos
  (`FOR UPDATE`). Se um deles mudou depois da prévia (alguém marcou ou
  removeu), a confirmação refaz o plano e aplica o atual; a resposta mostra
  o que de fato foi feito.

**Como ficou (conferência).**

- `GET /notas` ficou paginada: `{items, total, limite, offset}`, com os
  filtros `conferida` e `com_transacao` (ligada à compra pendente do cartão
  conta como ligada). `POST /notas` e `POST /notas/{id}/reler` trazem
  `proximos`; `GET /notas/{id}` não (`null`). Nota com `status = erro`:
  `proximos.conferencia = "sem_lista"`. `NotaResumo` ganhou `conferida_em` e
  `conferida_por`.
- A resposta da conferência traz também `nota_id` e `conferencia`
  (`pendente` na prévia, `sem_lista` quando nada da lista bate, `feita` na
  confirmação e em toda nota já conferida). `extras` e `despensa` trazem o
  `produto_id` (a ação "acompanhar na despensa" é o `PUT /despensa/{produto_id}`
  com `tem`). `pedido` e `veio` vão sem zeros à direita ("6", "0.512").
  Em `diferencas`, `volta` é nulo na prévia e traz a resposta na confirmação:
  é a única diferença entre as duas respostas.
- Pergunta sem resposta: 422 com `faltam: [{item_lista_id, produto}]`, nada
  gravado. Resposta a um item que não é pergunta é ignorada. O corpo da
  confirmação pode ser vazio quando não há pergunta.
- Nota que não está `lida`: 409. Nota já conferida (prévia ou confirmação):
  200 com `conferencia = "feita"`, reconstruída do que ficou gravado
  (`confirmados`, `marcados`, `extras`, `nao_reconhecidos`); as listas
  `continuam_pendentes`, `aguardando_nota`, `diferencas` e `despensa` vêm
  vazias, porque o que mudou naquele momento não fica guardado.
- Por produto, a nota atende **um** item: o comprado aguardando nota mais
  antigo que a regra da data deixa casar, senão o pendente. Todas as linhas
  do produto levam o mesmo `item_lista_id`. O fechamento por nota grava
  `fechado_por = leitura_nfce`; o pendente marcado pela nota grava
  `comprado_por` com quem confirmou e `comprado_em = emitida_em`.
- Despensa pela nota: o produto acompanhado vai para `tem` se `emitida_em` é
  depois do `estado_em` (o produto não acompanhado nunca ganha linha, venha
  da lista ou seja extra). "Volta" soma ao pendente do produto só se ele tem
  quantidade na mesma unidade; sem quantidade, fica como está.
- `PUT /notas/{id}/itens/{item_id}/variante` numa nota já conferida, na
  primeira associação da linha: a casa com o aguardando nota do mesmo
  produto (se a regra da data deixar) e aplica a despensa.

## Comprado, aguardando nota

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/lista` | **Muda:** os comprados com `fechamento` nulo vêm em `aguardando_nota`, separados dos comprados recentes, e os que passaram de 7 dias sem `perguntado_em` vêm em `perguntas` |
| POST | `/lista/itens/{id}/fechar` | `{"como": "sem_nota" \| "nao_comprei"}`. Pode ser chamado a qualquer momento, antes dos 7 dias. `nao_comprei` volta a pendente (ou remove, se já há outro pendente do produto) e leva a despensa para `acabou`. Item já fechado: 409 |
| POST | `/lista/itens/{id}/dispensar-pergunta` | Grava `perguntado_em` sem fechar: a pergunta não aparece de novo e o item continua aguardando nota |
| POST | `/lista/itens/{id}/desfazer` | Existe. Item fechado por nota: 409 (a nota é a fonte da verdade) |

As mudanças de `fechamento` chegam ao outro celular pelo `/mudancas`, como
qualquer mudança em `itens_lista`.

**Como ficou (aguardando nota).**

- `GET /lista` ganhou `aguardando_nota` (todo comprado com `fechamento` nulo,
  o mais antigo primeiro) e `perguntas` (os desses comprados há mais de 7
  dias, `COMPRAS_PERGUNTA_NOTA_DIAS`, e sem `perguntado_em`). `itens` não mudou:
  o comprado recente aparece nos dois, e a tela separa pelo id. Cada item
  (em `/lista`, `/mudancas` e nas respostas de escrita) traz `fechamento`,
  `fechado_em`, `fechado_por` e `perguntado_em`.
- `POST /lista/itens/{id}/fechar` com `sem_nota` grava `fechado_por` com quem
  respondeu. `nao_comprei` limpa também `perguntado_em` (uma compra nova
  pergunta de novo). Item pendente, apagado ou já fechado: 409 com o item.
- `POST /lista/itens/{id}/dispensar-pergunta` é idempotente (vale a primeira
  data); item fechado: 409.
- `desfazer` recusa (409) só o item fechado por `nota`; o `sem_nota`
  (inclusive os migrados) continua se desfazendo, e o desfazer limpa
  `perguntado_em`.

## Preços

Toda consulta de preço sai de `vw_preco_variante` (`modelo-notas.md`). Preço
comparável sempre com a unidade (`"por": "kg"`); linhas sem medida aparecem
com `comparavel: null` e uma contagem à parte, nunca misturadas.

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/precos/variantes/{id}?limite=&offset=` | Histórico da variante: cada compra com data, mercado, quantidade, preço cheio, desconto, preço pago e comparável. Paginado |
| GET | `/precos/produtos/{id}?desde=` | Agregado do produto: por variante e por mercado, último comparável e a data, mínimo, máximo e média; a variante mais barata pelo comparável |
| GET | `/precos/mercados/{id}?desde=&limite=&offset=` | O que se comprou naquele mercado: por produto, o último comparável e como ele se compara à média dos outros mercados |
| GET | `/precos/onde-mais-barato?produto_id=&dias=90` | Ranking dos mercados pelo **último** comparável do produto em cada um, dentro da janela; `dias` padrão 90. Também aceita `busca=leite` no lugar do id, que é o que a voz vai usar |
| GET | `/precos?produto_id=&mercado_id=` | Existe (`vw_preco_produto`); passa a agregar pela medida da variante. Fica até as telas usarem os novos |

**Como ficou:** `GET /precos` devolve `medida_base`, `por`,
`ultimo_comparavel`, `ultima_variante_id` e `sem_comparavel` (no lugar de
`unidade` e `ultimo_preco`). `onde-mais-barato` devolve `ranking` por unidade
(`por`), com `posicao`, `data` e `dias_atras`; `busca` é o nome sem caixa nem
acento (o nome inteiro, ou o único produto que o contém); mais de um: 409 com
`candidatos`. `/precos/produtos/{id}` traz `por_variante`, `por_mercado`,
`mais_barata` (uma por unidade) e `sem_comparavel`.

"Onde é mais barato" compara o último preço de cada mercado, não a média: o
que importa é o preço de agora. A resposta traz a data de cada um, para a
tela dizer "há 40 dias" quando for velho.

## Voz (futuro, sem detalhe)

Uma ferramenta do MCP do vault, cliente de `GET /precos/onde-mais-barato`:
"onde o leite está mais barato?". Registrada como direção na D-33; desenho e
nome da ferramenta ficam para quando os preços tiverem notas reais.

## Casos que a fase precisa cobrir nos testes

- **Variante:** dois itens com o mesmo GTIN em mercados diferentes caem na
  mesma variante; dois itens com o mesmo código interno no mesmo mercado
  caem na mesma variante, e o mesmo código em outro mercado não; "juntar
  variantes" leva códigos, apelidos e itens; a sugestão de medida lê
  "450G" e "1,5L" e não sugere nada com dois tamanhos na descrição; um item pesado em KG dá R$/kg; um leite de 1 L e um de
  200 ml do mesmo produto se comparam por R$/L; variante sem medida não
  entra no comparável e aparece na contagem.
- **Preço:** desconto de linha e desconto da nota inteira rateado; a soma
  dos preços pagos bate com o total da nota, centavo a centavo; item que
  recebeu desconto rateado vem com `preco_pago_estimado`.
- **Conferência:** os seis casos da D-33 (marcado e na nota; não marcado e
  na nota; extra; pendente fora da nota; marcado fora da nota; quantidade
  menor com "volta" e sem); prévia e confirmação com o mesmo resultado;
  confirmar duas vezes não muda nada.
- **Aguardando nota:** confirmado por uma nota de outro estabelecimento
  dias depois; não confirmado por nota emitida antes da marcação; a pergunta
  aparece só aos 7 dias e só uma vez; "não comprei" com e sem outro pendente
  do produto.
- **Despensa:** produto acompanhado vai para `tem`; produto da lista vai
  como ao marcar comprado; extra não acompanhado não ganha linha e vem com
  "acompanhar na despensa"; nota lida com atraso não desfaz um "acabou"
  posterior.
- **Despesa:** sugestão um dia antes e um dia depois, nas transações e nas
  pendentes; nota ligada a uma pendente passa para a transação sozinha
  quando ela consolida, sem nova pergunta; pendente cancelada devolve a nota
  à fila; nota sem ligação não bloqueia a conferência; a forma da nota
  ordena a sugestão; "lançar despesa pela nota" cria a transação marcada e
  liga; o item da Pluggy igual em data, valor e forma vai para a revisão e
  não é promovido; juntar mantém a do banco e a nota passa para ela pelo
  `consolidar-ligacoes`.
