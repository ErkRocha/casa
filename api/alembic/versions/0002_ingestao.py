"""ingestão — staging e regras de categorização

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09

Fase 5, passo 1. Nada aqui afeta relatório: `importacao_itens` é área de
espera. O agente escreve nela; quem promove para `transacoes` é o usuário,
pelo painel (D-07).

Três colunas de `importacao_itens` não estão em `docs/modelo-dados.md`:
`tipo_sugerido`, `competencia_sugerida` e `forma_pagamento_sugerida_id`. Sem
elas é impossível promover um item — `transacoes` exige tipo e competência, e
a forma de pagamento é o que distingue compra no cartão de débito em conta. O
documento foi atualizado junto desta migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLS = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz,
  deleted_em timestamptz
"""

_TABELAS_AUDITADAS = ("importacoes", "importacao_itens", "regras_categorizacao")


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE importacoes (
          {_BASE_COLS},
          arquivo_nome text NOT NULL,
          -- SHA-256 do arquivo. Barra reimportação do mesmo PDF (D-07).
          hash_arquivo text NOT NULL,
          -- "nubank_fatura", "nubank_extrato"
          origem text,
          periodo_inicio date,
          periodo_fim date,
          status status_importacao NOT NULL DEFAULT 'processando',
          -- "deterministico" ou "llm"
          parser_usado text,
          -- Versão do prompt, quando o LLM entrar (D-12). Nulo no parser
          -- determinístico.
          prompt_versao text,
          total_itens int NOT NULL DEFAULT 0,
          itens_aprovados int NOT NULL DEFAULT 0,
          -- {{entrada, saida, custo_estimado}}
          custo_tokens jsonb,
          -- Total declarado pelo próprio documento, quando ele diz. É o
          -- gabarito que permite conferir a extração sem confiar nela.
          total_declarado numeric(12, 2),
          erro_mensagem text,
          CONSTRAINT ck_importacoes_periodo_coerente
            CHECK (periodo_inicio IS NULL OR periodo_fim IS NULL OR periodo_inicio <= periodo_fim)
        )
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_importacoes_hash_arquivo ON importacoes (hash_arquivo)
        WHERE deleted_em IS NULL
        """
    )
    op.execute("CREATE INDEX ix_importacoes_status ON importacoes (status)")
    op.execute("CREATE INDEX ix_importacoes_deleted_em ON importacoes (deleted_em)")

    op.execute(
        f"""
        CREATE TABLE importacao_itens (
          {_BASE_COLS},
          importacao_id bigint NOT NULL REFERENCES importacoes (id) ON DELETE CASCADE,
          -- A linha exata do PDF, para conferir contra o documento.
          linha_bruta text NOT NULL,
          -- Ordem em que a linha apareceu no arquivo.
          linha_num int,

          data date,
          valor numeric(12, 2),
          descricao_original text,

          -- Sugestões. Todas anuláveis: o parser preenche o que consegue e o
          -- usuário resolve o resto na tela de revisão.
          tipo_sugerido tipo_transacao,
          competencia_sugerida date,
          categoria_sugerida_id bigint REFERENCES categorias (id) ON DELETE SET NULL,
          local_sugerido_id bigint REFERENCES locais (id) ON DELETE SET NULL,
          pessoa_sugerida_id bigint REFERENCES pessoas (id) ON DELETE SET NULL,
          forma_pagamento_sugerida_id bigint REFERENCES formas_pagamento (id) ON DELETE SET NULL,

          confianca numeric(3, 2),
          -- "regra" | "alias" | "llm" | "parser"
          origem_sugestao text,

          status status_item NOT NULL DEFAULT 'pendente',
          -- Preenchido ao aprovar. É o elo entre staging e o dado real.
          transacao_id bigint REFERENCES transacoes (id) ON DELETE SET NULL,
          motivo_rejeicao text,

          CONSTRAINT ck_importacao_itens_confianca_valida
            CHECK (confianca IS NULL OR confianca BETWEEN 0 AND 1),
          CONSTRAINT ck_importacao_itens_valor_positivo
            CHECK (valor IS NULL OR valor > 0),
          -- Item aprovado tem que apontar para a transação que gerou; item
          -- não aprovado não pode apontar para nenhuma.
          CONSTRAINT ck_importacao_itens_aprovado_tem_transacao CHECK (
            (status = 'aprovado' AND transacao_id IS NOT NULL)
            OR (status <> 'aprovado' AND transacao_id IS NULL)
          )
        )
        """
    )

    op.execute("CREATE INDEX ix_importacao_itens_importacao_id ON importacao_itens (importacao_id)")
    op.execute("CREATE INDEX ix_importacao_itens_status ON importacao_itens (status)")
    op.execute("CREATE INDEX ix_importacao_itens_deleted_em ON importacao_itens (deleted_em)")

    # A FK que faltava: `transacoes.importacao_id` nasceu na 0001 sem destino,
    # porque `importacoes` só existe agora.
    op.execute(
        """
        ALTER TABLE transacoes
        ADD CONSTRAINT fk_transacoes_importacao_id
        FOREIGN KEY (importacao_id) REFERENCES importacoes (id) ON DELETE SET NULL
        """
    )
    op.execute("CREATE INDEX ix_transacoes_importacao_id ON transacoes (importacao_id)")

    op.execute(
        f"""
        CREATE TABLE regras_categorizacao (
          {_BASE_COLS},
          -- Texto ou regex, conforme `tipo_match`.
          padrao text NOT NULL,
          tipo_match text NOT NULL DEFAULT 'contem',
          -- O que aplicar quando o padrão casar. Pelo menos um preenchido.
          categoria_id bigint REFERENCES categorias (id) ON DELETE CASCADE,
          local_id bigint REFERENCES locais (id) ON DELETE CASCADE,
          pessoa_id bigint REFERENCES pessoas (id) ON DELETE CASCADE,
          -- Menor roda primeiro.
          prioridade int NOT NULL DEFAULT 100,
          -- "usuario" | "correcao_automatica"
          criada_por text NOT NULL DEFAULT 'usuario',
          -- Quantas vezes a regra já acertou. Correção do usuário reforça
          -- em vez de criar duplicata (D-09).
          acertos int NOT NULL DEFAULT 0,
          ativo boolean NOT NULL DEFAULT true,

          CONSTRAINT ck_regras_categorizacao_tipo_match_valido
            CHECK (tipo_match IN ('contem', 'regex', 'exato')),
          CONSTRAINT ck_regras_categorizacao_faz_alguma_coisa CHECK (
            categoria_id IS NOT NULL OR local_id IS NOT NULL OR pessoa_id IS NOT NULL
          )
        )
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_regras_categorizacao_padrao
        ON regras_categorizacao (lower(padrao), tipo_match)
        WHERE deleted_em IS NULL
        """
    )
    op.execute(
        "CREATE INDEX ix_regras_categorizacao_prioridade ON regras_categorizacao (prioridade)"
    )
    op.execute(
        "CREATE INDEX ix_regras_categorizacao_deleted_em ON regras_categorizacao (deleted_em)"
    )

    for tabela in _TABELAS_AUDITADAS:
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_atualizado_em
            BEFORE UPDATE ON {tabela}
            FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_auditoria
            AFTER INSERT OR UPDATE OR DELETE ON {tabela}
            FOR EACH ROW EXECUTE FUNCTION fn_auditoria()
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transacoes_importacao_id")
    op.execute("ALTER TABLE transacoes DROP CONSTRAINT IF EXISTS fk_transacoes_importacao_id")
    for tabela in ("regras_categorizacao", "importacao_itens", "importacoes"):
        op.execute(f"DROP TABLE IF EXISTS {tabela} CASCADE")
