"""Transação da Pluggy -> `ItemExtraido` (fase 5b, passo 5; D-16).

Função pura: sem banco, sem HTTP, sem relógio. Recebe a transação, a conta
da Pluggy a que ela pertence e as faturas já buscadas, e devolve o mesmo
contrato dos parsers de PDF. Daí em diante o caminho é um só — o service de
ingestão, o enriquecimento, a revisão e a promoção.

**Por que este módulo mora aqui, e não num dos dois pacotes.** Ele precisa
ler os dois lados, e cada lado tem uma guarda que o impede de morar nele:

- `app.pluggy` só pode importar `app.pluggy.*` (teste de isolamento do
  cliente). A conversão precisa de `ItemExtraido` e `TipoTransacao`.
- `app.ingestao` não pode ter cliente HTTP (D-08,
  `test_pdf_nunca_sai_da_maquina`). Importar `app.pluggy.modelos` executa o
  `__init__` do pacote, que importa o cliente e o `httpx`. O teste, que é
  textual, nem perceberia; a regra que ele protege, sim.

**O que as amostras reais mostraram** (e que este módulo assume):

- O sinal de `amount` é **oposto** entre conta e cartão. Em conta, `DEBIT`
  vem negativo; no cartão, a compra (`DEBIT`) vem positiva e o pagamento
  (`CREDIT`) negativo. Por isso o sentido sai de `type`, nunca do sinal; o
  sinal só serve para conferir.
- O pagamento da fatura do lado do cartão vem com `operationType =
  PAGAMENTO_FATURA` e categoria `Credit card payment`. Do lado da conta, nem
  operação nem categoria são específicas (`OUTROS`, `OPERACAO_CREDITO`,
  `Transfers`, `Loans and financing`): só a descrição diz que é pagamento.
- `date` de transação vem em UTC, e meia-noite em São Paulo chega como
  `T03:00:00Z`. Já `dueDate` de fatura é data pura gravada como
  `T00:00:00Z`: convertida para São Paulo, viraria a véspera — e vencimento
  no dia 1º cairia no mês anterior.
- Cobrança sem cartão (IOF, juros, multa) traz `cardNumber = "0000"`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido, limpar_descricao, sem_acento
from app.pluggy.modelos import Conta, Fatura, Transacao

FUSO = ZoneInfo("America/Sao_Paulo")
CENTAVO = Decimal("0.01")

#: Mesma escala dos parsers de PDF: leitura direta na fatura é 1.00, linha de
#: extrato é 0.95, e o que depende de interpretação (transferência, estorno,
#: competência estimada) é 0.70 — abaixo de 0.80, a revisão destaca.
CONFIANCA_FATURA = Decimal("1.00")
CONFIANCA_CONTA = Decimal("0.95")
CONFIANCA_INTERPRETADA = Decimal("0.70")
CONFIANCA_SEM_BASE = Decimal("0.50")

_DEBITO = "DEBIT"
_CREDITO = "CREDIT"
_OPERACAO_PAGAMENTO_FATURA = "PAGAMENTO_FATURA"
_CATEGORIA_PAGAMENTO_FATURA = "Credit card payment"
_CATEGORIA_MESMA_PESSOA = "Same person transfer"

#: "PAGAMENTO DE FATURA CARTAO CREDITO VIA DEBITO", "Pagamento de fatura",
#: "Pagamento Cartão de crédito" — as três formas vistas do lado da conta.
_DESCRICAO_PAGAMENTO_FATURA = re.compile(r"^pagamento\s+(?:de\s+)?(?:fatura|cartao)\b")

#: Final de cartão que a Pluggy usa em cobrança sem cartão (IOF, juros).
_SEM_CARTAO = "0000"

_OBS_PAGAMENTO_NO_CARTAO = (
    "Pagamento da fatura, do lado do cartão. A saída da conta corrente é a "
    "outra ponta do mesmo dinheiro e o gasto já vem pelas compras: rejeite "
    "este lado na revisão (D-05)."
)
_OBS_PAGAMENTO_NA_CONTA = (
    "Pagamento de fatura de cartão, identificado pela descrição: dinheiro "
    "mudando de conta, fica fora do cálculo de gasto (D-05)."
)
_OBS_MESMA_PESSOA = (
    "A Pluggy classifica como transferência para a mesma pessoa. Confira se "
    "é entre contas suas; se não for, troque para despesa ou receita."
)
_OBS_ESTORNO = (
    "Crédito no cartão que a Pluggy não marca como pagamento de fatura: "
    "tratado como estorno. Confira."
)


@dataclass(slots=True)
class ResultadoConversao:
    """O lote convertido e o que ficou de fora, contado."""

    itens: list[ItemExtraido] = field(default_factory=list)
    #: `PENDING` ainda pode mudar de valor ou sumir (D-16): fica para a sync
    #: em que consolidar.
    pendentes_ignoradas: int = 0
    #: Status desconhecido ou valor zero. Cada uma deixa um aviso.
    outras_ignoradas: int = 0
    avisos: list[str] = field(default_factory=list)


def converter_lote(
    transacoes: Iterable[Transacao],
    conta: Conta,
    faturas: Iterable[Fatura] = (),
    *,
    dia_fechamento: int | None = None,
    dia_vencimento: int | None = None,
) -> ResultadoConversao:
    """Converte as transações de uma conta, ignorando e contando o que não entra.

    `dia_fechamento` e `dia_vencimento` são os da forma de pagamento mapeada;
    só servem ao cartão, quando a fatura apontada não está em `faturas`.
    """
    por_id = {f.id: f for f in faturas}
    resultado = ResultadoConversao()

    for transacao in transacoes:
        if transacao.status == "PENDING":
            resultado.pendentes_ignoradas += 1
            continue
        if transacao.status != "POSTED":
            resultado.outras_ignoradas += 1
            resultado.avisos.append(
                f"Transação {transacao.id} ignorada: status {transacao.status!r} desconhecido."
            )
            continue
        if transacao.amount == 0:
            # `transacoes` exige valor > 0, como o PDF já trata a linha zerada.
            resultado.outras_ignoradas += 1
            resultado.avisos.append(f"Transação {transacao.id} ignorada: valor zero.")
            continue

        resultado.itens.append(
            converter(
                transacao,
                conta,
                por_id,
                linha_num=len(resultado.itens) + 1,
                dia_fechamento=dia_fechamento,
                dia_vencimento=dia_vencimento,
            )
        )

    return resultado


def converter(
    transacao: Transacao,
    conta: Conta,
    faturas: Mapping[str, Fatura],
    *,
    linha_num: int = 1,
    dia_fechamento: int | None = None,
    dia_vencimento: int | None = None,
) -> ItemExtraido:
    """Uma transação `POSTED` -> um `ItemExtraido`.

    Não atribui pessoa: isso é enriquecimento (passo 6). Entrega o final do
    cartão, que é por onde o enriquecimento resolve o cartão adicional.
    """
    if transacao.status != "POSTED":
        raise ValueError(f"Só transação POSTED é convertida; {transacao.id} é {transacao.status}.")
    if transacao.account_id != conta.id:
        raise ValueError(f"Transação {transacao.id} não é da conta {conta.id}.")

    observacoes: list[str] = []
    confiancas: list[Decimal] = []

    entrada = _entrada(transacao, conta, observacoes, confiancas)
    valor = _valor(transacao, observacoes, confiancas)
    data_local = _data_local(transacao.date)

    tipo, direcao, confianca = _classificar(transacao, conta, entrada, observacoes)
    confiancas.append(confianca)

    if conta.e_cartao:
        competencia = _competencia_cartao(
            transacao, data_local, faturas, dia_fechamento, dia_vencimento, observacoes, confiancas
        )
    else:
        # Conta: o mês da própria data (D-02).
        competencia = data_local.replace(day=1)

    meta = transacao.credit_card_metadata
    parcela_num = parcela_total = None
    if meta and meta.total_installments and meta.total_installments > 1:
        parcela_num, parcela_total = meta.installment_number, meta.total_installments

    bruta = transacao.description_raw or transacao.description or ""
    descricao = limpar_descricao(transacao.description or bruta) or "(sem descrição na Pluggy)"
    if parcela_num and parcela_total:
        # O Nubank repete a parcela no texto ("Loja 1/3"); a fatura em PDF
        # também tira, e a parcela já vai nos campos próprios.
        descricao = re.sub(rf"\s+0?{parcela_num}\s*/\s*0?{parcela_total}$", "", descricao)

    return ItemExtraido(
        # Texto cru, imutável (regra 11): vira `descricao_original`.
        linha_bruta=bruta,
        linha_num=linha_num,
        data=data_local,
        valor=valor,
        descricao=descricao,
        tipo=tipo,
        cartao_final=_cartao_final(transacao),
        parcela_num=parcela_num,
        parcela_total=parcela_total,
        direcao=direcao,
        confianca=min(confiancas),
        observacao=" ".join(observacoes) or None,
        id_externo=transacao.id,
        competencia=competencia,
    )


# --- sentido e valor -----------------------------------------------------------


def _entrada(
    transacao: Transacao, conta: Conta, observacoes: list[str], confiancas: list[Decimal]
) -> bool:
    """O dinheiro entrou na conta (ou abateu a dívida do cartão)?

    O `type` decide. O sinal só confere, porque a convenção dele inverte entre
    conta e cartão: em conta a saída é negativa; no cartão a compra é
    positiva.
    """
    positivo = transacao.amount > 0
    # Sinal que uma entrada teria nesta conta.
    entrada_positiva = not conta.e_cartao

    if transacao.type not in (_DEBITO, _CREDITO):
        observacoes.append(
            f"A Pluggy não informou débito ou crédito (type={transacao.type!r}); "
            "o sentido foi deduzido do sinal do valor."
        )
        confiancas.append(CONFIANCA_SEM_BASE)
        return positivo == entrada_positiva

    entrada = transacao.type == _CREDITO
    if positivo != (entrada == entrada_positiva):
        observacoes.append(
            f"O sinal do valor ({transacao.amount}) contradiz o tipo {transacao.type}; "
            "valeu o tipo."
        )
        confiancas.append(CONFIANCA_SEM_BASE)
    return entrada


def _valor(transacao: Transacao, observacoes: list[str], confiancas: list[Decimal]) -> Decimal:
    """Sempre positivo e com centavos; o sentido vai em `tipo` (regra 1)."""
    bruto = transacao.amount
    moeda = transacao.currency_code
    if moeda and moeda != "BRL":
        if transacao.amount_in_account_currency is not None:
            bruto = transacao.amount_in_account_currency
            observacoes.append(f"Compra em {moeda}; valor convertido pela Pluggy para a conta.")
        else:
            observacoes.append(f"Valor em {moeda}, sem conversão informada pela Pluggy.")
            confiancas.append(CONFIANCA_SEM_BASE)

    valor = abs(Decimal(bruto))
    arredondado = valor.quantize(CENTAVO)
    if arredondado != valor:
        observacoes.append(f"Valor com mais de 2 casas ({valor}) arredondado para {arredondado}.")
        confiancas.append(CONFIANCA_INTERPRETADA)
    return arredondado


def _classificar(
    transacao: Transacao, conta: Conta, entrada: bool, observacoes: list[str]
) -> tuple[TipoTransacao, str | None, Decimal]:
    """Despesa, receita ou transferência — pelo que os dados sustentam.

    Na dúvida, confiança abaixo de 0.80 e uma observação, para a revisão
    olhar. Nunca confiança alta em cima de palpite.
    """
    operacao = (transacao.operation_type or "").upper()
    categoria = transacao.category or ""
    direcao = "entrada" if entrada else "saida"

    if conta.e_cartao:
        if not entrada:
            return TipoTransacao.DESPESA, None, CONFIANCA_FATURA
        if operacao == _OPERACAO_PAGAMENTO_FATURA or categoria == _CATEGORIA_PAGAMENTO_FATURA:
            observacoes.append(_OBS_PAGAMENTO_NO_CARTAO)
            return TipoTransacao.TRANSFERENCIA, direcao, CONFIANCA_INTERPRETADA
        observacoes.append(_OBS_ESTORNO)
        return TipoTransacao.RECEITA, None, CONFIANCA_INTERPRETADA

    chave = sem_acento(transacao.description or transacao.description_raw or "").lower().strip()
    if (
        operacao == _OPERACAO_PAGAMENTO_FATURA
        or categoria == _CATEGORIA_PAGAMENTO_FATURA
        or _DESCRICAO_PAGAMENTO_FATURA.match(chave)
    ):
        observacoes.append(_OBS_PAGAMENTO_NA_CONTA)
        return TipoTransacao.TRANSFERENCIA, direcao, CONFIANCA_INTERPRETADA
    if categoria == _CATEGORIA_MESMA_PESSOA:
        observacoes.append(_OBS_MESMA_PESSOA)
        return TipoTransacao.TRANSFERENCIA, direcao, CONFIANCA_INTERPRETADA

    tipo = TipoTransacao.RECEITA if entrada else TipoTransacao.DESPESA
    return tipo, direcao, CONFIANCA_CONTA


# --- datas e competência ---------------------------------------------------------


def _data_local(momento: datetime) -> date:
    """O dia em São Paulo. Compra às 23h de 21/08 chega como 02h de 22/08 UTC."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(FUSO).date()


