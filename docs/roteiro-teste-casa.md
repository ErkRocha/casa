# Roteiro de teste em casa

Ordem para testar o que ficou pronto até 05/11/2026. Os comandos são para o
Git Bash na pasta `controle-casa`. Neste PC o make é o `mingw32-make`; se o
`make` estiver instalado, ele funciona igual.

Em qualquer passo que der errado: rode `mingw32-make conferir` e mande a
saída, junto com o que apareceu na tela, para o Claude Code nesta pasta. A
conferência não mostra token nem endereço, então dá para colar sem medo.

---

## a. Conferência geral

```bash
mingw32-make conferir
```

**Deve ver:** 11 linhas `OK` e `Resumo: tudo ok`: os 5 containers, os dois
`/health`, a última sync do agendador (hora e quantos itens) e a próxima,
servidor MCP, ngrok e tailscale serve. `AVISO` não impede os passos
seguintes; o aviso diz o que falta.

**Se der errado:**
- `container ...` ou `/health`: `make up` e depois `make logs`.
- `servidor MCP` ou `ngrok`: na pasta `mcp-servidor`, abra o `iniciar-tudo.bat`.
  Se ele já estiver aberto numa janela, feche com Ctrl+C antes.
- `agendador` com `FALHA`: `docker logs casa_agendador --tail 20`.

## b. Painel no celular pelo Tailscale

O `serve` já estava ligado em 05/11; rodar de novo não faz mal.

```bash
tailscale serve --bg --https=443 http://127.0.0.1:5173
tailscale serve status        # mostra o endereço https://<pc>.<tailnet>.ts.net
```

No celular, com o Tailscale conectado na sua conta, abra o endereço com
`/#compras` no fim.

**Deve ver:** a lista de compras sem a pergunta "quem é você?". Para
confirmar, abra `<endereço>/api/compras/eu`: deve aparecer `"quem":"Erik"`,
`"origem":"tailscale"` e `"cadastrado":true`.

**Se der errado:**
- Não abre: confira no app se o Tailscale está conectado e se MagicDNS e
  HTTPS Certificates estão ligados no painel do Tailscale. README,
  "Acessando fora de casa (Tailscale)".
- Pede permissão no Windows: rode o comando num terminal de administrador.
- Pergunta "quem é você?": mande o que o `/api/compras/eu` mostrou.

## c. Convidar a esposa e cadastrar o login dela

Siga o README, "Convidando outra pessoa (lista de compras compartilhada)":
1. Convide pelo painel do Tailscale (Users → Invite users).
2. Ela entra com a conta dela no celular.
3. Copie o e-mail dela da página Users.
4. Cadastre com o `curl` do passo 4 do README, trocando o e-mail e o nome.

**Deve ver:** o `curl` volta 201 com o login e o nome. No celular dela, o
`<endereço>/api/compras/eu` mostra o nome cadastrado e `"cadastrado":true`.

**Se der errado:**
- 409: o login já estava cadastrado. `GET /api/compras/identidades` mostra
  os que existem.
- O celular dela não aparece em Machines: o convite não foi aceito na conta
  certa.

## d. Os dois com a lista aberta

Os dois abrem `<endereço>/#compras`. Um de vocês marca um item como
comprado.

**Deve ver:** no outro celular, o item muda em até uns 3 segundos, sem
recarregar a página (a tela consulta as mudanças a cada 3 s enquanto está
aberta). O item mostra quem pegou.

**Se der errado:** recarregue a página. Se continuar sem atualizar, mande
`mingw32-make conferir` e o que cada celular mostra.

## e. Pela voz no claude.ai

No claude.ai, numa conversa com o conector MCP-Casa ligado:
1. "Põe leite e pão na lista de compras."
2. "O que tem na lista?"
3. "Peguei o leite."

Depois abra o painel em `#compras`.

**Deve ver:**
- O passo 1 responde com uma linha por item, adicionado ou "já estava".
- O passo 2 lista o leite e o pão em "Para pegar", com "· voz".
- O passo 3 confirma o leite como comprado.
- No painel, o pão aparece pendente e o leite comprado, com "voz" como quem
  fez.

**Se der errado:**
- O Claude não acha as ferramentas: desconecte e conecte o conector de novo
  (as descrições mudaram em 05/11).
- A ferramenta responde "Erro": confira as linhas `servidor MCP` e `ngrok`
  do `mingw32-make conferir`.
- Para saber se a chamada chegou ao servidor, rode na pasta `mcp-servidor`:
  `.venv\Scripts\python.exe resumo_log.py`. Ele mostra chamadas e erros por
  ferramenta, sem conteúdo.

## f. Ler uma NFC-e real

Ainda não há tela; use a página da API. Vale só NFC-e do RS (modelo 65).

1. No celular, aponte a câmera para o QR code da nota e copie o link que
   aparece. Sem o QR, use os 44 dígitos da chave de acesso.
2. Abra `<endereço>/api/compras/docs` → `POST /notas` → *Try it out*.
   Preencha `X-Quem` com o seu nome; pelo Tailscale ele é trocado pelo seu
   login de qualquer forma. Envie:
   `{"entrada": "<link do QR ou a chave>"}`.

**Deve ver:** 201 com `"status": "lida"`, o mercado e os itens. Em
`GET /notas/{id}` aparecem os itens, `soma_itens` e `diferenca` (desconto da
nota inteira). Itens que o sistema não reconheceu ficam em
`GET /notas/itens-sem-produto`.

**Se der errado:**
- 422: a entrada não é uma NFC-e válida do RS. Confira se a chave tem os 44
  dígitos ou se copiou o link inteiro.
- 201 com `"status": "erro"`: a página foi guardada inteira, então nada se
  perdeu. Tente `POST /notas/{id}/reler?buscar_de_novo=true`.
- Se continuar com erro, peça ao Claude Code: "extraia a última NFC-e e
  ajuste o leitor" (roteiro em `compras/tests/amostras/README.md`). O leitor
  foi escrito sem nenhuma nota real; esta é a primeira validação dele.
- **Não commite a nota bruta**: o repositório é público. Só a versão
  anonimizada entra em `compras/tests/amostras/`.
