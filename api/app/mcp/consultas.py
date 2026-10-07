"""Consultas de leitura que o chat precisa e as tools de insights não cobrem.

Mesmas regras de `app/insights/tools.py` (D-10): funções parametrizadas, SQL
fixo com todo parâmetro por bind, nada concatenado a partir da entrada, e
nenhuma soma em Python (regra 7). Rodam sobre a sessão read-only da D-11 —
o servidor MCP não tem outra.

- Soft delete: só linhas vivas. A view `vw_transacoes_completa` já filtra.
- Transferência não é gasto (D-05): os totais a separam, como o resto do
  sistema faz.
- Dinheiro é `Decimal` e sai como texto decimal no JSON (regra 1).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.insights.deteccoes import PROMPT_SEM_IA
from app.models import Relatorio

#: Linhas por chamada de `buscar_transacoes`. Acima disso, a resposta pede
#: paginação: despejar meses de lançamentos no contexto do modelo não ajuda a
#: responder, e convida a somar na mão.
LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200

_COMPETENCIA = re.compile(r"^(\d{4})-(\d{2})(?:-\d{2})?$")


def competencia_de(texto: str) -> date:
    """`2026-07` (ou `2026-07-15`) -> 1º de julho de 2026 (D-02)."""
    casou = _COMPETENCIA.match(texto.strip())
    if not casou:
        raise ValueError(f"Mês inválido: {texto!r}. Use AAAA-MM, por exemplo 2026-07.")
    ano, mes = int(casou.group(1)), int(casou.group(2))
    if not 1 <= mes <= 12:
        raise ValueError(f"Mês inválido: {texto!r}. O mês vai de 01 a 12.")
    return date(ano, mes, 1)


# --- cadastros -----------------------------------------------------------------


class Pessoa(BaseModel):
    id: int
    nome: str
    ativo: bool


class Conta(BaseModel):
    id: int
    nome: str
    tipo: str
    titular: str | None = Field(description="Nulo = conta conjunta.")
    ativo: bool


class FormaPagamento(BaseModel):
    id: int
    apelido: str
    tipo: str
    conta_id: int | None
    conta: str | None
    ativo: bool


class Categoria(BaseModel):
    id: int
    nome: str
    tipo: str
    categoria_pai_id: int | None
    caminho: str = Field(description="'Pai › Filha' para subcategoria; o nome, para raiz.")
    ativo: bool


class Cadastros(BaseModel):
    pessoas: list[Pessoa]
    contas: list[Conta]
    formas_pagamento: list[FormaPagamento]
    categorias: list[Categoria]


def listar_cadastros(sessao: Session) -> Cadastros:
    """Nomes e ids válidos, para o modelo montar os filtros das outras tools."""
    pessoas = sessao.execute(
        text("SELECT id, nome, ativo FROM pessoas WHERE deleted_em IS NULL ORDER BY id")
    ).mappings()
    contas = sessao.execute(
        text("""
            SELECT c.id, c.nome, c.tipo::text AS tipo, p.nome AS titular, c.ativo
            FROM contas c
            LEFT JOIN pessoas p ON p.id = c.titular_id
            WHERE c.deleted_em IS NULL
            ORDER BY c.id
        """)
    ).mappings()
    formas = sessao.execute(
        text("""
            SELECT f.id, f.apelido, f.tipo::text AS tipo, f.conta_id, c.nome AS conta, f.ativo
            FROM formas_pagamento f
            LEFT JOIN contas c ON c.id = f.conta_id
            WHERE f.deleted_em IS NULL
            ORDER BY f.id
        """)
    ).mappings()
    categorias = sessao.execute(
        text("""
            SELECT c.id, c.nome, c.tipo::text AS tipo, c.categoria_pai_id, c.ativo,
                   CASE WHEN pai.id IS NULL THEN c.nome
                        ELSE pai.nome || ' › ' || c.nome END AS caminho
            FROM categorias c
            LEFT JOIN categorias pai ON pai.id = c.categoria_pai_id
            WHERE c.deleted_em IS NULL
            ORDER BY coalesce(pai.nome, c.nome), c.categoria_pai_id NULLS FIRST, c.nome
        """)
    ).mappings()
    return Cadastros(
        pessoas=[Pessoa(**dict(r)) for r in pessoas],
        contas=[Conta(**dict(r)) for r in contas],
        formas_pagamento=[FormaPagamento(**dict(r)) for r in formas],
        categorias=[Categoria(**dict(r)) for r in categorias],
    )


# --- transações -------------------------------------------------------------------


class FiltroTransacoes(BaseModel):
    """Filtros combinados com E. Todos opcionais."""

    data_inicio: date | None = None
    data_fim: date | None = None
    competencia: date | None = None
    categoria_id: int | None = None
    pessoa_id: int | None = None
    so_conjunto: bool = False
    conta_id: int | None = None
    texto: str | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    tipo: TipoTransacao | None = None


def _onde(filtro: FiltroTransacoes) -> tuple[str, dict[str, Any]]:
    """A cláusula WHERE: fragmentos fixos, valores só por bind."""
    partes: list[str] = []
    binds: dict[str, Any] = {}

    def usar(fragmento: str, **valores: Any) -> None:
        partes.append(fragmento)
        binds.update(valores)

    if filtro.data_inicio:
        usar("v.data >= :data_inicio", data_inicio=filtro.data_inicio)
    if filtro.data_fim:
        usar("v.data <= :data_fim", data_fim=filtro.data_fim)
    if filtro.competencia:
        usar("v.competencia = :competencia", competencia=filtro.competencia)
    if filtro.categoria_id is not None:
        # Categoria raiz traz as subcategorias junto.
        usar(
            "(v.categoria_id = :categoria_id OR v.categoria_raiz_id = :categoria_id)",
            categoria_id=filtro.categoria_id,
        )
    if filtro.so_conjunto:
        usar("v.pessoa_id IS NULL")
    elif filtro.pessoa_id is not None:
        usar("v.pessoa_id = :pessoa_id", pessoa_id=filtro.pessoa_id)
    if filtro.conta_id is not None:
        # A importação não preenche `conta_id`: a conta sai da forma de
        # pagamento. Transferência entra pela origem ou pelo destino.
        usar(
            "(v.conta_id = :conta_id OR fp.conta_id = :conta_id"
            " OR v.conta_origem_id = :conta_id OR v.conta_destino_id = :conta_id)",
            conta_id=filtro.conta_id,
        )
    if filtro.texto:
        # `position` em vez de LIKE: o texto do usuário não vira padrão.
        usar(
            "position(lower(:texto) IN lower(coalesce(v.descricao, '') || ' ' ||"
            " coalesce(v.descricao_original, ''))) > 0",
            texto=filtro.texto.strip(),
        )
    if filtro.valor_min is not None:
        usar("v.valor >= :valor_min", valor_min=filtro.valor_min)
    if filtro.valor_max is not None:
        usar("v.valor <= :valor_max", valor_max=filtro.valor_max)
    if filtro.tipo is not None:
        usar("v.tipo::text = :tipo", tipo=filtro.tipo.value)

    return (" AND ".join(partes) or "TRUE"), binds


_DE = """
    FROM vw_transacoes_completa v
    LEFT JOIN formas_pagamento fp ON fp.id = v.forma_pagamento_id
