"""Preços (D-33): histórico por variante, agregados por produto e mercado, e
onde é mais barato. Tudo sai de `vw_preco_variante`."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from compras.deps import SessionDep
from compras.schemas import (
    HistoricoVariante,
    OndeMaisBarato,
    PrecoLinha,
    PrecoMercado,
    PrecoProduto,
)
from compras.services.precos import PrecoService
from compras.services.variantes import VarianteService

router = APIRouter(prefix="/precos", tags=["preços"])


@router.get("", response_model=list[PrecoLinha])
def listar(
    session: SessionDep,
    produto_id: int | None = None,
    mercado_id: int | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Any:
    """Último comparável, mínimo, máximo, média e quantas compras, por produto,
    mercado e medida da variante (`vw_preco_produto`). Compras sem quantidade
    comparável ficam fora das estatísticas e entram em `sem_comparavel`."""
    return PrecoService(session).listar(produto_id, mercado_id, limite)


@router.get("/variantes/{id_}", response_model=HistoricoVariante)
def historico_da_variante(
    id_: int,
    session: SessionDep,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Cada compra da variante: data, mercado, quantidade, preço cheio,
    desconto, preço pago e comparável. Mais recente primeiro, paginado."""
    variante = VarianteService(session).get(id_)
    return PrecoService(session).historico_da_variante(variante, limite, offset)


@router.get("/produtos/{id_}", response_model=PrecoProduto)
def agregado_do_produto(id_: int, session: SessionDep, desde: date | None = None) -> Any:
    """O produto por variante e por mercado (último comparável e a data, mínimo,
    máximo e média) e a variante mais barata de cada unidade."""
    return PrecoService(session).do_produto(id_, desde)


@router.get("/mercados/{id_}", response_model=PrecoMercado)
def do_mercado(
    id_: int,
    session: SessionDep,
    desde: date | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """O que se comprou no mercado: por produto, o último comparável e como ele
    se compara à média dos outros mercados."""
    return PrecoService(session).do_mercado(id_, desde, limite, offset)


@router.get("/onde-mais-barato", response_model=OndeMaisBarato)
def onde_mais_barato(
    session: SessionDep,
    produto_id: int | None = None,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    dias: Annotated[int, Query(ge=1, le=3650)] = 90,
) -> Any:
    """Os mercados pelo **último** comparável do produto em cada um, dentro dos
    últimos `dias` (90). Aceita o nome do produto em `busca` no lugar do id; nome
    que serve a mais de um produto: 409 com os candidatos."""
    if produto_id is None and not (busca or "").strip():
        raise HTTPException(422, "Informe produto_id ou busca.")
    return PrecoService(session).onde_mais_barato(produto_id, busca, dias)
