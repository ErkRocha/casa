"""Aplicação FastAPI."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import analytics, cadastros, ingestao, pluggy, regras, relatorios, transacoes
from app.services.base import Conflito, NaoEncontrado, RegraViolada

settings = get_settings()

app = FastAPI(
    title="Controle de Casa — API",
    description=(
        "Sistema local de controle e análise financeira de uma casa. "
        "Roda em Docker na máquina do usuário; não vai pra internet."
    ),
    version="0.1.0",
    # Atrás do nginx do painel, em /api (D-19); vazio no acesso direto.
    root_path=settings.api_root_path,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Erros de domínio -> HTTP
# --------------------------------------------------------------------------


@app.exception_handler(NaoEncontrado)
def _nao_encontrado(_: Request, exc: NaoEncontrado) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(Conflito)
def _conflito(_: Request, exc: Conflito) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(RegraViolada)
def _regra_violada(_: Request, exc: RegraViolada) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------

app.include_router(cadastros.pessoas_router)
app.include_router(cadastros.contas_router)
app.include_router(cadastros.categorias_router)
app.include_router(cadastros.formas_pagamento_router)
app.include_router(cadastros.locais_router)
app.include_router(cadastros.orcamentos_router)
app.include_router(transacoes.router)
app.include_router(analytics.router)
app.include_router(ingestao.router)
app.include_router(regras.router)
app.include_router(pluggy.router)
app.include_router(relatorios.router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, Any]:
    """Vivo e falando com o banco.

    Critério de pronto da fase 0 do roadmap.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        banco = "ok"
    except Exception as exc:
        banco = f"erro: {exc}"

    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco}