"""


class Transacao(BaseModel):
    id: int
    data: date
    competencia: date
    valor: Decimal = Field(description="Sempre positivo; o sentido está em `tipo`.")
    tipo: str
    descricao: str
    categoria: str | None
    pessoa: str = Field(description="Nome da pessoa, ou 'Conjunto'.")
    forma_pagamento: str | None
    parcela: str | None = Field(description="'3/12' quando é parcela.")


class ResultadoBusca(BaseModel):
    transacoes: list[Transacao]
    total_encontrado: int
    retornadas: int
    ha_mais: bool = Field(description="Há mais resultados além desta página.")
    proximo_offset: int | None = Field(description="O offset da próxima página, se houver.")


def buscar_transacoes(
    sessao: Session,
    filtro: FiltroTransacoes,
    limite: int = LIMITE_PADRAO,
    offset: int = 0,
) -> ResultadoBusca:
    """Lançamentos que casam com o filtro, mais recentes primeiro."""
    limite = max(1, min(limite, LIMITE_MAXIMO))
    offset = max(0, offset)
    onde, binds = _onde(filtro)

    total = int(sessao.execute(text(f"SELECT count(*) {_DE} WHERE {onde}"), binds).scalar_one())
    linhas = sessao.execute(
        text(f"""
            SELECT v.id, v.data, v.competencia, v.valor, v.tipo::text AS tipo,
                   v.descricao, v.categoria_caminho AS categoria,
                   coalesce(v.pessoa_nome, 'Conjunto') AS pessoa,
                   v.forma_pagamento_apelido AS forma_pagamento,
                   CASE WHEN v.parcela_num IS NOT NULL
                        THEN v.parcela_num || '/' || v.parcela_total END AS parcela
            {_DE}
            WHERE {onde}
            ORDER BY v.data DESC, v.id DESC
            LIMIT :limite OFFSET :offset
        """),
        binds | {"limite": limite, "offset": offset},
    ).mappings()
    transacoes = [Transacao(**dict(r)) for r in linhas]

    proximo = offset + len(transacoes)
    ha_mais = proximo < total
    return ResultadoBusca(
        transacoes=transacoes,
        total_encontrado=total,
        retornadas=len(transacoes),
        ha_mais=ha_mais,
        proximo_offset=proximo if ha_mais else None,
    )


class Totais(BaseModel):
    """Somas feitas pelo Postgres sobre os mesmos filtros da busca."""

    despesas: Decimal
    quantidade_despesas: int
    receitas: Decimal
    quantidade_receitas: int
    saldo: Decimal = Field(description="Receitas menos despesas.")
    transferencias: Decimal = Field(
        description="Movimentação entre contas próprias: fica fora de despesa e receita (D-05)."
    )
    quantidade_transferencias: int


def totalizar_transacoes(sessao: Session, filtro: FiltroTransacoes) -> Totais:
    """Soma, no banco, despesas e receitas que casam com o filtro."""
    onde, binds = _onde(filtro)
    r = (
        sessao.execute(
            text(f"""
                SELECT
                  coalesce(sum(v.valor) FILTER (WHERE v.tipo = 'despesa'), 0)::numeric(14, 2)
                    AS despesas,
                  count(*) FILTER (WHERE v.tipo = 'despesa') AS quantidade_despesas,
                  coalesce(sum(v.valor) FILTER (WHERE v.tipo = 'receita'), 0)::numeric(14, 2)
                    AS receitas,
                  count(*) FILTER (WHERE v.tipo = 'receita') AS quantidade_receitas,
                  (coalesce(sum(v.valor) FILTER (WHERE v.tipo = 'receita'), 0)
                    - coalesce(sum(v.valor) FILTER (WHERE v.tipo = 'despesa'), 0)
                  )::numeric(14, 2) AS saldo,
                  coalesce(sum(v.valor) FILTER (WHERE v.tipo = 'transferencia'), 0)::numeric(14, 2)
                    AS transferencias,
                  count(*) FILTER (WHERE v.tipo = 'transferencia') AS quantidade_transferencias
                {_DE}
                WHERE {onde}
            """),
            binds,
        )
        .mappings()
        .one()
    )
    return Totais(**dict(r))


# --- relatório salvo -------------------------------------------------------------


class RelatorioLido(BaseModel):
    competencia: date
    tipo: str
    com_ia: bool = Field(description="Escrito por modelo; falso = só dos números.")
    prompt_versao: str
    gerado_em: datetime
    conteudo: str = Field(description="Markdown do relatório.")


def ler_relatorio(sessao: Session, competencia: date, tipo: str = "mensal") -> RelatorioLido | None:
    """O relatório vigente do mês, se já foi gerado."""
    r = sessao.scalar(
        select(Relatorio).where(
            Relatorio.deleted_em.is_(None),
            Relatorio.competencia == competencia,
            Relatorio.tipo == tipo,
        )
    )
    if r is None:
        return None
    return RelatorioLido(
        competencia=r.competencia,
        tipo=r.tipo,
        com_ia=r.prompt_versao != PROMPT_SEM_IA,
        prompt_versao=r.prompt_versao,
        gerado_em=r.criado_em,
        conteudo=r.conteudo,
    )
