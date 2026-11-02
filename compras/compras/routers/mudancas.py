"""O que mudou desde a última consulta: os dois celulares ao mesmo tempo."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query

from compras.deps import SessionDep
from compras.schemas import (
    DespensaLeitura,
    ItemLeitura,
    MudancasResposta,
    ProdutoLeitura,
    SecaoLeitura,
)
from compras.services.mudancas import mudancas

router = APIRouter(tags=["mudanças"])


@router.get("/mudancas", response_model=MudancasResposta)
def listar(
    session: SessionDep,
    desde: Annotated[
        datetime | None,
        Query(description="O `cursor` da resposta anterior (de `/lista` ou daqui)"),
    ] = None,
) -> Any:
    """Linhas inteiras que mudaram desde o cursor, apagadas inclusive.

    Polling a cada 3 s com a tela visível (api.md, recomendação). Volta uma
    folga de 30 s antes do cursor, então linha repetida é normal: substitua
    pela mais nova. Sem cursor, ou com um de mais de 7 dias, `recarregar`
    vem verdadeiro e as listas vazias.
    """
    m = mudancas(session, desde)
    return MudancasResposta(
        cursor=m.cursor,
        recarregar=m.recarregar,
        itens=[ItemLeitura.de(i) for i in m.itens],
        despensa=[DespensaLeitura.de(d) for d in m.despensa],
        produtos=[ProdutoLeitura.de(p) for p in m.produtos],
        secoes=[SecaoLeitura.de(s) for s in m.secoes],
    )
