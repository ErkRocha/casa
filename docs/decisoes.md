# Decisões de arquitetura

Cada decisão registra o *porquê*, não só o *quê*. Antes de contrariar alguma,
leia o motivo — ele costuma ser a parte que não é óbvia.

---

## D-01 — Postgres, Python no backend, React no front

Postgres foi requisito do usuário. Python no backend porque o coração do
sistema é ingestão e análise de dados, onde o ecossistema (`pdfplumber`,
`pandas`) é muito superior ao de JS — e porque é a linguagem que o usuário
domina melhor. React + Vite no front por familiaridade prévia.

Descartado: TypeScript ponta a ponta com Next.js. Traria projeto único e
tipagem compartilhada, mas extração de PDF em JS é pobre e acabaria exigindo
um script Python de qualquer forma.

---

## D-02 — `competencia` separada de `data`

Compra feita em 28/07 pode cair na fatura de agosto. Sem separar a data do
fato do mês de referência, os relatórios mensais não batem com o valor que
efetivamente se paga no mês. `competencia` guarda sempre o dia 1º do mês.

---

## D-03 — `pessoa_id` nullable em vez de N:N

Os gastos do casal são conjuntos; não há acerto de contas entre as duas
pessoas. O usuário quer apenas ver quanto cada um gastou, separadamente.

A modelagem N:N (transação ligada a várias pessoas) parece resolver "anexar
aos dois", mas duplica valor: a mesma transação soma para A e para B, e o
total infla. Com `pessoa_id` nullable, cada transação tem exatamente uma
atribuição e os três baldes — pessoa A, pessoa B, conjunto — somam o total
exato, sem sobreposição possível.

`pessoa_id` responde **quem gastou**, nunca **quem se beneficiou**.

---

## D-04 — Gasto com pets é categoria, não pessoa

Categoria responde o tipo do gasto: Pets › Ração, Pets › Veterinário. Custo
por pet individual, quando houver mais de um, sai de tag — que é o eixo
transversal à hierarquia de categorias. Os dois são independentes de
`pessoa_id`.

---

## D-05 — Contas e transferências desde o v1

Sem `contas`, o sistema sabe para onde o dinheiro vai mas não de onde saiu, e
conciliação de saldo fica impossível. Sem `tipo = transferencia`, o pagamento
da fatura importado do extrato vira despesa nova e todo o financeiro conta em
dobro. As duas coisas são estruturais e caras de retroencaixar.

---

## D-06 — Soft delete e auditoria por trigger

Vai haver agente escrevendo no banco sem supervisão humana em cada linha.
Quando ele categorizar 40 transações errado, a diferença entre desfazer em um
comando e refazer o mês na mão é ter `deleted_em` e a tabela `auditoria` com
`dados_antes`/`dados_depois`. Trigger em vez de código de aplicação porque
agentes escrevem por caminhos diferentes.

---

## D-07 — Ingestão nunca escreve direto em `transacoes`

O agente grava em `importacao_itens` com status `pendente` e uma sugestão de
categoria, local e pessoa, cada uma com score de confiança. O usuário aprova
em lote pelo painel. É a decisão que separa ferramenta confiável de banco
bagunçado em três meses.

O `hash_dedup` protege a promoção: reimportar o mesmo PDF ou aprovar duas
vezes esbarra no índice único.

---

## D-08 — Parser determinístico antes do LLM

Fatura de cartão tem layout fixo por banco. Depois de importar o mesmo banco
duas vezes, vale escrever um parser determinístico e deixar o LLM apenas como
fallback para formato desconhecido. Mais barato, mais rápido e sem risco de
alucinar número.

O PDF nunca vai inteiro para o modelo: `pdfplumber` extrai, o LLM só
estrutura o texto já extraído.

---

## D-09 — Correção do usuário vira regra

Toda vez que o usuário corrige uma sugestão na tela de revisão, isso grava ou
reforça uma linha em `regras_categorizacao` (ou um `produto_alias`). O
enriquecimento consulta regras e aliases primeiro — exatos e gratuitos — e só
manda para o LLM o que sobrou. Depois de alguns meses, a maioria das
importações passa sem chamada de modelo.

---

## D-10 — Insights com tools, não text-to-SQL

O agente de insights recebe funções Python prontas (`gasto_por_categoria`,
`comparar_periodos`, `status_orcamento`, `variacao_preco_produto`,
`recorrencias_com_reajuste`, `transacoes_atipicas`) que rodam SQL agregado e
devolvem JSON. Ele escolhe o que chamar e interpreta o resultado.

