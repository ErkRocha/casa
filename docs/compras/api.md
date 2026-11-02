# API — `compras`, fase de lista e despensa

Implementado (D-25): lista e despensa, e o backend da nota fiscal e preços. Modelo em `modelo-dados.md`.

## Endereço

Pelo painel, `/api/compras/...`. O nginx do `web` repassa para o container
`compras` tirando o prefixo, como faz com `/api/` para finanças (D-19). Os
caminhos abaixo são os do serviço, sem o prefixo. `API_ROOT_PATH` do
serviço é `/api/compras`, para o `/docs` funcionar em `/api/compras/docs`.

No modo local (`scripts/local/`), o proxy do Vite precisa da mesma regra,
declarada antes da de `/api`.

## Convenções

- **Quem.** Toda escrita exige o cabeçalho `X-Quem` (texto, por enquanto o
  nome que o celular guardou). Sem ele, 400. O serviço o usa nas colunas
  `*_por` e em `app.autor` (auditoria). Na fase de uso compartilhado, o
  nginx passa a **sobrescrever** esse cabeçalho com a identidade do
  Tailscale, e o valor enviado pelo celular deixa de valer. Por ser um
  cabeçalho desde o começo, o contrato da API não muda nessa troca.
- **Idempotência.** O `POST` que cria item ou produto leva `id_cliente`
  (uuid gerado no celular). Repetir o mesmo `id_cliente` devolve 200 com o
  que já existe, não 201 nem erro.
- **Respostas de escrita trazem a linha inteira**, com `atualizado_em`. O
  celular substitui a cópia local pela resposta, sem esperar a próxima
  consulta de mudanças.
- **Concorrência: a última escrita vence**, campo a campo, porque a escrita
  é por ação ("comprar", "mudar quantidade"), não um `PUT` do item inteiro.
  Os dois mexendo no mesmo item ao mesmo tempo é raro, e o pior caso (uma
  quantidade sobrescrita) se vê na tela logo depois. Controle otimista com
  `If-Match` fica de fora até fazer falta.
- **Dinheiro e quantidade** saem como texto decimal, como em finanças.
- **Paginação**: as listas desta fase são pequenas (dezenas de itens) e não
  são paginadas, exceto produtos (`limite`) e o histórico.

## Endpoints

### Saúde

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/health` | `{"status": "ok", "banco": "ok"}`, como o de finanças |

### Seções

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/secoes` | Todas, na ordem do percurso |
| POST | `/secoes` | Cria; entra antes de "Sem seção" |
| PATCH | `/secoes/{id}` | Renomeia |
| PUT | `/secoes/ordem` | Recebe a lista de ids na ordem nova; reordena numa transação |
| DELETE | `/secoes/{id}` | Soft delete; os produtos dela vão para "Sem seção" |

### Produtos

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/produtos?busca=&limite=20` | Busca por trigram para o campo de adicionar; mais comprados primeiro no empate |
| POST | `/produtos` | `{nome, secao_id?, unidade_padrao?, id_cliente}` |
| PATCH | `/produtos/{id}` | Nome, seção, unidade |
| DELETE | `/produtos/{id}` | Soft delete; recusa (409) se há item pendente dele na lista |

### Lista

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/lista?comprados_desde=` | Pendentes e os comprados depois de `comprados_desde` (padrão: 6 horas atrás), ordenados pela seção e pelo nome, já com o nome do produto e da seção. Traz o `cursor` para `/mudancas` e as `sugestoes`: produtos "acabando" na despensa que ainda não estão na lista |
| POST | `/lista/itens` | `{id_cliente, produto_id ou produto_nome, quantidade?, unidade?, observacao?, origem?}` (`origem`: `manual`, o padrão, ou `voz`; `despensa` é só do ciclo). Com `produto_nome` sem produto, cria o produto em "Sem seção" na mesma transação |
| PATCH | `/lista/itens/{id}` | Quantidade, unidade, observação |
| POST | `/lista/itens/{id}/comprar` | Marca comprado (quem e quando); despensa vai para `tem` |
| POST | `/lista/itens/{id}/desfazer` | Volta a pendente; despensa volta para `acabou` |
| DELETE | `/lista/itens/{id}` | Tira da lista (soft delete) |
| GET | `/lista/historico?produto_id=&limite=&offset=` | Comprados, mais recentes primeiro, paginado com total |

Casos que a fase precisa cobrir nos testes:

- **Os dois adicionam o mesmo produto.** O segundo `POST` encontra o
  pendente (único parcial do modelo) e devolve 200 com ele e
  `"ja_estava": true`, sem somar quantidade: na prática os dois quiseram
  dizer a mesma coisa. A tela avisa "já estava na lista, por Fulano".
- **Os dois marcam comprado.** `comprar` em item já comprado devolve 200 com
  o item como está (mantém o primeiro `comprado_por`). Não é erro: o
  resultado que os dois queriam já aconteceu.
