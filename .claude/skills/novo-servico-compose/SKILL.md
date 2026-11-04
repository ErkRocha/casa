---
name: novo-servico-compose
description: Adiciona um serviço/container novo ao docker-compose do projeto, seguindo o padrão do serviço `compras`. Use quando pedirem "novo serviço", "novo container" ou "adicionar ao compose".
---

Modelo: o serviço `compras` (docker-compose.yml, Makefile, web/nginx). Abaixo `<nome>` e `<NOME>`.

1. Normalmente exige decisão: use a skill nova-decisao antes.
2. docker-compose.yml: serviço com `build.context: ./<nome>`, `image: casa-<nome>:local`, `container_name: casa_<nome>`, `restart: unless-stopped`, porta só em `127.0.0.1:${<NOME>_PORT:-<porta>}:8000`, volume `./<nome>:/app`, `depends_on: db: condition: service_healthy`, `healthcheck` (curl no /health, como o de compras) e `command: uvicorn ...`. Credencial do banco na URL com a role própria, nunca o superusuário.
3. .env.example: adicione `<NOME>_DB_PASSWORD` (só letras, dígitos, - e _) e `<NOME>_PORT`, com comentário no estilo da seção de compras.
4. Banco (D-26): role própria sem superusuário e schema próprio se tiver dados. Crie o serviço `<nome>-role` no compose (perfil `ferramentas`, `restart: "no"`, `command: python -m scripts.aplicar_role`) e o alvo `make <nome>-role`, como `compras-role`.
5. docker-compose.dev.yml: se for Python, repita o `command` com `--reload`.
6. web/nginx/default.conf.template: se o painel ou o mcp-servidor forem consumir, adicione `location /api/<nome>/` (modelo: bloco de compras, com `resolver` e destino em variável) e a variável `<NOME>_UPSTREAM` no `web` do compose. No dev, adicione `<NOME>_PROXY_TARGET` e o proxy em web/vite.config.ts.
7. Makefile: alvos `<nome>-migrate`, `<nome>-test`, `<nome>-lint` copiando os de compras, e inclua-os em `.PHONY`. Seed só se houver.
8. docs/ecossistema.md: tabela de containers, rotas do nginx, quem chama quem e roles. Se o mcp-servidor for consumir, avise o usuário: o repo dele também precisa mudar.
9. Rode `make validar` para confirmar. Não rode `make reset` nem `down -v`.
