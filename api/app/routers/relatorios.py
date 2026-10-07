"""Router da tela de relatórios (fase 6). Só leitura.

Nenhum endpoint aqui gera ou altera relatório: a geração continua pelo CLI
no host (`make relatorio m=AAAA-MM`), que chama o modelo com a credencial da
máquina e grava pelo service.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Relatorio
from app.schemas.common import Page, Paginacao, paginacao
from app.schemas.relatorios import RelatorioDetalhe, RelatorioResumo
from app.services.relatorios import RelatorioLeituraService, com_ia

router = APIRouter(prefix="/relatorios", tags=["relatórios"])

SessionDep = Annotated[Session, Depends(get_session)]
PaginacaoDep = Annotated[Paginacao, Depends(paginacao)]


def _resumo(r: Relatorio) -> dict[str, Any]:
    return {
        "id": r.id,
        "competencia": r.competencia,
        "tipo": r.tipo,
        "com_ia": com_ia(r),
        "prompt_versao": r.prompt_versao,
        "criado_em": r.criado_em,
    }


@router.get("", response_model=Page[RelatorioResumo])
def listar(session: SessionDep, pag: PaginacaoDep) -> Any:
    """Mais recente primeiro."""
    itens, total = RelatorioLeituraService(session).listar(pag)
    return Page(items=[_resumo(r) for r in itens], total=total, limit=pag.limit, offset=pag.offset)


@router.get("/{id_}", response_model=RelatorioDetalhe)
def obter(id_: int, session: SessionDep) -> Any:
    r = RelatorioLeituraService(session).get(id_)
    periodo = r.periodo_dados
    return {
        **_resumo(r),
        "conteudo": r.conteudo,
        # `{}` é o padrão da coluna: relatório sem dossiê salvo.
        "dossie": r.dados_base or None,
        "periodo_inicio": getattr(periodo, "lower", None),
        "periodo_fim": getattr(periodo, "upper", None),
        "execucao": r.execucao or {},
    }
