"""Aplicação FastAPI do serviço `compras` (D-25)."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from compras.config import get_settings
from compras.db import engine
from compras.financas import FinancasIndisponivel
from compras.routers import (
    despensa,
    identidades,
    lista,
    mercados,
    mudancas,
    notas,
    precos,
    produtos,
    secoes,
)
from compras.services.base import Conflito, NaoEncontrado, RegraViolada

settings = get_settings()

app = FastAPI(
    title="Controle de Casa — Compras",
    description=(
        "Lista de compras e despensa da casa, usada pelo celular dentro do "
        "mercado. Serviço próprio, separado da API de finanças (D-25). Toda "
        "escrita exige o cabeçalho `X-Quem`."
    ),
    version="0.1.0",
    # Atrás do nginx do painel, em /api/compras; vazio no acesso direto.
    root_path=settings.root_path,
)


@app.exception_handler(NaoEncontrado)
def _nao_encontrado(_: Request, exc: NaoEncontrado) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(Conflito)
def _conflito(_: Request, exc: Conflito) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc), **exc.corpo}
    )


@app.exception_handler(RegraViolada)
def _regra_violada(_: Request, exc: RegraViolada) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(FinancasIndisponivel)
def _financas_indisponivel(_: Request, exc: FinancasIndisponivel) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})


app.include_router(lista.router)
app.include_router(despensa.router)
app.include_router(mudancas.router)
app.include_router(produtos.router)
app.include_router(secoes.router)
app.include_router(notas.router)
app.include_router(mercados.router)
app.include_router(precos.router)
app.include_router(identidades.router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, Any]:
    """Vivo e falando com o banco, no mesmo formato do de finanças."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        banco = "ok"
    except Exception as exc:
        banco = f"erro: {exc}"
    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco}
