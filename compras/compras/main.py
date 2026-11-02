"""Aplicação FastAPI do serviço `compras` (D-25)."""

from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from compras.config import get_settings
from compras.db import engine

settings = get_settings()

app = FastAPI(
    title="Controle de Casa — Compras",
    description=(
        "Lista de compras e despensa da casa, usada pelo celular dentro do "
        "mercado. Serviço próprio, separado da API de finanças (D-25)."
    ),
    version="0.1.0",
    # Atrás do nginx do painel, em /api/compras; vazio no acesso direto.
    root_path=settings.root_path,
)


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
