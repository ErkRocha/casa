"""O que mudou desde o cursor do celular (api.md, "Como o cursor funciona").

* O cursor é o `now()` do Postgres na leitura, nunca o relógio do celular.
* A consulta volta uma folga (30 s) antes do cursor. `now()` é o início da
  transação: uma escrita que começou antes desta leitura e confirmou depois
  dela tem `atualizado_em` anterior ao cursor, e sem a folga sumiria.
* Repetir linha não faz mal: o celular substitui pela mais nova.
* A linha apagada volta com `deleted_em`, e é assim que a remoção chega ao
  outro celular.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.config import get_settings
from compras.models import Despensa, ItemLista, Produto, Secao


@dataclass
class Mudancas:
    cursor: datetime
    recarregar: bool
    itens: list[ItemLista] = field(default_factory=list)
    despensa: list[Despensa] = field(default_factory=list)
    produtos: list[Produto] = field(default_factory=list)
    secoes: list[Secao] = field(default_factory=list)


def agora(session: Session) -> datetime:
    """O relógio do banco: é ele que carimba `atualizado_em`."""
    # Tipo declarado: no SQLAlchemy 2.1 o `scalar` de uma função devolve Any.
    valor: datetime | None = session.scalar(select(func.now()))
    assert valor is not None
    return valor


def mudancas(session: Session, desde: datetime | None) -> Mudancas:
    cfg = get_settings()
    cursor = agora(session)
    if desde is None or desde < cursor - timedelta(days=cfg.validade_cursor_dias):
        return Mudancas(cursor=cursor, recarregar=True)

    limite = desde - timedelta(seconds=cfg.folga_mudancas_s)

    def depois(modelo: type[ItemLista | Despensa | Produto | Secao]) -> list:  # type: ignore[type-arg]
        return list(
            session.scalars(
                select(modelo)
                .where(modelo.atualizado_em > limite)
                .order_by(modelo.atualizado_em, modelo.id)
            )
        )

    return Mudancas(
        cursor=cursor,
        recarregar=False,
        itens=depois(ItemLista),
        despensa=depois(Despensa),
        produtos=depois(Produto),
        secoes=depois(Secao),
    )