Text-to-SQL livre é impressionante em demo e imprevisível no uso real. E o
modelo nunca faz aritmética: erra e escreve bem o suficiente para o erro
passar despercebido.

Boa parte das detecções (assinatura reajustada, orçamento estourado, gasto
fora do padrão por mediana e desvio) é SQL puro e não precisa de LLM nenhum.

---

## D-11 — Role read-only para o agente de insights

Garantia estrutural, não instrução de prompt. Uma role separada no Postgres
com `SELECT` apenas — assim a impossibilidade de corromper dados não depende
de ninguém lembrar de escrever a regra no prompt.

---

## D-12 — Harness determinístico em volta do LLM

O modelo é uma peça no meio de código comum e testável:

- structured output validado com Pydantic; resposta inválida é reenviada com
  o erro anexo, até 3 tentativas;
- prompt em arquivo versionado, com a versão gravada na `importacoes`;
- log estruturado por execução: tokens, custo, latência, tentativas,
  distribuição de confiança;
- circuit breaker: se mais de 30% dos itens vierem com confiança baixa,
  aborta a importação inteira em vez de encher o staging de lixo.

---

## D-13 — Evals com PDFs reais

Um diretório com ~10 PDFs e o gabarito JSON do resultado correto, rodado por
`make eval`, reportando acurácia de extração e de categorização. É o que
transforma "mexi no prompt e acho que melhorou" em número — e com agente
editando prompts, é a rede de segurança.

---

## D-14 — Agregação no banco

O front recebe dados prontos e desenha. Filtro cruzado vira `WHERE` na query,
não `filter()` em array no navegador. Com anos de histórico é a diferença
entre gráfico instantâneo e painel travando.

---

## D-15 — Design das telas antes da implementação do front

As telas saem do Claude Design, que gera protótipo e empacota o resultado
para handoff a um agente de código. O Claude Code recebe a interface já
decidida e só liga na API, em vez de inventar UI enquanto implementa.

---

## D-16 — Sincronização via Pluggy como fonte de ingestão

O PDF exige baixar a fatura, subir o arquivo e esperar o parser daquele banco
existir. A Pluggy, pelo conector MeuPluggy, entrega as transações já
estruturadas e de graça para uso pessoal. A ingestão continua sendo a mesma
coisa: a Pluggy entra como mais uma **origem**, pelo mesmo contrato dos
parsers de PDF.

**Atualização (05/10/2026, decisão do usuário): a Pluggy é a fonte única do
dia a dia.** A importação por PDF foi descontinuada como rotina. Os parsers
ficam no código como fallback: banco não coberto pela Pluggy, período
anterior à janela dela (até 12 meses) e o dia em que ela sair do ar ou mudar
de termos. O dado de PDF já importado **dentro** da janela da Pluggy é
removido por soft delete antes da primeira sync (Fase 5b, passo 7). O
**anterior** à janela é preservado: é o único registro daquele período.

Limites do plano gratuito, que moldam o desenho: até 5 conexões ativas,
apenas contas do mesmo titular, dados atualizados pela própria Pluggy a cada
24h, histórico de até 12 meses, transações paginadas de 500 em 500 por cursor
e rate limit por minuto por IP (360/min em auth e transactions, 20/min no
`PATCH /items`). Uso comercial e contas de terceiros exigem plano pago. Como a
Pluggy já atualiza sozinha a cada 24h, a sync só **lê**: não força atualização
pelo `PATCH /items`.

O que não muda:

- **Regra 5 e D-07, integralmente.** A sync nunca escreve em `transacoes`. Ela
  cria uma `importacao` com `origem = 'pluggy'` e grava itens em
  `importacao_itens`, que o usuário revisa e promove pelo painel, como faz com
  qualquer PDF. Sincronização automática não é promoção automática.
- **Um caminho só.** O JSON da Pluggy é convertido para `ItemExtraido`, o
  mesmo contrato dos parsers, e daí em diante passa pelo service de ingestão
  existente. O enriquecimento (D-09), a revisão e a promoção são os mesmos. Um
  caminho paralelo divergiria do principal no primeiro ajuste de regra.
- **`pessoa_id` segue a regra 3.** A sugestão vem do titular da conta mapeada
  (`contas.titular_id`), e conta conjunta sugere `NULL`, ou seja, conjunto.
  Regra de categorização e titular do cartão (pelo final do cartão, como no
  PDF) continuam à frente. É o que atribui certo o cartão adicional: a fatura
  é do titular, mas quem comprou foi o dono do adicional.

O que é novo:

