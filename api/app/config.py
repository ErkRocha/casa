"""Configuração por variável de ambiente."""

from functools import lru_cache
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Segundos até desistir de conectar ao banco. Sem isto, banco fora do ar (o
#: Docker parado, a porta fechada) prendia a API e os scripts por minutos, em
#: vez de falhar com erro claro.
CONNECT_TIMEOUT_S = 5


def com_connect_timeout(url: str, segundos: int = CONNECT_TIMEOUT_S) -> str:
    """A URL do banco com `connect_timeout`, sem duplicar se já houver.

    Mexe só na query string: usuário, senha codificada, host e banco ficam
    como vieram. Um `connect_timeout` que já esteja na URL é respeitado.
    """
    partes = urlsplit(url)
    parametros = parse_qsl(partes.query, keep_blank_values=True)
    if any(chave == "connect_timeout" for chave, _ in parametros):
        return url
    parametros.append(("connect_timeout", str(segundos)))
    return urlunsplit(partes._replace(query=urlencode(parametros)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://casa:casa@db:5432/casa"
    app_env: str = "dev"

    #: Gravado em `auditoria.autor` quando a escrita vem do painel. Agentes
    #: sobrescrevem por sessão via `SET LOCAL app.autor`.
    app_autor_padrao: str = "usuario"

    #: Prefixo sob o qual a API é servida atrás de um proxy (D-19). No compose
    #: é `/api`: o nginx do painel repassa `/api/...` tirando o prefixo, e com
    #: isto o `/docs` monta os links em `/api/...` e funciona em `/api/docs`
    #: pelo painel. Vazio no acesso direto (`127.0.0.1:8000`, modo local).
    api_root_path: str = ""

    #: Origens liberadas no CORS. Desde a D-18 o painel chama a API por `/api`
    #: na mesma origem (o servidor do front repassa), e o CORS não entra no uso
    #: normal. Fica para quem apontar `VITE_API_URL` direto para a API.
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

    @field_validator("database_url", "insights_database_url_override", mode="after")
    @classmethod
    def _com_timeout(cls, valor: str | None) -> str | None:
        """Toda URL de banco do projeto passa por aqui: API, scripts, sync,
        relatório, Alembic e testes. A do insights deriva desta e herda."""
        return com_connect_timeout(valor) if valor else valor

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
