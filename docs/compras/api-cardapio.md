# API — `compras`, módulo de cardápio (D-30)

**Implementado (migrations 0004 e 0005).** Diferenças em relação ao plano no fim
deste arquivo. Mesmo serviço, mesmo endereço
(`/api/compras/...`) e mesmas convenções de `api.md`: `X-Quem` em toda
escrita (substituído pela identidade do Tailscale quando há), `id_cliente`
no `POST` que cria receita, resposta de escrita com a linha inteira,
quantidade como texto decimal, a última escrita vence. Modelo em
`modelo-cardapio.md`.

Listas paginadas (regra do `CLAUDE.md`): receitas e semanas, com
`limite`/`offset` e `total`. Pessoas, refeições de uma semana e roteiro
são pequenos e vêm inteiros.

O cardápio não entra no `/mudancas`: é planejado com calma, não com os dois
no mercado. A tela busca de novo ao abrir e depois de cada escrita. A
exceção são os passos do roteiro marcados como feitos (`passos_feitos`),
que os dois celulares veem ao mesmo tempo na cozinha. O que a
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
| GET | `/receitas?busca=&tipo=&pode_antecipar=&revisadas=&limite=20&offset=0` | Busca no `nome_normalizado` (contém; quem começa com o texto vem antes), com `total`. `revisadas=true|false` filtra pelas quantidades conferidas |
| GET | `/receitas/{id}` | A receita com os ingredientes na ordem, o nome do produto e se cada um converte |
| POST | `/receitas` | `{id_cliente, nome, tipo, rendimento_porcoes, tempo_preparo_min?, modo_preparo?, pode_antecipar, dura_dias?, pode_congelar, ingredientes: [{produto_id ou produto_nome, quantidade?, unidade, observacao?}]}`. Ingrediente com `produto_nome` sem produto cria o produto em "Sem seção", na mesma transação. `id_cliente` repetido: 200 com a que existe. Criada por pessoa, nasce com `quantidades_revisadas = true`, `revisadas_por` = quem e `revisadas_em` = agora |
| POST | `/receitas/{id}/conferir` | "Conferi, está certa": marca `quantidades_revisadas = true` com quem e agora e devolve a receita. Já conferida: 200 com a receita como está (vale a primeira conferência) |
| PUT | `/receitas/{id}` | Mesmo corpo, sem `id_cliente`: substitui os campos e a lista de ingredientes numa transação. Todo ingrediente antigo leva soft delete e o novo é criado (nunca UPDATE no lugar), para a semana passada continuar lendo os seus (D-30). Não mexe em `quantidades_revisadas`, `revisadas_por` nem `revisadas_em`. Aqui é `PUT` porque a receita é editada como um formulário inteiro, não por ação |
| POST | `/receitas/{id}/duplicar` | Cópia com o nome "<nome> (cópia)", para variar uma receita; leva a conferência da origem |
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
| GET | `/semanas/{id}/preparo` | O roteiro, calculado na hora (regras em `modelo-cardapio.md`, "Preparo"). Cada sessão traz `sessao_id` e cada passo traz `feito` |
| PUT | `/sessoes/{sessao_id}/passos/{receita_id}/feito` | `{id_cliente}`: marca o passo como feito, por quem pede e agora. 201 com a linha de `passos_feitos`. Já feito (por qualquer um): 200 com o que existe, vale o primeiro. Mesmo `id_cliente` repetido: 200. `id_cliente` de outro passo: 409. Sessão ou receita inexistente ou apagada: 404 |
| DELETE | `/sessoes/{sessao_id}/passos/{receita_id}/feito` | Desfaz (soft delete) e devolve a linha com `deleted_em`. Não estava feito: 200 com `null`, sem mudança |

