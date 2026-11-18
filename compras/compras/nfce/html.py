"""Peças comuns dos leitores de HTML da NFC-e: decodificação, uma árvore
mínima (só biblioteca padrão), números e datas no formato da página."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

_CHARSET = re.compile(rb"charset\s*=\s*[\"']?\s*([\w-]+)", re.IGNORECASE)


def decodificar(conteudo: bytes) -> str:
    """Decodifica pelo `charset` declarado nos primeiros 2 KB (padrão utf-8).

    A Consulta Completa do RS vem em iso-8859-1; o resto, em utf-8."""
    achado = _CHARSET.search(conteudo[:2048])
    nome = achado.group(1).decode("ascii").lower() if achado else "utf-8"
    if nome in {"iso-8859-1", "iso8859-1", "latin1", "latin-1"}:
        nome = "latin-1"
    try:
        return conteudo.decode(nome, errors="replace")
    except LookupError:
        return conteudo.decode("utf-8", errors="replace")


_VAZIOS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)


@dataclass
class _No:
    tag: str
    attrs: dict[str, str]
    filhos: list[_No | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def texto(self) -> str:
        partes: list[str] = []
        for f in self.filhos:
            partes.append(f if isinstance(f, str) else f.texto())
        return " ".join(" ".join(partes).split())

    def todos(self) -> list[_No]:
        achados: list[_No] = []
        for f in self.filhos:
            if isinstance(f, _No):
                achados.append(f)
                achados.extend(f.todos())
        return achados

    def por_classe(self, classe: str) -> list[_No]:
        return [n for n in self.todos() if classe in n.classes]

    def por_id(self, id_: str) -> _No | None:
        return next((n for n in self.todos() if n.attrs.get("id") == id_), None)


class _Arvore(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = _No("raiz", {})
        self._pilha = [self.raiz]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        no = _No(tag, {k: v or "" for k, v in attrs})
        self._pilha[-1].filhos.append(no)
        if tag not in _VAZIOS:
            self._pilha.append(no)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._pilha[-1].filhos.append(_No(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        # HTML real fecha fora de ordem: volta até a tag aberta mais próxima.
        for i in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[i].tag == tag:
                del self._pilha[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._pilha[-1].filhos.append(data)


# --- números e datas no formato da página ---------------------------------------


def _decimal(texto: str | None) -> Decimal | None:
    """ "1.234,56" -> 1234.56; o primeiro número do texto."""
    if not texto:
        return None
    achado = re.search(r"-?\d[\d.]*(?:,\d+)?", texto)
    if not achado:
        return None
    try:
        return Decimal(achado.group(0).replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _depois_do_rotulo(no: _No) -> str:
    """O texto de um campo como "Qtde.: 2", sem o rótulo."""
    return no.texto().split(":", 1)[-1].strip()


def _gtin(codigo: str | None) -> str | None:
    """O código vira GTIN só quando é, com certeza razoável, um código de
    barras brasileiro: 13 dígitos, prefixo GS1 Brasil (789/790) e dígito
    verificador certo. Código interno do mercado fica só em `codigo`."""
    if not codigo or not re.fullmatch(r"\d{13}", codigo) or codigo[:3] not in {"789", "790"}:
        return None
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(codigo[:12]))
    return codigo if (10 - soma % 10) % 10 == int(codigo[12]) else None
