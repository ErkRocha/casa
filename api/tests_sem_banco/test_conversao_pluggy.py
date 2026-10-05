"""Conversão de transação da Pluggy para `ItemExtraido` (fase 5b, passo 5).

Sem banco e sem rede. A fixture tem a estrutura das respostas reais do
MeuPluggy, com todo valor trocado (ids, descrições, nomes, cartões, datas).
"""

from __future__ import annotations

import ast
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.conversao_pluggy import converter, converter_lote, estimar_competencia
from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido
from app.pluggy.modelos import Conta, Fatura, Transacao

FIXTURE = Path(__file__).parent / "fixtures" / "pluggy_conversao.json"
DADOS: dict[str, Any] = json.loads(FIXTURE.read_text("utf-8"), parse_float=Decimal)

CARTAO = Conta.model_validate(DADOS["contas"]["cartao"])
CORRENTE = Conta.model_validate(DADOS["contas"]["corrente"])
FATURAS = {f.id: f for f in (Fatura.model_validate(x) for x in DADOS["faturas"])}


def _tx(grupo: str, nome: str, **troca: Any) -> Transacao:
    return Transacao.model_validate(DADOS[grupo][nome] | troca)


def _cartao(nome: str, **kwargs: Any) -> ItemExtraido:
    return converter(_tx("transacoes_cartao", nome), CARTAO, FATURAS, **kwargs)


def _conta(nome: str, **troca: Any) -> ItemExtraido:
    return converter(_tx("transacoes_conta", nome, **troca), CORRENTE, {})


class TestCartao:
    def test_compra_simples(self) -> None:
        item = _cartao("compra_simples")
        assert item.tipo is TipoTransacao.DESPESA
        assert item.valor == Decimal("87.90")
        assert isinstance(item.valor, Decimal)
        assert item.data == date(2025, 3, 20)
        # Fatura que vence em 10/04: despesa de abril (D-02).
        assert item.competencia == date(2025, 4, 1)
        assert item.cartao_final == "1111"
        assert item.id_externo == "00000000-0000-4000-8000-00000000a001"
        assert item.confianca == Decimal("1.00")
        assert item.observacao is None
        assert item.direcao is None
        assert item.parcela_num is None and item.parcela_total is None

    def test_compra_parcelada(self) -> None:
        item = _cartao("compra_parcelada")
        assert (item.parcela_num, item.parcela_total) == (2, 3)
        assert item.valor == Decimal("120.00")
        # A parcela sai do texto editável e fica nos campos próprios; o texto
        # cru continua inteiro (regra 11).
        assert item.descricao == "Loja Ficticia"
        assert item.linha_bruta == "Loja Ficticia 2/3"
        # Cartão adicional: o final é o dele, não o do titular.
        assert item.cartao_final == "2222"

    def test_compra_perto_da_meia_noite_fica_no_dia_de_sao_paulo(self) -> None:
        """02:22 UTC de 29/03 é 23:22 de 28/03 em São Paulo."""
        assert _cartao("perto_da_meia_noite").data == date(2025, 3, 28)

    def test_vencimento_no_dia_1_nao_vira_o_mes_anterior(self) -> None:
        """`dueDate` é data pura em meia-noite UTC. Convertida para São Paulo,
        2025-05-01 viraria 30/04 e a competência cairia em abril."""
        assert _cartao("fatura_no_dia_1").competencia == date(2025, 5, 1)

    def test_sem_fatura_encontrada_estima_pelos_dias_da_forma(self) -> None:
        item = _cartao("sem_fatura_encontrada", dia_fechamento=3, dia_vencimento=10)
        # Compra em 04/03, depois do fechamento do dia 3: fatura que fecha em
        # 03/04 e vence em 10/04.
        assert item.competencia == date(2025, 4, 1)
        assert item.confianca == Decimal("0.70")
        assert item.observacao is not None and "estimada" in item.observacao
        assert "00000000-0000-4000-8000-00000000b999" in item.observacao

    def test_sem_fatura_e_sem_dias_cai_no_mes_da_compra_com_confianca_baixa(self) -> None:
        item = _cartao("sem_fatura_encontrada")
        assert item.competencia == date(2025, 3, 1)
        assert item.confianca == Decimal("0.50")
        assert item.observacao is not None and "Confira" in item.observacao

    def test_sem_bill_id_usa_o_fallback(self) -> None:
        dados = DADOS["transacoes_cartao"]["compra_simples"]
        meta = {k: v for k, v in dados["creditCardMetadata"].items() if k != "billId"}
        tx = Transacao.model_validate(dados | {"creditCardMetadata": meta})
        item = converter(tx, CARTAO, FATURAS, dia_fechamento=3, dia_vencimento=10)
        assert item.competencia == date(2025, 4, 1)
        assert item.observacao is not None and "billId" in item.observacao

    def test_pagamento_de_fatura_do_lado_do_cartao_e_transferencia(self) -> None:
        item = _cartao("pagamento_de_fatura")
        assert item.tipo is TipoTransacao.TRANSFERENCIA
        assert item.direcao == "entrada"
        assert item.valor == Decimal("950.40")
        assert item.confianca < Decimal("0.80")
        assert item.observacao is not None and "rejeite" in item.observacao

    def test_estorno_vira_receita_com_confianca_baixa(self) -> None:
        item = _cartao("estorno")
        assert item.tipo is TipoTransacao.RECEITA
        assert item.valor == Decimal("35.50")
        assert item.confianca < Decimal("0.80")
        assert item.observacao is not None and "estorno" in item.observacao

    def test_cobranca_sem_cartao_nao_tem_final(self) -> None:
        """A Pluggy manda `0000` em IOF e juros. Final `0000` casaria com
        cartão nenhum e atrapalharia o enriquecimento."""
        item = _cartao("tarifa_sem_cartao")
        assert item.cartao_final is None
        assert item.tipo is TipoTransacao.DESPESA
        assert item.competencia == date(2025, 5, 1)

    def test_pendente_e_recusada_na_conversao_unitaria(self) -> None:
        with pytest.raises(ValueError, match="POSTED"):
            _cartao("pendente")