- **Comprar item removido**: 409, com o item na resposta, para o celular
  tirá-lo da tela.

### Despensa

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/despensa?estado=` | Produtos acompanhados, por seção; filtro por estado no banco |
| PUT | `/despensa/{produto_id}` | `{estado}`. Começa a acompanhar se não acompanhava. Em `acabou`, cria o item pendente (se não houver) e o devolve junto: `{despensa, item_criado}` |
| DELETE | `/despensa/{produto_id}` | Para de acompanhar (soft delete) |

### Mudanças

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/mudancas?desde=<cursor>` | Tudo o que mudou desde o cursor, nas quatro tabelas, com as linhas inteiras (as apagadas com `deleted_em`), e o cursor novo |

```json
{
  "cursor": "2026-11-02T14:03:11.482911-03:00",
  "itens": [ { "id": 41, "situacao": "comprado", "comprado_por": "Laura", "...": "..." } ],
  "despensa": [],
  "produtos": [],
  "secoes": []
}
```

Ver a seção seguinte.

### Identidade (roadmap, Lista de compras, 3)

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/eu` | Quem o serviço vê: `origem = tailscale` (o nome vem da tailnet; o aparelho não pergunta), `aparelho` (o `X-Quem`) ou nulo (perguntar "quem é você?") |
| GET | `/identidades` | Os logins da tailnet cadastrados |
| POST | `/identidades` | `{"login", "nome"}`: liga o login ao nome exibido. Repetido: 409 |
| PATCH | `/identidades/{id}` | Troca o `nome` |
| DELETE | `/identidades/{id}` | Soft delete; o login volta a aparecer com o nome do Tailscale |

Com `Tailscale-User-Login` (posto pelo `tailscale serve`, que apaga o que o
cliente mandar), o "quem" de toda escrita é o nome cadastrado para o login,
senão o `Tailscale-User-Name` (decodificado de RFC 2047), senão o login. O
`X-Quem` do cliente é ignorado: o proxy o substitui pelo login, e o serviço
não o lê nesse caso.

### Nota fiscal e preços (backend, 02/11/2026)

Sem telas ainda (D-15: precisam de desenho antes). Toda escrita exige
`X-Quem`; o que a leitura grava sozinha vai para a auditoria com o autor
`leitura_nfce`.

| Método | Caminho | O que faz |
|---|---|---|
| POST | `/notas` | `{"entrada": "<URL do QR code ou chave>"}`. Confere a chave (44 dígitos, dígito verificador, modelo 65, UF RS), busca a consulta pública e guarda a resposta **inteira**. 201 com a nota; **200 com a nota que já existe** se a chave já foi lida (sem buscar de novo). Consulta ou leitor falhou: 201 com `status = erro`. Entrada inválida: 422, nada gravado |
| GET | `/notas` | As notas, mais recentes primeiro, sem o conteúdo bruto |
| GET | `/notas/{id}` | A nota com os itens, `soma_itens`, `diferenca` (total menos a soma: desconto da nota inteira aparece, não bloqueia) e quantos estão `sem_produto` |
| POST | `/notas/{id}/reler` | Só nota com erro: interpreta de novo o conteúdo guardado, ou busca de novo (sem conteúdo, ou `?buscar_de_novo=true`). Lida: 409 |
| GET | `/notas/itens-sem-produto` | A fila de "associar" |
| PUT | `/notas/{id}/itens/{item_id}/produto` | `{"produto_id": 7}`. Associa e grava (ou reforça) o apelido do texto no mercado da nota, e o do GTIN quando houver |
| GET | `/notas/{id}/sugestoes-transacao` | Despesas de finanças do mesmo dia (São Paulo) e mesmo valor total, pela API de finanças (`GET /transacoes`). Só sugestão. Finanças fora do ar: 502 |
| PUT | `/notas/{id}/transacao` | `{"transacao_id": 123}` confirma o vínculo (nulo desfaz); a transação precisa existir em finanças |
| DELETE | `/notas/{id}` | Soft delete da nota e dos itens; a mesma chave pode ser lida de novo |
| GET | `/mercados` | Os mercados, criados pelo CNPJ da chave |
| PATCH | `/mercados/{id}` | `nome` como o casal chama o mercado, `cidade` |
| GET | `/precos?produto_id=&mercado_id=` | `vw_preco_produto` com os nomes: último preço e data, mínimo, máximo, média e quantas compras, por produto, mercado e unidade |

**Associação automática**, na leitura: GTIN aprendido > apelido do texto no
mesmo mercado > apelido sem mercado > apelido de outro mercado, só se todos
concordam. Nada disso: o item fica sem produto, na fila.

**Pendente de uma nota real** (roadmap): o leitor da página
(`compras/nfce/leitor_svrs.py`, versão `svrs-html-1`) segue o layout
presumido do portal SVRS, e a URL montada só com a chave
(`entrada.URL_CONSULTA_POR_CHAVE`) também não foi conferida. O teste contra
a amostra fica pulado até existir `compras/tests/amostras/nfce_rs_anonimizada.html`.

---

## Os dois celulares ao mesmo tempo: polling com `desde` ou SSE

O problema: no mercado, um marca "leite" como comprado, e o outro, dois
corredores adiante, precisa ver isso logo, para não pôr outro leite no
carrinho. "Logo" é segundos, não instantâneo.

### Polling com `desde`

O celular chama `GET /mudancas?desde=<cursor>` a cada poucos segundos,
enquanto a tela está aberta, e aplica o que vier.

Prós:
- **Simples nas três pontas.** Uma requisição comum: o nginx, o `tailscale
  serve` e o proxy do Vite repassam sem configuração nova. Testa como
  qualquer endpoint.
- **Aguenta o celular de verdade.** Navegador de celular congela a aba em
  segundo plano e derruba conexões quando a tela apaga ou a rede troca de
  Wi-Fi para 4G. Com polling, a próxima chamada depois de voltar busca
  tudo o que faltou, sem lógica de reconexão.
- **É o mesmo mecanismo do uso offline.** Quando o celular voltar a ter
  sinal, a sincronização é exatamente "o que mudou desde o meu cursor". O
  risco em aberto do roadmap fica mais barato de resolver.
- **Recupera de qualquer perda.** O cursor fica no celular; nada no servidor
  precisa lembrar quem estava conectado.

Contras:
- **Atraso** de até um intervalo (3 s com a tela aberta).
- **Requisições vazias.** Dois celulares a cada 3 s, só durante a compra,
  dão algumas centenas de requisições pequenas por ida ao mercado. Para um
  Postgres com índice em `atualizado_em`, é nada.

### SSE

O servidor mantém uma conexão aberta com cada celular e empurra cada
mudança quando ela acontece.

Prós:
- **Instantâneo**, e sem requisição vazia.

Contras:
- **Infraestrutura nova.** O nginx precisa de `proxy_buffering off`, timeouts
  longos e cuidado com o HTTP/2 do `tailscale serve`; o Vite de
  desenvolvimento e o modo local também. Cada camada é um lugar novo para
  a conexão morrer em silêncio.
- **O serviço precisa saber das mudanças para empurrá-las**: `LISTEN/NOTIFY`
  do Postgres e um processo segurando conexões abertas, em vez de
  requisições curtas e sem estado.
- **Não dispensa o `desde`.** A conexão cai sempre no celular (tela apagada,
  troca de rede), e na volta é preciso buscar o que se perdeu. Ou seja: SSE
  é o polling **mais** a conexão aberta, não no lugar dele.

### Recomendação: polling com `desde`

Polling, a cada 3 segundos com a tela visível e parado com ela em segundo
plano (`visibilitychange`), com uma consulta imediata ao voltar e logo
depois de cada escrita. O ganho do SSE, sair de "até 3 segundos" para
"instantâneo", não muda nada em quem está andando no mercado, e o custo
dele é a parte mais frágil do sistema numa rede de celular. Se um dia fizer
falta, o SSE entra **por cima**, como aviso de "tem novidade, busque", sem
mudar o `/mudancas`.

### Como o cursor funciona

- **O cursor é o relógio do servidor, não o do celular.** Cada resposta de
  `/mudancas` (e de `/lista`) traz como `cursor` o `now()` do Postgres no
  momento da leitura. O celular só devolve o que recebeu.
- **A consulta é `atualizado_em > desde - 30 segundos`.** A sobreposição
  existe porque `now()` é o início da transação: uma escrita que começou
  antes da leitura e confirmou depois dela tem `atualizado_em` anterior ao
  cursor, e sem a folga sumiria. As escritas aqui são de uma linha e duram
  milissegundos; 30 segundos cobre com sobra.
- **Repetir não faz mal.** A folga devolve de novo linhas já vistas, e o
  celular substitui pela versão mais nova (mesma `id`, `atualizado_em`
  maior ou igual). Aplicar duas vezes dá o mesmo resultado.
- **Apagar é mudança como outra qualquer.** A linha com `deleted_em` volta
  nas mudanças, e o celular a tira da tela. É o soft delete fazendo o
  trabalho que a sincronização precisaria fazer de outro jeito.
- **Cursor muito velho** (mais de 7 dias, ou ausente): a resposta diz
  `"recarregar": true`, e o celular busca `/lista` e `/despensa` inteiras.
  Evita que um celular esquecido numa gaveta peça o histórico todo.

### Fora desta fase

- O cliente do MCP de voz: ele usará estes mesmos endpoints, com o seu
  próprio `X-Quem` (ou a identidade definida na fase de uso compartilhado).