- **Deduplicação já no staging, pelo id da transação na Pluggy.** A sync roda
  todo dia sobre uma janela que se sobrepõe à anterior. Sem uma barreira no
  staging, cada execução empilharia de novo os mesmos itens aguardando
  revisão, inclusive os já rejeitados. O id externo tem que ser único em
  `importacao_itens`, em qualquer status. O `hash_dedup` de `transacoes`
  continua sendo a segunda barreira, na promoção.
- **Uma origem por conta e período.** O `hash_dedup` inclui
  `descricao_original`, e o texto que a Pluggy devolve não é o mesmo da linha
  do PDF. Se a mesma compra entrar pelas duas origens, a segunda barreira não
  pega. Por isso cada conta mapeada tem uma data a partir da qual a Pluggy
  manda (`sincronizar_desde`). Antes dela vale o PDF, como registro
  histórico; depois dela, o PDF daquela conta só entra se a Pluggy falhar. O
  PDF que já estava no banco depois dessa data sai na limpeza que precede a
  primeira sync.
- **Duplicata vinda da própria Pluggy.** O id externo não basta: há caso
  real de a Pluggy entregar a mesma movimentação duas vezes, com ids
  diferentes (dois "Pagamento recebido" de mesmo valor, no mesmo dia, no
  cartão Nubank, quando o app do banco mostra um só). Mesma conta, data,
  valor e descrição com ids diferentes marca o item com observação e
  confiança reduzida. Nunca descarta sozinho: duas compras iguais no mesmo
  dia também existem, e quem decide é a revisão.
- **Só transação consolidada.** Transação ainda pendente na Pluggy pode mudar
  de valor ou sumir. Entra só a lançada. O id estável é o que permite pegá-la
  na sync seguinte, quando consolidar.

Segurança e escopo:

- Client id e secret ficam só no `.env`, com placeholder no `.env.example`,
  nunca no repositório, em log ou em tabela.
- O sistema continua sem ir para a internet. A sync só faz requisição de saída
  para a API da Pluggy. Nenhuma porta é exposta e nada é recebido por webhook.
- Nesta fase entram só as contas do usuário. As contas da esposa ficam
  pendentes até a Pluggy confirmar que isso cabe no uso pessoal. O desenho já
  comporta isso: incluí-las é cadastrar o mapeamento de outra conexão para
  contas com outro `titular_id`, sem mudança estrutural.

Esta decisão substitui o item "Integração com Open Finance ou API de banco"
que estava em "Fora de escopo" no roadmap. Ele foi excluído por dois motivos:
integração direta com banco custa caro e expõe credencial, e um dado que
entrasse sozinho no banco ameaçaria a D-07. Os dois deixaram de valer. O
MeuPluggy é gratuito para uso pessoal, a credencial bancária fica na Pluggy e
não aqui, e o dado continua passando pelo staging e pela aprovação do usuário.
Integração direta com API de cada banco segue fora de escopo.

---

## D-17 — Docker como modo de execução principal em casa

Decisão do usuário, 07/10/2026.

O modo local sem Docker (`scripts/local/`) mostrou o limite dele na prática:
o Postgres roda como processo comum do usuário, preso ao console de quem o
iniciou, e cai quando esse console fecha — o que aconteceu junto de cada
suspensão do Windows. O banco se recuperava sozinho, mas o sistema ficava
fora do ar até alguém subir tudo de novo, e a sync diária da Pluggy (fase 5b)
precisa dele no ar.

- **Docker é o modo principal.** O PC de casa fica ligado e bloqueado, sem
  suspensão, rodando o sistema continuamente. Os três serviços do compose têm
  `restart: unless-stopped`: voltam sozinhos depois de reiniciar o Windows
  (com o Docker Desktop iniciando no login) e só ficam parados se alguém os
  parar de propósito.
- **O modo local vira reserva**, para máquina sem Docker. Depois da migração,
  o banco local é **cópia congelada** e não deve mais ser usado: dois bancos
  ativos divergiriam, e não há como reconciliar dois históricos de staging,
  aprovações e auditoria. O `scripts/local/subir.sh` recusa subir quando o
  banco do Docker está no ar, quando a porta está ocupada por outro processo
  ou depois da migração.

**Pendente:** a migração ainda não foi feita — a máquina não tinha Docker em
07/10/2026. O roteiro está em `scripts/migrar_para_docker.sh` (backup do
banco local, restore no container, conferência de contagens, `make validar`
e simulação da sync). Até ela rodar, o banco local continua sendo o único
banco ativo.
