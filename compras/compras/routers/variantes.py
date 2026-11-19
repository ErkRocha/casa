"""Variantes: o item exato que se compra (D-33). Reconhecer os itens da nota."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from compras.deps import QuemDep, SessionDep
from compras.models import Variante
from compras.schemas import (
    VarianteAtualizar,
    VarianteCriar,
    VarianteJuntar,
    VarianteLeitura,
)
from compras.services.variantes import VarianteService

router = APIRouter(prefix="/variantes", tags=["variantes"])


def _leitura(servico: VarianteService, variante: Variante) -> VarianteLeitura:
    return servico.leituras([variante])[0]


@router.get("", response_model=list[VarianteLeitura])
def buscar(
    session: SessionDep,
    produto_id: int | None = None,
    gtin: Annotated[str | None, Query(max_length=14)] = None,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    sem_medida: bool | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Para associar: contém o texto no nome da variante, no do produto ou no do
    mercado onde ela tem código. `sem_medida=true` é a fila de variantes sem
    `medida_base` (a pesada já tem: é medida em g)."""
    servico = VarianteService(session)
    return servico.leituras(servico.listar(produto_id, gtin, busca, sem_medida, limite, offset))


@router.post(
    "",
    response_model=VarianteLeitura,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "GTIN repetido: a variante que já o tem vem na resposta"}},
)
def criar(payload: VarianteCriar, session: SessionDep, quem: QuemDep) -> Any:
    servico = VarianteService(session, quem)
    variante = servico.criar(**payload.model_dump())
    session.commit()
    return _leitura(servico, variante)


@router.get("/{id_}", response_model=VarianteLeitura)
def detalhe(id_: int, session: SessionDep) -> Any:
    servico = VarianteService(session)
    return _leitura(servico, servico.get(id_))


@router.patch("/{id_}", response_model=VarianteLeitura)
def atualizar(id_: int, payload: VarianteAtualizar, session: SessionDep, quem: QuemDep) -> Any:
    """Nome, marca, medida, `pesada` e o produto (os itens de nota e os apelidos
    vão junto). É por aqui que se confirma a medida sugerida pela descrição."""
    servico = VarianteService(session, quem)
    variante = servico.atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return _leitura(servico, variante)


@router.delete("/{id_}", response_model=VarianteLeitura)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Soft delete. 409 se há item de nota ligado: junte ou mude o produto."""
    servico = VarianteService(session, quem)
    variante = servico.remover(id_)
    session.commit()
    return _leitura(servico, variante)


@router.post("/{id_}/juntar", response_model=VarianteLeitura)
def juntar(id_: int, payload: VarianteJuntar, session: SessionDep, quem: QuemDep) -> Any:
    """Fica esta; a `outra_id` passa os códigos, apelidos e itens de nota para
    cá e é apagada. Produtos diferentes ou GTINs diferentes: 422. Consigo mesma:
    422."""
    servico = VarianteService(session, quem)
    variante = servico.juntar(id_, payload.outra_id)
    session.commit()
    return _leitura(servico, variante)
