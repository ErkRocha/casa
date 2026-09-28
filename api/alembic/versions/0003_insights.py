"""insights — relatórios gerados

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

Fase 6. A tabela guarda o texto do fechamento do mês **e** os números que o
geraram: sem `dados_base`, um relatório de seis meses atrás vira uma
afirmação sem procedência, impossível de auditar depois que as transações
foram editadas.

Duas colunas além do `docs/modelo-dados.md`:

- `execucao` (jsonb) — telemetria exigida pela D-12: backend, modelo,
  tentativas até validar, duração, tokens. Ficou em jsonb, e não em cinco
  colunas tipadas, porque nada no app filtra por esses valores; eles existem
  para responder "por que este relatório saiu estranho" meses depois, e o
  formato vai mudar quando o backend mudar.
- `periodo_dados` (daterange) — a janela de competências que alimentou o
  texto. O relatório de julho cita a média dos 12 meses anteriores; guardar
  só `competencia` perderia o que "anteriores" queria dizer.

O documento foi atualizado junto desta migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLS = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz,
  deleted_em timestamptz
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE relatorios (
          {_BASE_COLS},
          -- Mês de referência, sempre dia 1º. Em relatório anual, 1º de janeiro.
          competencia date NOT NULL,
          tipo text NOT NULL DEFAULT 'mensal',
          -- Markdown pronto para exibir.
          conteudo text NOT NULL,
          -- Os números que alimentaram o texto, exatamente como o modelo os
          -- recebeu. É o que permite conferir uma afirmação do relatório sem
          -- depender de as transações continuarem intactas.
          dados_base jsonb NOT NULL DEFAULT '{{}}'::jsonb,
          -- Janela de competências considerada. Fechado no início, aberto no
          -- fim: [2025-08-01, 2026-08-01) são os 12 meses até julho.
          periodo_dados daterange,
          -- Arquivo de prompt usado, ex. "relatorio_mensal_v1".
          prompt_versao text NOT NULL,
          -- Telemetria da execução (D-12).
          execucao jsonb NOT NULL DEFAULT '{{}}'::jsonb,

          CONSTRAINT ck_relatorios_tipo_valido
            CHECK (tipo IN ('mensal', 'anual', 'avulso')),
          CONSTRAINT ck_relatorios_competencia_e_dia_primeiro
            CHECK (competencia = date_trunc('month', competencia)::date),
          CONSTRAINT ck_relatorios_conteudo_nao_vazio
            CHECK (length(btrim(conteudo)) > 0)
        )
        """
    )

    # Um relatório vigente por competência e tipo. Regerar o mês não empilha
    # versões visíveis: o service apaga (soft) o anterior e insere o novo, e o
    # histórico continua recuperável por `deleted_em`.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_relatorios_competencia_tipo
        ON relatorios (competencia, tipo)
        WHERE deleted_em IS NULL
        """
    )
    op.execute("CREATE INDEX ix_relatorios_competencia ON relatorios (competencia DESC)")
    op.execute("CREATE INDEX ix_relatorios_deleted_em ON relatorios (deleted_em)")

    op.execute(
        """
        CREATE TRIGGER tg_relatorios_atualizado_em
        BEFORE UPDATE ON relatorios
        FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em()
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_relatorios_auditoria
        AFTER INSERT OR UPDATE OR DELETE ON relatorios
        FOR EACH ROW EXECUTE FUNCTION fn_auditoria()
        """
    )

    # O ALTER DEFAULT PRIVILEGES do `init_roles.sql` já cobriria esta tabela,
    # mas só se a role tiver nascido antes da migration. Num banco que existia
    # desde antes da fase 6 a ordem é a inversa, e o agente ficaria sem
    # enxergar justamente a tabela dele. O GRANT explícito remove a dependência
    # de ordem; o IF EXISTS mantém a migration aplicável onde a role não existe.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'casa_insights') THEN
            GRANT SELECT ON relatorios TO casa_insights;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS relatorios CASCADE")
