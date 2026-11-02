"""Texto normalizado para busca e unicidade (`*_normalizado`)."""

import unicodedata


def normalizar(texto: str) -> str:
    """Maiúsculas, sem acento e com os espaços colapsados.

    "  Pão  francês " vira "PAO FRANCES". É o que impede "leite integral 1L"
    e "Leite  integral 1l" de virarem dois produtos.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())