class TestConta:
    def test_debito(self) -> None:
        item = _conta("debito")
        assert item.tipo is TipoTransacao.DESPESA
        assert item.direcao == "saida"
        assert item.valor == Decimal("45.10")
        assert item.data == date(2025, 3, 18)
        assert item.competencia == date(2025, 3, 1)
        assert item.confianca == Decimal("0.95")
        assert item.cartao_final is None
        assert item.linha_bruta == "Compra no débito|MERCADO EXEMPLO"

    def test_credito(self) -> None:
        item = _conta("credito")
        assert item.tipo is TipoTransacao.RECEITA
        assert item.direcao == "entrada"
        assert item.valor == Decimal("300.00")

    def test_pagamento_de_fatura_vira_transferencia_de_saida(self) -> None:
        item = _conta("pagamento_de_fatura")
        assert item.tipo is TipoTransacao.TRANSFERENCIA
        assert item.direcao == "saida"
        assert item.confianca < Decimal("0.80")
        assert item.observacao is not None and "D-05" in item.observacao

    def test_pagamento_de_fatura_por_debito_automatico(self) -> None:
        """Categoria `Loans and financing`, operação `OUTROS`: só a descrição
        diz que é pagamento de fatura."""
        assert _conta("pagamento_de_fatura_por_debito").tipo is TipoTransacao.TRANSFERENCIA

    def test_transferencia_para_a_mesma_pessoa(self) -> None:
        item = _conta("mesma_pessoa")
        assert item.tipo is TipoTransacao.TRANSFERENCIA
        assert item.direcao == "saida"
        assert item.confianca < Decimal("0.80")
        assert item.observacao is not None and "mesma pessoa" in item.observacao

    def test_virada_de_mes_no_fuso(self) -> None:
        """02:01 UTC de 01/03 é 23:01 de 28/02: a competência é fevereiro."""
        item = _conta("virada_de_mes")
        assert item.data == date(2025, 2, 28)
        assert item.competencia == date(2025, 2, 1)

    def test_pix_para_terceiro_e_despesa(self) -> None:
        assert _conta("virada_de_mes").tipo is TipoTransacao.DESPESA


