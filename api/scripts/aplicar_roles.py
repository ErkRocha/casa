"""Cria (ou repara) a role read-only do agente de insights e prova que ela é read-only.

    python -m scripts.aplicar_roles

Idempotente: pode rodar quantas vezes quiser. O que ele faz:

1. executa `init_roles.sql` com a credencial dona do banco;
2. troca a senha da role pela de `INSIGHTS_PASSWORD`;
3. **conecta como a role e tenta escrever.** Se a escrita passar, o script
   falha — a D-11 diz que a impossibilidade de corromper dados é estrutural,
   e garantia que ninguém verifica não é garantia, é intenção.

Por que existe um script em vez de só o entrypoint do Docker: o
`init_roles.sql` só roda no *primeiro* boot do volume. Quem já tinha o banco
de pé antes da fase 6 — ou subiu o Postgres à mão, sem Docker — nunca viu
esse arquivo rodar. O sintoma seria a role simplesmente não existir na hora
de gerar o primeiro relatório.
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import sql as pgsql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from app.config import get_settings

SQL = Path(__file__).resolve().parent / "init_roles.sql"

#: Escrita de mentira usada para provar que a role não escreve. Roda dentro de
#: uma transação que sempre sofre rollback — mas nem chega lá: o Postgres
#: recusa antes, e é justamente isso que estamos verificando.
SONDA_DE_ESCRITA = "INSERT INTO pessoas (nome) VALUES ('sonda_readonly')"

#: `42501 insufficient_privilege` — o código que o Postgres devolve quando a
#: permissão falta. Conferir o código, e não o texto, porque a mensagem muda
#: com o idioma do servidor.
PRIVILEGIO_INSUFICIENTE = "42501"


def aplicar(url_dono: str, senha: str, role: str) -> None:
    engine = create_engine(url_dono, pool_pre_ping=True)
    with engine.begin() as conexao:
        # `exec_driver_sql` sem parâmetro: o arquivo tem `$$ ... $$`, que o
        # `text()` do SQLAlchemy leria como bindparam.
        conexao.exec_driver_sql(SQL.read_text(encoding="utf-8"))

        # ALTER ROLE é DDL, e DDL no Postgres não aceita bind parameter — a
        # senha precisa ir literal na string. Interpolar à mão seria injeção
        # esperando acontecer, então quem monta é o `sql` do psycopg, que
        # escapa identificador e literal pelas regras do servidor.
        bruta = conexao.connection.dbapi_connection
        comando = pgsql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
            pgsql.Identifier(role), pgsql.Literal(senha)
        )
        with bruta.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(comando)
    engine.dispose()


def verificar(url_role: str) -> tuple[int, str]:
    """Conecta como a role e confirma: lê tudo, não escreve nada.

    Devolve quantas tabelas ela enxerga, para o caso de os GRANTs terem
    passado mas alcançado zero objetos — que é um jeito silencioso de a fase 6
    nascer quebrada.
    """
    engine = create_engine(url_role, pool_pre_ping=True)
    try:
        with engine.connect() as conexao:
            legiveis = conexao.execute(
                text("""
                    SELECT count(*)
                    FROM information_schema.table_privileges
                    WHERE grantee = current_user AND privilege_type = 'SELECT'
                """)
            ).scalar_one()

            escrevveis = conexao.execute(
                text("""
                    SELECT count(*)
                    FROM information_schema.table_privileges
                    WHERE grantee = current_user
                      AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                """)
            ).scalar_one()
            if escrevveis:
                raise SystemExit(
                    f"ABORTADO: a role tem {escrevveis} permissão(ões) de escrita. "
                    "Revogue antes de usar — a D-11 exige leitura pura."
                )

            usuario = str(conexao.execute(text("SELECT current_user")).scalar_one())

            # A prova de fogo: a permissão declarada e o comportamento real
            # podem divergir (herança de role, GRANT em PUBLIC). Só tentando.
            #
            # O rollback no `finally` não é zelo: as leituras acima já abriram
            # transação implícita, e a sonda a deixa abortada. Sem limpar, a
            # própria consulta seguinte morreria com "current transaction is
            # aborted" e o script culparia a permissão errada.
            try:
                conexao.execute(text(SONDA_DE_ESCRITA))
            except ProgrammingError as erro:
                codigo = getattr(erro.orig, "sqlstate", None)
                if codigo != PRIVILEGIO_INSUFICIENTE:
                    raise SystemExit(
                        f"ABORTADO: a escrita falhou por {codigo}, não por falta de "
                        f"permissão. Erro real: {erro.orig}"
                    ) from erro
            else:
                raise SystemExit(
                    "ABORTADO: a role conseguiu inserir em `pessoas`. Ela NÃO é "
                    "read-only e não pode ser usada pelo agente de insights."
                )
            finally:
                conexao.rollback()

            return int(legiveis), usuario
    finally:
        engine.dispose()


def main() -> int:
    cfg = get_settings()

    if cfg.insights_password == "trocar_no_primeiro_uso":
        print(
            "AVISO: INSIGHTS_PASSWORD está no valor de exemplo. Defina uma senha "
            "própria no .env antes de usar fora da sua máquina.",
            file=sys.stderr,
        )

    aplicar(cfg.database_url, cfg.insights_password, cfg.insights_role)
    legiveis, usuario = verificar(cfg.insights_database_url)

    print(f"role `{usuario}` pronta: {legiveis} objeto(s) legível(is), 0 de escrita.")
    print("Escrita testada e recusada pelo Postgres (42501). D-11 satisfeita.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
