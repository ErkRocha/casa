"""Router de ingestão (fase 5).

Upload do PDF, revisão dos itens em staging e promoção para `transacoes`.
Nenhum endpoint aqui escreve em `transacoes` sem aprovação explícita (D-07).
"""

from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.enums import StatusItem, TipoTransacao
from app.schemas.common import LoteResponse
from app.schemas.ingestao import (
    ImportacaoDetalhe,
    ImportacaoRead,
    ItemAjuste,
    ItemRead,
    LoteItens,
    LoteRejeitar,
    ResultadoAprovacao,
)
from app.services.base import NaoEncontrado, RegraViolada
from app.services.ingestao import IngestaoService

router = APIRouter(prefix="/importacoes", tags=["ingestão"])

SessionDep = Annotated[Session, Depends(get_session)]

#: Fatura de cartão raramente passa disso. O limite evita que um upload
#: errado consuma memória do container.
TAMANHO_MAXIMO = 15 * 1024 * 1024


@router.post("", response_model=ImportacaoRead, status_code=status.HTTP_201_CREATED)
async def importar(
    session: SessionDep,
    arquivo: Annotated[UploadFile, File(description="PDF de fatura ou extrato")],
) -> Any:
    """Lê o PDF e cria os itens em staging.

    O arquivo é processado localmente com `pdfplumber` e **não sai da
    máquina** (D-08). Reimportar o mesmo PDF volta 409: o hash do arquivo é
    único.
    """
    conteudo = await arquivo.read()

    if not conteudo:
        raise RegraViolada("Arquivo vazio.")
    if len(conteudo) > TAMANHO_MAXIMO:
        raise RegraViolada(
            f"Arquivo maior que {TAMANHO_MAXIMO // 1024 // 1024} MB. "
            "Fatura e extrato costumam ter menos de 1 MB."
        )
    if not conteudo.startswith(b"%PDF"):
        raise RegraViolada("O arquivo não é um PDF.")

    importacao = IngestaoService(session).importar(arquivo.filename or "sem-nome.pdf", conteudo)
    session.commit()
    return importacao


@router.get("", response_model=list[ImportacaoRead])
def listar(session: SessionDep) -> Any:
    return IngestaoService(session).listar()


@router.get("/{importacao_id}/arquivo", response_class=Response)
def baixar_arquivo(importacao_id: int, session: SessionDep) -> Response:
    """Devolve o PDF original desta importação.

    É o que fecha o rastro: a transação aponta para a importação, e a
    importação devolve o documento que a originou. Sem isto, conferir um
    lançamento antigo contra o comprovante dependeria de o arquivo continuar
    na pasta de origem, com o mesmo nome, na mesma máquina.

    `inline` no Content-Disposition: o navegador abre o PDF em vez de baixar,
    que é o comportamento certo para conferir uma linha e fechar a aba.
    """
    importacao = IngestaoService(session).get(importacao_id)

    conteudo = importacao.arquivo_conteudo
    if conteudo is None:
        raise NaoEncontrado("arquivo da importação", importacao_id)

    # `quote` no nome: ele veio do upload do usuário, e acento ou aspas num
    # cabeçalho HTTP quebram o download em alguns navegadores.
    nome = quote(importacao.arquivo_nome or f"importacao-{importacao_id}.pdf")
    return Response(
        content=conteudo,
        media_type=importacao.arquivo_tipo or "application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{nome}"},
    )


@router.get("/{importacao_id}", response_model=ImportacaoDetalhe)
def detalhe(
    importacao_id: int,
    session: SessionDep,
    apenas: Annotated[StatusItem | None, Query(description="Filtra por status")] = None,
) -> Any:
    service = IngestaoService(session)
    importacao = service.get(importacao_id)
    itens = service.itens(importacao_id, apenas)

    # Quanto entra em despesa se aprovar tudo que está pendente.
    total_pendente = sum(
        (
            item.valor or Decimal("0")
            for item in itens
            if item.status is StatusItem.PENDENTE and item.tipo_sugerido is TipoTransacao.DESPESA
        ),
        Decimal("0"),
    )

    return ImportacaoDetalhe(
        importacao=ImportacaoRead.model_validate(importacao),
        itens=[ItemRead.model_validate(item) for item in itens],
        total_pendente=total_pendente,
    )


@router.patch("/itens/{item_id}", response_model=ItemRead)
def ajustar_item(item_id: int, payload: ItemAjuste, session: SessionDep) -> Any:
    """Corrige um item antes de aprovar.

    Mudar a categoria grava ou reforça uma regra de categorização — é o que
    faz a próxima importação já vir certa (D-09).
    """
    item = IngestaoService(session).ajustar(item_id, payload.model_dump(exclude_unset=True))
    session.commit()
    return item


@router.post("/itens/aprovar", response_model=ResultadoAprovacao)
def aprovar(payload: LoteItens, session: SessionDep) -> Any:
    """Promove os itens para `transacoes`.

    É o único caminho por onde dado de ingestão vira dado real. Item que
    esbarra na deduplicação vira `duplicado` e o lote continua.
    """
    resultado = IngestaoService(session).aprovar(payload.ids)
    session.commit()
    return resultado


@router.post("/itens/rejeitar", response_model=LoteResponse)
def rejeitar(payload: LoteRejeitar, session: SessionDep) -> Any:
    afetadas = IngestaoService(session).rejeitar(payload.ids, payload.motivo)
    session.commit()
    return LoteResponse(afetadas=afetadas)