def _dia_civil(momento: datetime) -> date:
    """Data pura que a Pluggy grava como meia-noite UTC (`dueDate`).

    Não converte de fuso: `2026-11-01T00:00:00Z` é "vence em 1º/11", e em São
    Paulo viraria 31/10 — competência de outubro, errada.
    """
    if momento.tzinfo is None:
        return momento.date()
    return momento.astimezone(UTC).date()


def _competencia_cartao(
    transacao: Transacao,
    data_local: date,
    faturas: Mapping[str, Fatura],
    dia_fechamento: int | None,
    dia_vencimento: int | None,
    observacoes: list[str],
    confiancas: list[Decimal],
) -> date:
    """Mês do vencimento da fatura apontada pelo `billId` (D-02).

    É o dado que o próprio banco declara. Sem a fatura, estima pelos dias da
    forma de pagamento; sem os dias, cai no mês da compra. Os dois últimos
    caminhos baixam a confiança e explicam o porquê.
    """
    meta = transacao.credit_card_metadata
    bill_id = meta.bill_id if meta else None
    fatura = faturas.get(bill_id) if bill_id else None
    if fatura is not None:
        return _dia_civil(fatura.due_date).replace(day=1)

    motivo = (
        f"a fatura {bill_id} não veio entre as faturas lidas"
        if bill_id
        else "a Pluggy não informou a fatura (billId)"
    )
    if dia_fechamento and dia_vencimento:
        competencia = estimar_competencia(data_local, dia_fechamento, dia_vencimento)
        observacoes.append(
            f"Competência estimada pelo fechamento no dia {dia_fechamento} e vencimento "
            f"no dia {dia_vencimento}, porque {motivo}. Feriado ou mudança de data "
            "erram a estimativa: confira."
        )
        confiancas.append(CONFIANCA_INTERPRETADA)
        return competencia

    observacoes.append(
        f"Competência no mês da compra, porque {motivo} e a forma de pagamento não "
        "tem dia de fechamento e vencimento. Confira em que fatura ela caiu."
    )
    confiancas.append(CONFIANCA_SEM_BASE)
    return data_local.replace(day=1)


def estimar_competencia(compra: date, dia_fechamento: int, dia_vencimento: int) -> date:
    """O mês de vencimento da fatura em que a compra provavelmente caiu.

    Compra no dia do fechamento ou depois vai para a fatura seguinte. Se o
    vencimento é num dia menor que o fechamento, ele cai no mês seguinte ao
    fechamento (fecha 25, vence 5).
    """
    meses = 1 if compra.day >= dia_fechamento else 0
    if dia_vencimento <= dia_fechamento:
        meses += 1
    indice = compra.year * 12 + compra.month - 1 + meses
    return date(indice // 12, indice % 12 + 1, 1)


def _cartao_final(transacao: Transacao) -> str | None:
    """Os 4 últimos dígitos do cartão. Cobrança sem cartão vem `0000`: nulo."""
    meta = transacao.credit_card_metadata
    numero = re.sub(r"\D", "", meta.card_number or "") if meta else ""
    if len(numero) < 4 or numero[-4:] == _SEM_CARTAO:
        return None
    return numero[-4:]
