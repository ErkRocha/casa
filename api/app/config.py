"""Configuração por variável de ambiente."""

from functools import lru_cache
from urllib.parse import quote, urlsplit, urlunsplit

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
