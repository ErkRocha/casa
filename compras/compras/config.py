"""Configuração por variável de ambiente, toda com prefixo `COMPRAS_`.

O prefixo não é enfeite: no modo local o mesmo terminal exporta a
`DATABASE_URL` de finanças, e este serviço não pode pegá-la por engano. Ele
conecta só com a role `casa_compras` (D-25).
"""

from functools import lru_cache
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Segundos até desistir de conectar ao banco, como em finanças.
CONNECT_TIMEOUT_S = 5

#: Role dona do schema `compras`. Fixa: o trigger que recusa escrita de
#: outras roles (migration 0001) compara com este nome.
ROLE = "casa_compras"
SCHEMA = "compras"


def com_connect_timeout(url: str, segundos: int = CONNECT_TIMEOUT_S) -> str:
    """A URL com `connect_timeout`, sem duplicar se já houver."""
    partes = urlsplit(url)
    parametros = parse_qsl(partes.query, keep_blank_values=True)
    if any(chave == "connect_timeout" for chave, _ in parametros):
        return url
    parametros.append(("connect_timeout", str(segundos)))
    return urlunsplit(partes._replace(query=urlencode(parametros)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMPRAS_", env_file=".env", extra="ignore")

    #: Sempre com a role `casa_compras`. `COMPRAS_DATABASE_URL`.
    database_url: str = "postgresql+psycopg://casa_compras:casa_compras@db:5432/casa"

    #: Prefixo atrás do nginx (`/api/compras`); vazio no acesso direto.
    root_path: str = ""

    #: Autor gravado na auditoria quando a requisição não traz `X-Quem`
    #: (leituras, e o seed).
    autor_padrao: str = "compras"

    #: Folga do `GET /mudancas` (api.md, "Como o cursor funciona").
    folga_mudancas_s: int = 30

    #: Cursor mais velho que isto pede recarga inteira.
    validade_cursor_dias: int = 7

    #: Comprados que o `GET /lista` mostra quando o celular não diz desde quando.
    comprados_recentes_h: int = 6

    #: A API de finanças, para sugerir a transação de uma nota (só leitura,
    #: por HTTP; D-25). No compose, o serviço `api`; no modo local, a porta
    #: dela. `COMPRAS_FINANCAS_URL`.
    financas_url: str = "http://api:8000"

    #: Segundos até desistir da consulta pública da SEFAZ.
    sefaz_tempo_limite_s: float = 20.0

    @field_validator("database_url", mode="after")
    @classmethod
    def _com_timeout(cls, valor: str) -> str:
        return com_connect_timeout(valor)


def url_com_role(url: str, senha: str, role: str = ROLE) -> str:
    """A mesma URL (host, porta, banco) com a credencial da role trocada."""
    partes = urlsplit(url)
    hospedeiro = partes.hostname or "localhost"
    if partes.port:
        hospedeiro = f"{hospedeiro}:{partes.port}"
    credencial = f"{role}:{quote(senha, safe='')}"
    return urlunsplit((partes.scheme, f"{credencial}@{hospedeiro}", partes.path, partes.query, ""))


def url_para_alembic(url: str) -> str:
    """Escapa o `%` da senha codificada para o `configparser` do Alembic."""
    return url.replace("%", "%%")


@lru_cache
def get_settings() -> Settings:
    return Settings()
