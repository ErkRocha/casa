"""Ingestão de extratos e faturas (fase 5).

A ordem da D-08: `pdfplumber` extrai o texto localmente, o parser
determinístico do banco resolve o que reconhece, e só o que sobrar de formato
desconhecido iria para um LLM — que ainda não existe aqui.

O PDF nunca vai inteiro para modelo nenhum.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdfplumber

from app.ingestao.base import DocumentoExtraido, ItemExtraido, Parser
from app.ingestao.nubank_extrato import NubankExtratoParser
from app.ingestao.nubank_fatura import NubankFaturaParser

#: Ordem importa: o primeiro que reconhecer ganha. Fatura antes de extrato
#: porque a fatura é mais específica.
PARSERS: list[Parser] = [NubankFaturaParser(), NubankExtratoParser()]


class FormatoDesconhecido(Exception):
    """Nenhum parser reconheceu o documento.

    Na fase 5 completa é aqui que o LLM entraria como fallback (D-08). Hoje o
    arquivo é recusado, o que é melhor que adivinhar.
    """


def extrair_texto(pdf: Path | bytes) -> str:
    """Texto do PDF inteiro, página a página.

    Roda local, sem rede. É esta string — e nunca o arquivo — que qualquer
    etapa seguinte enxerga.
    """
    if isinstance(pdf, bytes):
        import io

        origem: object = io.BytesIO(pdf)
    else:
        origem = pdf

    with pdfplumber.open(origem) as documento:  # type: ignore[arg-type]
        return "\n".join((pagina.extract_text() or "") for pagina in documento.pages)


def hash_arquivo(conteudo: bytes) -> str:
    """SHA-256 do arquivo. É o que barra reimportar o mesmo PDF (D-07)."""
    return hashlib.sha256(conteudo).hexdigest()


def escolher_parser(texto: str) -> Parser:
    for parser in PARSERS:
        if parser.reconhece(texto):
            return parser
    raise FormatoDesconhecido(
        "Nenhum parser reconheceu este arquivo. Hoje o sistema lê fatura e "
        "extrato do Nubank; outros bancos precisam de um parser novo."
    )


def processar(conteudo: bytes) -> DocumentoExtraido:
    """PDF -> documento extraído. Não toca no banco."""
    texto = extrair_texto(conteudo)
    return escolher_parser(texto).extrair(texto)


__all__ = [
    "PARSERS",
    "DocumentoExtraido",
    "FormatoDesconhecido",
    "ItemExtraido",
    "escolher_parser",
    "extrair_texto",
    "hash_arquivo",
    "processar",
]
