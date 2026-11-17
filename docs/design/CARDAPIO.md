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
