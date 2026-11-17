# API — `compras`, módulo de cardápio (D-30)

**Planejado, não implementado.** Mesmo serviço, mesmo endereço
(`/api/compras/...`) e mesmas convenções de `api.md`: `X-Quem` em toda
escrita (substituído pela identidade do Tailscale quando há), `id_cliente`
no `POST` que cria receita, resposta de escrita com a linha inteira,
quantidade como texto decimal, a última escrita vence. Modelo em
`modelo-cardapio.md`.

Listas paginadas (regra do `CLAUDE.md`): receitas e semanas, com
`limite`/`offset` e `total`. Pessoas, refeições de uma semana e roteiro
são pequenos e vêm inteiros.

O cardápio não entra no `/mudancas`: é planejado com calma, não com os dois
no mercado. A tela busca de novo ao abrir e depois de cada escrita. O que a
geração da lista cria ou ajusta em `itens_lista` chega aos celulares pelo
`/mudancas` de sempre.

## Pessoas

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/pessoas` | As vivas, com `porcao_padrao` e a identidade ligada (`login`, quando há) |
| POST | `/pessoas` | `{nome, porcao_padrao?, identidade_id?}`. Nome repetido: 409 |
| PATCH | `/pessoas/{id}` | Nome, `porcao_padrao`, `identidade_id` |
| DELETE | `/pessoas/{id}` | Soft delete. Some das refeições a partir de hoje; as passadas mantêm a linha |

## Produtos (o que muda no endpoint que existe)

| Método | Caminho | O que faz |
|---|---|---|
| PATCH | `/produtos/{id}` | Aceita também `medida_base` (`g`, `ml`, `un` ou nulo) e `medida_por_unidade`. `medida_por_unidade` sem `medida_base`: 422 |
| GET | `/produtos/sem-medida?usados_em_receita=true` | Produtos de ingrediente sem o que a conversão precisa: a fila de "cadastre a medida" |

## Receitas

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/receitas?busca=&tipo=&pode_antecipar=&limite=20&offset=0` | Busca no `nome_normalizado` (contém; quem começa com o texto vem antes), com `total` |
| GET | `/receitas/{id}` | A receita com os ingredientes na ordem, o nome do produto e se cada um converte |
| POST | `/receitas` | `{id_cliente, nome, tipo, rendimento_porcoes, tempo_preparo_min?, modo_preparo?, pode_antecipar, dura_dias?, pode_congelar, ingredientes: [{produto_id ou produto_nome, quantidade?, unidade, observacao?}]}`. Ingrediente com `produto_nome` sem produto cria o produto em "Sem seção", na mesma transação. `id_cliente` repetido: 200 com a que existe |
| PUT | `/receitas/{id}` | Mesmo corpo, sem `id_cliente`: substitui os campos e a lista de ingredientes numa transação. Todo ingrediente antigo leva soft delete e o novo é criado (nunca UPDATE no lugar), para a semana passada continuar lendo os seus (D-30). Aqui é `PUT` porque a receita é editada como um formulário inteiro, não por ação |
| POST | `/receitas/{id}/duplicar` | Cópia com o nome "<nome> (cópia)", para variar uma receita |
| DELETE | `/receitas/{id}` | Soft delete. Usada em semana que ainda não acabou: 409, com as semanas |

