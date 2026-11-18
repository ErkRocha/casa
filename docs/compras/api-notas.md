# API — notas fiscais, conferência e preços (D-33)

**Plano, não implementado.** Amplia a seção "Nota fiscal e preços" de
`api.md`, que continua valendo onde este documento não diz o contrário.
Modelo em `modelo-notas.md`. Convenções de `api.md`: caminhos sem o prefixo
`/api/compras`, toda escrita exige `X-Quem`, dinheiro e quantidade como
texto decimal, resposta de escrita traz a linha inteira, o que a leitura
grava sozinha vai para a auditoria com o autor `leitura_nfce`.

O fluxo da D-33 e o endpoint de cada passo:

| passo | endpoint |
|---|---|
| ler a nota | `POST /notas` [existe] |
| ligar à despesa | `GET /notas/{id}/sugestoes-transacao` [muda], `PUT /notas/{id}/transacao` [existe] |
| reconhecer os itens | `PUT /notas/{id}/itens/{item_id}/variante` [novo] |
| conferir a lista | `GET` (prévia) e `POST` (confirmação) `/notas/{id}/conferencia` [novo] |
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
| GET | `/notas/{id}/sugestoes-transacao` | **Muda:** hoje é o mesmo dia e o mesmo valor. Passa a procurar de um dia antes a um dia depois da emissão (a data da Pluggy varia, D-23) e o valor exato; ordena pelo dia mais próximo. Continua só sugestão |
| PUT | `/notas/{id}/transacao` | Como hoje: `{"transacao_id": 123}` confirma, nulo desfaz |

A compra do cartão lida no mesmo dia quase sempre está **pendente na
Pluggy** (D-28) e não existe em `transacoes` ainda: não há o que sugerir. A
nota fica na fila "sem despesa" (`GET /notas?com_transacao=false`) e a
sugestão aparece quando a sync promover a compra. Ligar a uma pendente não é
possível nem desejável: ela não tem id estável em finanças.

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

**Associação automática** na leitura, na ordem: GTIN da variante > apelido
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
  "extras":      [{"linha": 9, "produto": "Chocolate", "variante": "Chocolate Garoto 90g"}],
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

## Comprado, aguardando nota

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/lista` | **Muda:** os comprados com `fechamento` nulo vêm em `aguardando_nota`, separados dos comprados recentes, e os que passaram de 7 dias sem `perguntado_em` vêm em `perguntas` |
| POST | `/lista/itens/{id}/fechar` | `{"como": "sem_nota" \| "nao_comprei"}`. Pode ser chamado a qualquer momento, antes dos 7 dias. `nao_comprei` volta a pendente (ou remove, se já há outro pendente do produto) e leva a despensa para `acabou`. Item já fechado: 409 |
| POST | `/lista/itens/{id}/dispensar-pergunta` | Grava `perguntado_em` sem fechar: a pergunta não aparece de novo e o item continua aguardando nota |
| POST | `/lista/itens/{id}/desfazer` | Existe. Item fechado por nota: 409 (a nota é a fonte da verdade) |

As mudanças de `fechamento` chegam ao outro celular pelo `/mudancas`, como
qualquer mudança em `itens_lista`.

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

"Onde é mais barato" compara o último preço de cada mercado, não a média: o
que importa é o preço de agora. A resposta traz a data de cada um, para a
tela dizer "há 40 dias" quando for velho.

## Voz (futuro, sem detalhe)

Uma ferramenta do MCP do vault, cliente de `GET /precos/onde-mais-barato`:
"onde o leite está mais barato?". Registrada como direção na D-33; desenho e
nome da ferramenta ficam para quando os preços tiverem notas reais.

## Casos que a fase precisa cobrir nos testes

- **Variante:** dois itens com o mesmo GTIN em mercados diferentes caem na
  mesma variante; um item pesado em KG dá R$/kg; um leite de 1 L e um de
  200 ml do mesmo produto se comparam por R$/L; variante sem medida não
  entra no comparável e aparece na contagem.
- **Preço:** desconto de linha e desconto da nota inteira rateado; a soma
  dos preços pagos bate com o total da nota, centavo a centavo.
- **Conferência:** os seis casos da D-33 (marcado e na nota; não marcado e
  na nota; extra; pendente fora da nota; marcado fora da nota; quantidade
  menor com "volta" e sem); prévia e confirmação com o mesmo resultado;
  confirmar duas vezes não muda nada.
- **Aguardando nota:** confirmado por uma nota de outro estabelecimento
  dias depois; não confirmado por nota emitida antes da marcação; a pergunta
  aparece só aos 7 dias e só uma vez; "não comprei" com e sem outro pendente
  do produto.
- **Despensa:** produto não acompanhado passa a ter linha em `tem`; nota
  lida com atraso não desfaz um "acabou" posterior.
- **Despesa:** sugestão um dia antes e um dia depois; nota sem sugestão fica
  na fila e não bloqueia a conferência.
