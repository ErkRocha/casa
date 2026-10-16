"""Schemas da revisão (D-21, D-22)."""

from pydantic import BaseModel


class MotivoRevisao(BaseModel):
    #: Chave estável (`possivel_duplicata`, `transferencia`...).
    motivo: str
    rotulo: str
    quantidade: int


class RevisarResumo(BaseModel):
    """Itens pendentes no staging, por motivo, na ordem de leitura."""

    total: int
    #: Só os motivos com algum item.
    motivos: list[MotivoRevisao]
