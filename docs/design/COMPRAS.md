# Telas da lista de compras (D-25)

Complemento de docs/design/README.md: mesmos tokens, fonte e regras.

| Tela | Arquivo |
|---|---|
| Lista no mercado | telas/ComprasListaCelular.dc.html |
| Adicionar item (painel que sobe de baixo) | telas/ComprasAdicionarCelular.dc.html |
| Despensa | telas/ComprasDespensaCelular.dc.html |

Navegação:
- Celular: a barra inferior passa a ter 5 itens: Início, Lançamentos, Compras, Revisar, Análises.
  Compras fica no meio.
- Computador: "Compras" entra no primeiro grupo da barra lateral, depois de Lançamentos.
  Não há prancheta de computador: use a mesma tela com largura máxima de leitura
  (lista centralizada), e a despensa pode ficar ao lado da lista quando houver espaço.

Comportamentos desenhados:
- itens agrupados pela ordem das seções; caixa de marcar de 28px com alvo de toque de 56px;
- cada item mostra quem adicionou ou "Voltou da despensa";
- comprados descem para "No carrinho", riscados, com quem pegou e há quanto tempo; dá para esconder;
- "Acabando em casa" aparece no topo como sugestões de um toque (vem do GET /lista);
- adicionar: busca enquanto digita; produto já pendente mostra "Já na lista" e o botão vira
  "Atualizar ... na lista" (pendente único); opção de criar produto novo;
- despensa: três estados por produto (Tem, Acabando, Acabou) com a última compra;
- rodapé da lista informa a sincronização.