## Semanas e refeições

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/semanas?limite=10&offset=0` | As semanas, mais recentes primeiro, com quantas refeições cada uma tem |
| GET | `/semanas/{inicio}` | A semana pela segunda-feira (`2026-11-23`), com as refeições por dia e tipo, quem come cada prato e a porção **efetiva** de cada um (`porcoes`, `ajustada: true/false`), e as sessões de preparo. Semana que não existe: 404 com `{"existe": false}`, para a tela oferecer criar ou copiar. Data que não é segunda: 422 |
| POST | `/semanas` | `{inicio}`. Cria com a sessão de preparo do domingo anterior. Já existe: 200 com ela |
| POST | `/semanas/{id}/copiar` | `{destino}` (segunda-feira). Copia refeições, pessoas, ajustes e sessões, deslocando as datas. Cria a semana destino se precisar. Destino com refeição: 409. 201 com a semana nova e os `avisos` (receitas apagadas) |
| DELETE | `/semanas/{id}` | Soft delete da semana e das refeições. Os itens que ela pôs na lista ficam (já são da lista) |
| POST | `/semanas/{id}/refeicoes` | `{dia, tipo, receita_id?, observacao?, pessoas?: [{pessoa_id, porcoes?}]}`. Sem `pessoas`: todas as vivas, com a porção padrão |
| PATCH | `/refeicoes/{id}` | Dia (dentro da semana), tipo, receita, observação, ordem |
| PUT | `/refeicoes/{id}/pessoas` | `[{pessoa_id, porcoes?}]`: quem come e quanto. `porcoes` nulo volta ao padrão do perfil |
| DELETE | `/refeicoes/{id}` | Soft delete |

## Preparo

| Método | Caminho | O que faz |
|---|---|---|
| POST | `/semanas/{id}/sessoes` | `{data, rotulo?}` (de sábado anterior a domingo da semana) |
| PATCH | `/sessoes/{id}` | Data, rótulo |
| DELETE | `/sessoes/{id}` | Soft delete; as refeições dela vão para a sessão anterior ou para "no dia" |
| GET | `/semanas/{id}/preparo` | O roteiro, calculado na hora (regras em `modelo-cardapio.md`, "Preparo") |

```json
{
  "sessoes": [
    {
      "data": "2026-11-22", "rotulo": "domingo",
      "passos": [
        {
          "receita": {"id": 4, "nome": "Frango assado", "tempo_preparo_min": 90},
          "porcoes": "6.00", "fator": "1.500",
          "destinos": [
            {"refeicao_id": 31, "dia": "2026-11-23", "tipo": "almoco", "porcoes": "2.00", "onde": "geladeira"},
            {"refeicao_id": 40, "dia": "2026-11-27", "tipo": "janta", "porcoes": "2.00", "onde": "congelador", "descongelar_em": "2026-11-26"}
          ],
          "avisos": []
        }
      ]
    }
  ],
  "no_dia": [
    {"dia": "2026-11-24", "tipo": "janta", "receita": {"id": 9, "nome": "Omelete", "tempo_preparo_min": 10}}
  ],
  "avisos": [
    {"refeicao_id": 44, "texto": "Salada de folhas não dura até sábado (dura 2 dias) e não congela"}
  ]
}
```

## Lista de compras pelo cardápio

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/semanas/{id}/lista` | **Prévia**: o que a geração faria, sem gravar nada. Semana que já passou: 409 (D-30), nas duas |
| POST | `/semanas/{id}/lista` | Gera ou atualiza: grava os itens e a `itens_lista_cardapio`, numa transação com a semana travada. Repetir sem mudar o cardápio não muda nada (todos em `sem_mudanca`) |

Mesma resposta nos dois:

```json
{
  "criados":    [{"produto": "Cebola", "item_id": 88, "quantidade": "0.450", "unidade": "kg",
                  "de": ["Frango assado", "Arroz"]}],
  "ajustados":  [{"produto": "Leite integral 1L", "item_id": 51, "antes": "1.000", "depois": "3.000",
                  "unidade": "un", "origem_item": "manual"}],
  "sem_mudanca": [],
  "confira":    [{"produto": "Arroz 5kg", "estado_despensa": "tem", "pedido": "0.300", "unidade": "un",
                  "texto": "provavelmente já tem, confira"}],
  "avisos":     [{"produto": "Farinha de trigo 1kg", "texto": "cadastre a medida: 2 colher_sopa não converte para g"}]
}
```

`pedido` é o que a semana pede daquele produto, já na unidade de compra.
Itens criados aparecem na lista com "do cardápio"; ajustados, com o
acréscimo ("e +2 un do cardápio").

## Casos que a fase precisa cobrir nos testes

- **Conversão**: os quatro casos de `modelo-cardapio.md` ("Unidades"), o
  arredondamento para cima da embalagem e o item sem quantidade quando não
  converte.
- **Porções**: duas pessoas com 1 e 1,5, receita que rende 4: fator 0,625;
  um ajuste numa refeição muda só ela; mudar o perfil muda as não
  ajustadas.
- **Despensa**: `tem` vai para `confira` e não cria item; `acabando` e
  `acabou` criam; `tem` com item pendente já existente ajusta.
- **Pendente único**: produto já na lista à mão é ajustado, não duplicado,
  e mantém `origem = manual`.
- **Repetir**: gerar duas vezes seguidas não muda nada; acrescentar uma
  refeição e gerar soma só a diferença; tirar uma refeição subtrai; item
  comprado não volta a pendente nem é recriado sem aumento do pedido;
  item removido à mão não volta.
- **Os dois geram ao mesmo tempo**: o resultado é o de uma geração só.
- **Copiar semana**: datas deslocadas, ajustes mantidos, destino ocupado
  dá 409, receita apagada vira aviso.
- **Roteiro**: refeição além de `dura_dias` vai ao congelador (com o dia de
  descongelar) ou vira aviso; duas refeições da mesma receita na mesma
  sessão viram um passo só; ordem pelo tempo de preparo.

## Fora da v1

- Sugestão de cardápio pelo Claude, no painel e pela voz (o MCP será
  cliente destes endpoints, como é da lista).
- Registro do que foi comido e baixa na despensa.
- Nutrientes por refeição e por pessoa.
- Gerar a lista de só parte da semana (`de`/`ate`).
