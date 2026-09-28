# faturas/

É aqui que vão os PDFs de fatura e extrato.

**Nada desta pasta entra no git** — só este README e os `.gitkeep`. São dados
financeiros pessoais: uma vez commitados, saem do histórico só reescrevendo a
árvore inteira. O `.gitignore` da raiz já cuida disso, mas a proteção só passa
a valer quando o repositório existir (hoje ainda não há `git init`).

---

## Onde colocar

Uma pasta por origem, com o nome do banco em minúsculas:

```
faturas/
  nubank/
    2026-06.pdf
    2026-07.pdf
    2026-08.pdf
  itau/
    extrato-2026-07.pdf
  gabaritos/
    nubank_2026-07.json      ← criado depois, na etapa de evals
```

O nome do arquivo não importa para o parser — ele lê o conteúdo. Datar ajuda
só você a se achar.

## Quantos, e de quais

Para eu escrever o parser determinístico de um banco: **2 ou 3 faturas do
mesmo banco**, de meses diferentes. Meses diferentes importam mais que
quantidade — é o que revela o que no layout é fixo e o que varia.

Comece por **um banco só**, o que você mais usa. A fase 5 do roadmap é
explícita nisso: extrair de um banco, fazer funcionar de ponta a ponta, e só
então generalizar.

Para os evals (D-13), depois: ~10 PDFs com o gabarito JSON do resultado
correto ao lado, em `gabaritos/`. É o que transforma "mexi no prompt e acho
que melhorou" em número.

## Se preferir mascarar

Editar os valores não atrapalha — o que o parser precisa é do **layout**:
posição das colunas, formato de data, como o banco escreve descrição, onde
aparecem parcelas ("03/12"), como marca estorno e IOF.

O que **não** pode mudar sem quebrar o trabalho: a estrutura da tabela, o
formato dos números (`1.234,56`) e o das datas (`28/07` ou `28 JUL`).

Trocar seu nome, número do cartão e agência por texto qualquer é seguro.

## Como isso é lido

O PDF **nunca vai inteiro para um modelo de IA** (D-08). O `pdfplumber`
extrai o texto localmente; o parser determinístico do banco resolve o que
reconhece; e só o que sobrar de layout desconhecido é estruturado por LLM,
com o resultado validado por schema.

Nada aqui é enviado para lugar nenhum enquanto a fase 5 não existir — hoje
esta pasta é só um depósito.
