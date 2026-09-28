"""Declaração Core das views de leitura.

As views são criadas por SQL na migration; aqui só descrevemos as colunas para
poder montar `select()` com filtro dinâmico em cima delas. Ficam fora do
`Base.metadata` de propósito — senão o autogenerate do Alembic tentaria criar
tabela com esses nomes.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
)

from app.db import pg_enum
from app.enums import TipoPagamento, TipoTransacao

views_metadata = MetaData()

vw_transacoes_completa = Table(
    "vw_transacoes_completa",
    views_metadata,
    Column("id", BigInteger),
    Column("data", Date),
    Column("competencia", Date),
    Column("valor", Numeric(12, 2)),
    # Enum nativo, não Text: `tipo_transacao = varchar` não tem operador no
    # Postgres e o filtro estoura em runtime.
    Column("tipo", pg_enum(TipoTransacao, "tipo_transacao")),
    Column("descricao", Text),
    Column("descricao_original", Text),
    Column("observacao", Text),
    Column("parcela_num", SmallInteger),
    Column("parcela_total", SmallInteger),
    Column("desconto_total", Numeric(12, 2)),
    Column("criado_em", DateTime(timezone=True)),
    Column("atualizado_em", DateTime(timezone=True)),
    Column("pessoa_id", BigInteger),
    Column("pessoa_nome", Text),
    Column("categoria_id", BigInteger),
    Column("categoria_nome", Text),
    Column("categoria_pai_id", BigInteger),
    Column("categoria_pai_nome", Text),
    Column("categoria_caminho", Text),
    Column("categoria_raiz_id", BigInteger),
    Column("forma_pagamento_id", BigInteger),
    Column("forma_pagamento_apelido", Text),
    Column("forma_pagamento_tipo", pg_enum(TipoPagamento, "tipo_pagamento")),
    Column("local_id", BigInteger),
    Column("local_nome", Text),
    Column("conta_id", BigInteger),
    Column("conta_origem_id", BigInteger),
    Column("conta_destino_id", BigInteger),
    # Origem: de qual arquivo importado a linha nasceu (migration 0004).
    Column("importacao_id", BigInteger),
    Column("importacao_arquivo", Text),
    Column("importacao_em", DateTime(timezone=True)),
    Column("importacao_tem_arquivo", Boolean),
)

vw_gasto_por_pessoa = Table(
    "vw_gasto_por_pessoa",
    views_metadata,
    Column("competencia", Date),
    Column("balde", Text),
    Column("balde_nome", Text),
    Column("total", Numeric(12, 2)),
)

vw_orcamento_mes = Table(
    "vw_orcamento_mes",
    views_metadata,
    Column("orcamento_id", BigInteger),
    Column("competencia", Date),
    Column("categoria_id", BigInteger),
    Column("categoria_nome", Text),
    Column("valor_meta", Numeric(12, 2)),
    Column("realizado", Numeric(12, 2)),
    Column("percentual", Numeric(12, 2)),
)

__all__ = [
    "views_metadata",
    "vw_gasto_por_pessoa",
    "vw_orcamento_mes",
    "vw_transacoes_completa",
]
