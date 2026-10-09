"""Quem a sync da Pluggy promove sozinha, e por que o resto fica (D-21).

Função pura, usada pela sync, pela simulação dela e pelo reprocessamento:
as três têm que dizer a mesma coisa sobre o mesmo item. Recebe o item
convertido (`ItemExtraido`, onde vivem a leitura e a observação), a
categoria que o enriquecimento sugeriu e se já existe transação idêntica.

A ordem dos testes é a ordem do relatório: o primeiro motivo que se aplica é
o motivo do item.
"""

from __future__ import annotations

from decimal import Decimal

from app.conversao_pluggy import OBS_PAGAMENTO_NO_CARTAO
from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido

LEITURA_LIMPA = Decimal("1.00")
#: Trecho da observação que a sync põe no gêmeo vindo da própria Pluggy.
MARCA_DUPLICATA = "Possível duplicata"

#: Motivo -> texto do relatório, na ordem em que são checados.
MOTIVOS: dict[str, str] = {
    "duplicata": "transação idêntica já existe (hash_dedup)",
    "possivel_duplicata": "possível duplicata vinda da Pluggy",
    "encargos": "encargos de fatura deduzidos",
    "pagamento_fatura_cartao": "pagamento de fatura, lado do cartão",
    "transferencia": "transferência",
    "observacao": "item com observação",
    "confianca": "leitura abaixo de 1.00",
    "sem_categoria": "sem categoria",
}


def motivo_para_revisao(
    extraido: ItemExtraido, *, categoria_id: int | None, ja_existe: bool
) -> str | None:
    """`None` = item limpo, promovido pela sync. Senão, a chave do motivo."""
    observacao = extraido.observacao or ""
    if ja_existe:
        return "duplicata"
    if MARCA_DUPLICATA in observacao:
        return "possivel_duplicata"
    if (extraido.id_externo or "").startswith("bill:"):
        return "encargos"
    if extraido.tipo is TipoTransacao.TRANSFERENCIA:
        # Transferência nunca é promovida: `transacoes` exige conta de origem e
        # destino, e a promoção recusa sem elas (D-05).
        if OBS_PAGAMENTO_NO_CARTAO in observacao:
            return "pagamento_fatura_cartao"
        return "transferencia"
    if observacao:
        return "observacao"
    if extraido.confianca < LEITURA_LIMPA:
        return "confianca"
    if categoria_id is None:
        return "sem_categoria"
    return None
