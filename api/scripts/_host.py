"""Ambiente para os scripts que rodam no host, fora do container.

O `make relatorio` roda no host porque usa o `claude` logado na máquina, que
não existe dentro da imagem. Lá não há o `DATABASE_URL` que o compose monta
para o container, e o padrão do `Settings` aponta para o host `db`, que só
existe na rede do Docker.

Com Docker como modo principal (D-17), o padrão no host é o banco do compose
pela porta publicada: `127.0.0.1:POSTGRES_PORT`, com as credenciais
`POSTGRES_*` do `.env` da raiz. Quem já exportou `DATABASE_URL` — o modo
local, pelo `source scripts/local/ambiente.sh` — continua mandando.

Tem que rodar **antes** de qualquer `import app.db`: a engine nasce na
importação, com a URL que estiver no ambiente naquele momento.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = RAIZ / ".env"

_OBRIGATORIAS = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


def url_do_host(env: Mapping[str, str | None]) -> str:
    """URL do banco do compose vista do host, pela porta publicada.

    Usuário e senha vão codificados: `@`, `:` e `/` na senha quebrariam a
    URL. A porta padrão é a do compose quando `POSTGRES_PORT` falta.
    """
    faltando = [nome for nome in _OBRIGATORIAS if not env.get(nome)]
    if faltando:
        raise ValueError(
            f"Para montar o DATABASE_URL no host faltam no .env: {', '.join(faltando)}."
        )
    usuario = quote(str(env["POSTGRES_USER"]), safe="")
    senha = quote(str(env["POSTGRES_PASSWORD"]), safe="")
    banco = quote(str(env["POSTGRES_DB"]), safe="")
    porta = env.get("POSTGRES_PORT") or "5432"
    return f"postgresql+psycopg://{usuario}:{senha}@127.0.0.1:{porta}/{banco}"


def preparar_ambiente_host(
    arquivo_env: Path = ARQUIVO_ENV,
    environ: MutableMapping[str, str] | None = None,
) -> str | None:
    """Completa o ambiente do host com o `.env` da raiz.

    Variável já definida no ambiente vence o arquivo, como no compose. Sem
    `DATABASE_URL`, monta a do banco do Docker. Devolve a URL montada, ou
    `None` quando ela já existia.
    """
    alvo = os.environ if environ is None else environ
    arquivo = dotenv_values(arquivo_env) if arquivo_env.exists() else {}
    for chave, valor in arquivo.items():
        if valor is not None and chave not in alvo:
            alvo[chave] = valor

    if alvo.get("DATABASE_URL"):
        return None
    try:
        url = url_do_host(alvo)
    except ValueError as exc:
        raise SystemExit(
            f"{exc} Ou exporte DATABASE_URL (modo local: source scripts/local/ambiente.sh)."
        ) from None
    alvo["DATABASE_URL"] = url
    return url
