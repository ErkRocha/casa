"""Configuração por variável de ambiente."""

from functools import lru_cache
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://casa:casa@db:5432/casa"
    app_env: str = "dev"

    #: Gravado em `auditoria.autor` quando a escrita vem do painel. Agentes
    #: sobrescrevem por sessão via `SET LOCAL app.autor`.
    app_autor_padrao: str = "usuario"

    #: Origens liberadas no CORS. O front roda no host, a API no container.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    #: Teto de itens por página. Toda listagem é paginada.
    page_size_max: int = 200
    page_size_default: int = 50

    # --- Insights (fase 6) --------------------------------------------------

    #: Senha da role read-only. A role em si nasce no `init_roles.sql`.
    insights_password: str = "trocar_no_primeiro_uso"
    insights_role: str = "casa_insights"

    #: Só preencha para apontar o agente para outro host. Por padrão é a mesma
    #: URL do banco com credencial trocada — mesmo banco, permissão menor.
    insights_database_url_override: str | None = None

    #: Como o relatório mensal chama o modelo:
    #:   `claude_code` — CLI local, usa a assinatura, sem chave de API;
    #:   `api`         — SDK da Anthropic, exige ANTHROPIC_API_KEY.
    insights_backend: str = "claude_code"
    insights_modelo: str = "claude-opus-4-8"

    #: Teto de tentativas do harness quando a saída não valida (D-12).
    insights_tentativas_max: int = 3

    # --- Pluggy (fase 5b, D-16) ---------------------------------------------

    #: Credenciais da aplicação na Pluggy. Opcionais: sem as duas, a sync fica
    #: desligada e o resto do sistema não percebe diferença.
    pluggy_client_id: str | None = None
    #: `SecretStr` para não vazar em `repr`, log ou traceback de validação —
    #: o valor só sai por `.get_secret_value()`, e só o cliente HTTP chama.
    pluggy_client_secret: SecretStr | None = None

    @field_validator("pluggy_client_id", "pluggy_client_secret", mode="before")
    @classmethod
    def _vazio_e_ausente(cls, valor: object) -> object:
        """`""` conta como ausente.

        O compose repassa `${PLUGGY_CLIENT_ID:-}`, que chega como string vazia
        quando a variável não existe no `.env`. Sem isto, "vazio" ligaria a
        sync com credencial em branco e o erro só apareceria no `POST /auth`.
        """
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @property
    def pluggy_habilitada(self) -> bool:
        return self.pluggy_client_id is not None and self.pluggy_client_secret is not None

    @property
    def insights_database_url(self) -> str:
        """A URL do banco com a credencial read-only.

        Derivada em vez de configurada à parte porque as duas apontam
        obrigatoriamente para o mesmo banco: uma URL solta convidaria a
        divergência silenciosa entre o que o painel lê e o que o agente lê.
        """
        if self.insights_database_url_override:
            return self.insights_database_url_override

        partes = urlsplit(self.database_url)
        hospedeiro = partes.hostname or "localhost"
        if partes.port:
            hospedeiro = f"{hospedeiro}:{partes.port}"
        # `quote` porque senha com `@` ou `/` quebraria o parse da URL.
        credencial = f"{self.insights_role}:{quote(self.insights_password, safe='')}"
        return urlunsplit(
            (partes.scheme, f"{credencial}@{hospedeiro}", partes.path, partes.query, "")
        )


def url_para_alembic(url: str) -> str:
    """A URL do banco pronta para `Config.set_main_option` do Alembic.

    O Alembic guarda a opção num `configparser`, que lê `%` como início de
    interpolação. Senha com `@`, `:` ou `/` chega aqui codificada (`%40`,
    `%3A`), e sem o escape a migration morria antes de conectar.
    """
    return url.replace("%", "%%")


@lru_cache
def get_settings() -> Settings:
    return Settings()
