# Telas do cardápio (D-30)

Complemento de docs/design/README.md e COMPRAS.md: mesmos tokens, fonte e regras.

| Tela | Arquivo |
|---|---|
| Semana (celular) | telas/CardapioSemanaCelular.dc.html |
| Receita (celular; no computador, painel lateral) | telas/CardapioReceitaCelular.dc.html |
| Roteiro de preparo (celular; no computador, painel lateral) | telas/CardapioPreparoCelular.dc.html |
| Semana (computador) | telas/CardapioDesktop.dc.html |

Navegação: o cardápio é uma aba dentro de Compras (Lista, Cardápio, Despensa). A barra
inferior do celular e a lateral do computador não mudam.

Comportamentos desenhados:
- celular: seletor de 7 dias; dia passado apagado; dia de hoje destacado; cada refeição lista
  os pratos com quem come e a porção ("Erik 1,5", "Laura 1"), e como fica pronto (pronto no
  domingo, na hora, congelado);
- computador: grade 7 dias x 4 refeições; célula clicável abre o prato para trocar; abaixo,
  roteiro de preparo resumido e prévia da lista lado a lado;
- avisos do roteiro (validade estourada) aparecem no topo da semana;
- receita: aviso "quantidades estimadas" com botão "Conferi, está certa"; ingrediente sem
  medida cadastrada aparece sinalizado; rendimento, tempo, validade e se congela;
- roteiro: uma aba por sessão (passada apagada), passos pelo que demora mais, caixa de marcar
  o que já foi feito, porções, destino (geladeira até X; congelador com dia de descongelar);
- lista: prévia com contagem de novos, ajustados e "confira" antes de gravar.

## Implementação

Código em `web/src/features/cardapio/`. Escolhas e diferenças em relação ao desenho:

- **Rotas** (hash, como o resto do painel): `#cardapio` é a aba; `#compras` e `#despensa`
  seguem como as outras duas. O que vale um link vai depois do `?`:
  `#cardapio?semana=2026-11-16&dia=2026-11-17`, `#cardapio?receita=6` (`&editar=1`;
  `receita=nova` cria), `#cardapio?roteiro=1` (`&sessao=ID` ou `no_dia`),
  `#cardapio?receitas=1` (busca de receitas). O "voltar" do navegador fecha o painel.
- **Cabeçalho de Compras** com título e as três abas (links) nas três telas; some o
  botão "Despensa" do topo da lista e o cabeçalho próprio da despensa. Barras inferior e
  lateral intactas (a aba Cardápio acende "Compras").
- **Celular x computador**: ponto de troca em 1280px (`xl`), o mesmo da despensa ao lado
  da lista. Abaixo disso vale a tela do celular, inclusive em tablet. Receita e roteiro
  são o `Dialogo` lateral: tela cheia abaixo de 768px, painel de 520px (novo `larga`) acima.
- **Semana, celular**: o "Trocar" por refeição virou "Editar" (ou "Adicionar" se vazia), que
  abre uma janela com trocar prato, quem come e porção (passos de 0,5; "Voltar ao padrão"),
  remover e adicionar. Tocar no nome do prato abre a receita. Não há o botão "Adicionar
  prato em terça" separado. Porção ajustada tem contorno.
- **Grade**: a célula abre a mesma janela de edição. Mostra os pratos, quem come do
  primeiro prato (abreviado) e uma palavra de preparo (pronto, congelado, na hora, aviso).
- **Como fica pronto**: lido do roteiro por `refeicao_id` (sessão -> "Pronto no domingo",
  congelador -> "Congelado: descongelar dia DD/MM", `no_dia` -> "Na hora, N min", aviso).
- **Roteiro**: a aba da sessão mostra "N passos" no lugar do "cerca de 1h30" do desenho:
  somar minutos seria agregação no front. O destino mostra "Geladeira até sáb 21/11"; com
  congelador, as duas porções separadas e a data de descongelar.
- **Receita**: "para N porções" usa o rendimento da receita (o desenho dizia "para 1
  porção"). "Pronta dura" e "Congela" viraram "Pode antecipar" e "Congela" (a API não tem
  "até 3 meses"). Ingredientes não se reordenam no formulário (só entram no fim). O produto
  do ingrediente é escolhido por busca; produto novo só por escolha explícita.
- **Medida do produto**: atalho "Cadastrar a medida de X" no ingrediente que não converte
  (`converte: false`), com a frase "1 unidade de Cebola tem 150 g".
- **Lista**: a prévia (GET) carrega sozinha e mostra as contagens; no celular o botão abre
  a prévia completa, no computador mostra os 6 primeiros e "Ver os N itens". "Confira" não
  vai para a lista (a despensa diz que tem): a tela diz isso. Semana encerrada: botões
  desabilitados com "Semana encerrada: vira histórico e não gera lista.". Na Lista, item
  de origem `cardapio` mostra "Do cardápio".
- **Sincronização**: a caixa de "feito" usa o polling de `/mudancas` da lista
  (`passos_feitos`); a aba Cardápio mantém a lista carregada só para ter o cursor.
- **Cores de quem come**: pela ordem de cadastro das pessoas (a primeira, mais escura).