```json
{
  "sessoes": [
    {
      "sessao_id": 7, "data": "2026-11-22", "rotulo": "domingo",
      "passos": [
        {
          "receita": {"id": 4, "nome": "Frango assado", "tempo_preparo_min": 90},
          "porcoes": "6.00", "fator": "1.500",
          "feito": {"por": "Laura", "em": "2026-11-22T14:05:31.482913Z"},
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

`feito` é `{"por", "em"}` quando o passo foi marcado e `null` quando não. A
marcação (`PUT .../feito`) responde a linha inteira:

```json
{
  "id": 12, "sessao_id": 7, "receita_id": 4,
  "feito_por": "Laura", "feito_em": "2026-11-22T14:05:31.482913Z",
  "id_cliente": "6f1c2a9e-8f3a-4c35-9d7e-2b0f4b6a1c11",
  "criado_em": "2026-11-22T14:05:31.482913Z",
  "atualizado_em": "2026-11-22T14:05:31.482913Z",
  "deleted_em": null
}
```

No `GET /mudancas`, a chave `passos_feitos` traz essas mesmas linhas, as
que mudaram desde o cursor, e a desfeita volta com `deleted_em`
preenchido (a tela troca a cópia local pela mais nova, como nas outras
chaves):

```json
{
  "cursor": "2026-11-22T14:06:00.000000Z", "recarregar": false,
  "itens": [], "despensa": [], "produtos": [], "secoes": [],
  "passos_feitos": [
    {"id": 12, "sessao_id": 7, "receita_id": 4, "feito_por": "Laura",
     "feito_em": "2026-11-22T14:05:31.482913Z", "id_cliente": "6f1c2a9e-8f3a-4c35-9d7e-2b0f4b6a1c11",
     "criado_em": "2026-11-22T14:05:31.482913Z", "atualizado_em": "2026-11-22T14:05:58.100000Z",
     "deleted_em": "2026-11-22T14:05:58.100000Z"}
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

---

# Diferenças em relação ao plano (17/11/2026)

Todos os endpoints acima existem. O que a implementação acrescentou ou
resolveu:

- **Paginação.** `GET /receitas` e `GET /semanas` respondem
  `{items, total, limite, offset}` (a lista de histórico de `api.md` usa
  `limit`; aqui o nome é o do plano, `limite`).
- **`GET /semanas/{inicio}?ingredientes=true`** traz os ingredientes de cada
  receita; na semana passada, os vivos no fim do domingo dela (é por onde a
  regra de D-30 aparece na leitura). Sem o parâmetro, a receita vem sem
  `ingredientes`. A resposta tem `dias` (os 7, cada um com as refeições por
  tipo e ordem), `sessoes` e `passada`.
- **`GET /produtos/sem-medida`** responde uma lista (com `limite` e
  `offset`) de `{id, nome, ..., motivos, receitas}`; `usados_em_receita` é
  verdadeiro por padrão. Com `false`, todo produto sem `medida_base`.
- **Roteiro.** Cada passo traz também `porcoes_geladeira` e
  `porcoes_congelador` (regra 6), `avisos` (os mesmos textos do `avisos` de
  cima) e cada destino leva `descongelar_em` (nulo na geladeira). O texto do
  aviso termina com "; faça uma sessão mais perto ou prepare no dia".
- **Lista pelo cardápio.** `ajustados`, `sem_mudanca` e `confira` trazem
  também `pedido` e `de` (as receitas); `ajustados` traz `removido: true`
  quando a semana deixou de pedir e o item saiu da lista (`depois` zero); na
  prévia, `criados[].item_id` é nulo; `avisos[].produto` é nulo no aviso de
  receita apagada. A prévia e a gravação usam o mesmo plano; só a gravação
  trava a semana (`FOR UPDATE`). Semana inexistente: 404; semana passada:
  409, com a semana no corpo.
- **Receitas.** Nome repetido (sem caixa nem acento): 409 com a receita que
  existe. `duplicar` numera a cópia se o nome já existe ("(cópia 2)").
  Em `GET /receitas/{id}`, `converte` de um ingrediente `a_gosto` é
  verdadeiro (não há o que converter).
- **Pessoas.** Nome repetido ou login já ligado a outra pessoa: 409;
  `identidade_id` inexistente: 404.
- **Refeições.** `PATCH` de `receita_id: null` sem `observacao` é 422;
  dia fora da semana é 422 (e o trigger do banco é a segunda barreira).
  `PUT /refeicoes/{id}/pessoas` aceita lista vazia (ninguém come) e recusa
  pessoa repetida.
- **`DELETE /semanas/{id}`** responde a semana com `deleted_em`.
- **`POST /semanas/{id}/copiar`** responde a semana inteira (como
  `GET /semanas/{inicio}`) mais `avisos: [{refeicao_id, texto}]`.

# Revisão e passos feitos (migration 0005, 17/11/2026)

- **Receitas** trazem `quantidades_revisadas`, `revisadas_por` e
  `revisadas_em` em toda resposta (resumo e detalhe).
- **`PUT .../feito`** responde 201 quando marca e 200 quando já estava
  feito; o mesmo `id_cliente` de um passo já desfeito marca de novo (a
  linha antiga volta, com o autor e a hora novos).
- **`DELETE .../feito`** não valida sessão nem receita: o que não está
  feito responde 200 e `null`, existindo ou não.
