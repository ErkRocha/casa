"""Quem a sync da Pluggy promove sozinha, e por que o resto fica (D-21).

Função pura, usada pela sync, pela simulação dela e pelo reprocessamento:
as três têm que dizer a mesma coisa sobre o mesmo item. Recebe o item
convertido (`ItemExtraido`, onde vivem a leitura e a observação), a
categoria que o enriquecimento sugeriu e se já existe transação idêntica.

A ordem dos testes é a ordem do relatório: o primeiro motivo que se aplica é
o motivo do item.

**Rejeição automática (D-22).** Antes da promoção, `motivo_para_rejeitar`
separa o que não é gasto nem receita da casa e não precisa de decisão:
pagamento de fatura (os dois lados, D-05) e dinheiro entre contas da casa.
O item fica no staging como `rejeitado`, com o motivo escrito — nada entra
em `transacoes`, e a tela da importação mostra e deixa reverter.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.conversao_pluggy import (
    OBS_ABERTA,
    OBS_MESMA_PESSOA,
    OBS_PAGAMENTO_NA_CONTA,
    OBS_PAGAMENTO_NO_CARTAO,
)
from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido

LEITURA_LIMPA = Decimal("1.00")
#: Trecho da observação que a sync põe no gêmeo vindo da própria Pluggy.
MARCA_DUPLICATA = "Possível duplicata"
#: A nota inteira, para tirá-la da observação quando a revisão decide.
NOTA_DUPLICATA = re.compile(rf"{MARCA_DUPLICATA}.*?aprovar os dois\.", re.S)

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


#: Motivo -> texto gravado em `motivo_rejeicao` e mostrado no relatório (D-22).
REJEICOES: dict[str, str] = {
    "pagamento_fatura": (
        "Rejeitado pela sync (D-22): pagamento de fatura. O gasto já vem pelas "
        "compras do cartão (D-05)."
    ),
    "movimento_casa": (
        "Rejeitado pela sync (D-22): dinheiro entre contas da casa, não é gasto nem receita."
    ),
}


#: Rótulo curto de cada rejeição, para os relatórios no terminal.
ROTULOS_REJEICAO: dict[str, str] = {
    "pagamento_fatura": "pagamento de fatura (D-05)",
    "movimento_casa": "dinheiro entre contas da casa",
}


def motivo_para_rejeitar(extraido: ItemExtraido, *, documentos_casa: frozenset[str]) -> str | None:
    """`None` = segue para a promoção ou a revisão. Senão, a chave em `REJEICOES`.

    Possível duplicata não é rejeitada: ela pede o olho do usuário.
    """
    observacao = extraido.observacao or ""
    if MARCA_DUPLICATA in observacao or (extraido.id_externo or "").startswith("bill:"):
        return None
    if OBS_PAGAMENTO_NO_CARTAO in observacao or OBS_PAGAMENTO_NA_CONTA in observacao:
        return "pagamento_fatura"
    if OBS_MESMA_PESSOA in observacao:
        return "movimento_casa"
    if extraido.documento_contraparte and extraido.documento_contraparte in documentos_casa:
        return "movimento_casa"
    return None


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
    # A compra em aberto (D-23) é promovida como as outras: a marca diz só
    # que a sync ainda vai atualizá-la. Qualquer outra nota segura o item.
    if observacao.replace(OBS_ABERTA, "").strip():
        return "observacao"
    if extraido.confianca < LEITURA_LIMPA:
        return "confianca"
    if categoria_id is None:
        return "sem_categoria"
    return None