class TestSentido:
    def test_sinal_contraditorio_segue_o_tipo_e_baixa_a_confianca(self) -> None:
        item = _conta("debito", amount=Decimal("45.10"))
        assert item.tipo is TipoTransacao.DESPESA
        assert item.confianca == Decimal("0.50")
        assert item.observacao is not None and "contradiz" in item.observacao

    def test_sem_tipo_deduz_do_sinal_com_confianca_baixa(self) -> None:
        conta = _conta("debito", type=None)
        assert conta.tipo is TipoTransacao.DESPESA
        assert conta.confianca == Decimal("0.50")

        # No cartão a convenção inverte: positivo é compra.
        cartao = converter(_tx("transacoes_cartao", "compra_simples", type=None), CARTAO, FATURAS)
        assert cartao.tipo is TipoTransacao.DESPESA

    def test_moeda_estrangeira_usa_o_valor_convertido(self) -> None:
        item = converter(
            _tx(
                "transacoes_cartao",
                "compra_simples",
                currencyCode="USD",
                amount=Decimal("10.00"),
                amountInAccountCurrency=Decimal("55.32"),
            ),
            CARTAO,
            FATURAS,
        )
        assert item.valor == Decimal("55.32")
        assert item.observacao is not None and "USD" in item.observacao

    def test_transacao_de_outra_conta_e_recusada(self) -> None:
        with pytest.raises(ValueError, match="não é da conta"):
            converter(_tx("transacoes_cartao", "compra_simples"), CORRENTE, FATURAS)


class TestLote:
    def test_pendente_e_ignorada_e_contada(self) -> None:
        transacoes = [Transacao.model_validate(t) for t in DADOS["transacoes_cartao"].values()]
        resultado = converter_lote(
            transacoes, CARTAO, FATURAS.values(), dia_fechamento=3, dia_vencimento=10
        )
        assert resultado.pendentes_ignoradas == 1
        assert resultado.outras_ignoradas == 0
        assert len(resultado.itens) == len(transacoes) - 1
        assert "00000000-0000-4000-8000-00000000a009" not in {i.id_externo for i in resultado.itens}
        assert [i.linha_num for i in resultado.itens] == list(range(1, len(resultado.itens) + 1))

    def test_status_desconhecido_e_valor_zero_ficam_de_fora_com_aviso(self) -> None:
        resultado = converter_lote(
            [
                _tx("transacoes_conta", "debito", status="CANCELLED"),
                _tx("transacoes_conta", "credito", amount=0),
                _tx("transacoes_conta", "virada_de_mes"),
            ],
            CORRENTE,
        )
        assert len(resultado.itens) == 1
        assert resultado.outras_ignoradas == 2
        assert len(resultado.avisos) == 2

    def test_todo_item_tem_valor_positivo_e_competencia_no_dia_1(self) -> None:
        transacoes = [
            Transacao.model_validate(t)
            for t in DADOS["transacoes_cartao"].values()
            if t["status"] == "POSTED"
        ]
        for item in converter_lote(transacoes, CARTAO, FATURAS.values()).itens:
            assert item.valor > 0
            assert item.competencia is not None and item.competencia.day == 1


@pytest.mark.parametrize(
    ("compra", "fechamento", "vencimento", "esperado"),
    [
        (date(2025, 3, 2), 3, 10, date(2025, 3, 1)),  # antes do fechamento
        (date(2025, 3, 3), 3, 10, date(2025, 4, 1)),  # no dia do fechamento
        (date(2025, 12, 26), 25, 5, date(2026, 2, 1)),  # vence no mês seguinte ao fechamento
        (date(2025, 12, 10), 25, 5, date(2026, 1, 1)),
    ],
)
def test_estimar_competencia(
    compra: date, fechamento: int, vencimento: int, esperado: date
) -> None:
    assert estimar_competencia(compra, fechamento, vencimento) == esperado


def test_fixture_e_anonimizada() -> None:
    """Repositório público: nenhum id real, nenhum final de cartão real."""
    texto = FIXTURE.read_text("utf-8")
    for uuid in re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", texto):
        assert uuid.startswith("00000000-0000-4000-8000-"), uuid
    for final in re.findall(r'"(?:cardNumber|number)": "([^"]+)"', texto):
        assert final in {"0000", "1111", "2222", "0000-1"}, final


def test_conversao_e_pura() -> None:
    """Sem banco, sem HTTP, sem service: só os dois contratos e a stdlib."""
    fonte = Path(__file__).parents[1] / "app" / "conversao_pluggy.py"
    permitidos = {"app.enums", "app.ingestao.base", "app.pluggy.modelos"}
    for no in ast.walk(ast.parse(fonte.read_text("utf-8"))):
        if isinstance(no, ast.ImportFrom) and no.module and no.module.startswith("app"):
            assert no.module in permitidos, no.module
        if isinstance(no, ast.Import | ast.ImportFrom):
            nomes = [a.name for a in no.names] if isinstance(no, ast.Import) else [no.module or ""]
            for nome in nomes:
                assert not nome.startswith(("sqlalchemy", "httpx", "psycopg", "fastapi")), nome
