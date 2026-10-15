"""Investigação dos resgates da Pluggy — a parte pura, sem banco."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.pluggy.modelos import Transacao
from scripts.pluggy_resgates import (
    SEM_ITEM,
    Analise,
    Gravado,
    Linha,
    Movimento,
    analisar,
    casar,
    concluir,
    e_aplicacao,
    imprimir,
    movimentos_de,
)

DIA = date(2026, 9, 15)
RESGATE = "RESGATE_APLIC_FINANCEIRA"


def _m(
    id_: str,
    valor: str,
    *,
    entrada: bool,
    operacao: str | None = "PIX",
    conta: str = "c1",
    dia: date = DIA,
) -> Movimento:
    return Movimento(
        id=id_,
        conta=conta,
        dia=dia,
        valor=Decimal(valor),
        entrada=entrada,
        operacao=operacao,
        categoria=None,
    )


@pytest.mark.parametrize(
    ("operacao", "esperado"),
    [
        (RESGATE, True),
        ("APLICACAO_FINANCEIRA", True),
        ("resgate_aplic_financeira", True),
        ("PIX", False),
        ("CARTAO", False),
        (None, False),
    ],
)
def test_e_aplicacao(operacao: str | None, esperado: bool) -> None:
    assert e_aplicacao(operacao) is esperado


class TestCasar:
    def test_saida_de_mesmo_valor(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        assert casar(r, [r, _m("s", "50.00", entrada=False)]) == "igual"

    def test_soma_de_todas(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        do_dia = [r, _m("a", "30.00", entrada=False), _m("b", "20.05", entrada=False)]
        assert casar(r, do_dia) == "soma_proxima"

    def test_soma_de_um_subconjunto(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        do_dia = [
            r,
            _m("a", "30.00", entrada=False),
            _m("b", "20.00", entrada=False),
            _m("c", "300.00", entrada=False),
        ]
        assert casar(r, do_dia) == "soma_proxima"

    def test_saidas_maiores_cobrem_parte(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        do_dia = [r, _m("a", "120.00", entrada=False), _m("b", "300.00", entrada=False)]
        assert casar(r, do_dia) == "cobre_parte"

    def test_saidas_menores_sem_relacao(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        assert casar(r, [r, _m("a", "10.00", entrada=False)]) == "sem_relacao"

    def test_outra_conta_outro_dia_e_mesmo_sentido_nao_contam(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        do_dia = [
            r,
            _m("conta", "50.00", entrada=False, conta="c2"),
            _m("dia", "50.00", entrada=False, dia=date(2026, 9, 16)),
            _m("entrada", "50.00", entrada=True),
        ]
        assert casar(r, do_dia) == "sem_contraparte"

    def test_aplicacao_nao_e_contraparte_de_resgate(self) -> None:
        r = _m("r", "50.00", entrada=True, operacao=RESGATE)
        aplicacao = _m("a", "50.00", entrada=False, operacao="APLICACAO_FINANCEIRA")
        assert casar(r, [r, aplicacao]) == "sem_contraparte"

    def test_aplicacao_casa_com_entrada(self) -> None:
        a = _m("a", "800.00", entrada=False, operacao="APLICACAO_FINANCEIRA")
        assert casar(a, [a, _m("pix", "800.00", entrada=True)]) == "igual"


def test_movimentos_de_pula_pendente_e_usa_o_dia_de_sao_paulo() -> None:
    base = {
        "accountId": "c1",
        "amount": Decimal("-12.34"),
        "type": "DEBIT",
        "operationType": "PIX",
    }
    confirmada = Transacao.model_validate(
        {**base, "id": "t1", "status": "POSTED", "date": "2026-09-16T02:00:00Z"}
    )
    pendente = Transacao.model_validate(
        {**base, "id": "t2", "status": "PENDING", "date": "2026-09-16T15:00:00Z"}
    )
    [m] = movimentos_de([confirmada, pendente])
    assert m.dia == date(2026, 9, 15)  # 23h de 15/09 em São Paulo
    assert m.valor == Decimal("12.34") and not m.entrada
    assert confirmada.date.tzinfo is not None
    assert datetime(2026, 9, 16, 2, tzinfo=UTC) == confirmada.date


def _linha(valor: str, contraparte: str, gravado: Gravado = SEM_ITEM) -> Linha:
    return Linha(
        movimento=_m("x", valor, entrada=True, operacao=RESGATE),
        conta="Conta",
        gravado=gravado,
        contraparte=contraparte,
    )


class TestConcluir:
    def test_sem_resgate(self) -> None:
        assert concluir(Analise())[0] == "SEM DADOS"

    def test_maioria_casada_sustenta(self) -> None:
        analise = Analise(
            [_linha("50", "igual"), _linha("20", "soma_proxima"), _linha("5", "sem_contraparte")]
        )
        veredito, texto = concluir(analise)
        assert veredito == "SUSTENTA-SE"
        assert any("não contar resgate" in t for t in texto)

    def test_compativel_sustenta_em_parte(self) -> None:
        analise = Analise(
            [_linha("50", "igual"), _linha("20", "cobre_parte"), _linha("5", "sem_relacao")]
        )
        assert concluir(analise)[0] == "SUSTENTA-SE EM PARTE"

    def test_centavos_em_dia_de_saida_maior_nao_contam_como_compativeis(self) -> None:
        analise = Analise([_linha("0.01", "cobre_parte")] * 2 + [_linha("50", "igual")])
        assert concluir(analise)[0] == "NÃO SE SUSTENTA COMO DESCRITA"

    def test_centavos_sozinhos_nao_sustentam(self) -> None:
        analise = Analise([_linha("0.01", "sem_contraparte")] * 3 + [_linha("50", "igual")])
        veredito, texto = concluir(analise)
        assert veredito == "NÃO SE SUSTENTA COMO DESCRITA"
        assert any("rendimento" in t for t in texto)

    def test_conta_as_que_viraram_receita(self) -> None:
        receita = Gravado(tipo="receita", status="aprovado", virou_transacao=True)
        analise = Analise([_linha("50", "igual", receita), _linha("50", "igual")])
        _, texto = concluir(analise)
        assert "1 de 2 resgates (somando R$ 100,00) viraram transação de receita" in texto[1]


def test_analisar_so_pega_aplicacao_e_imprime_sem_descricao(
    capsys: pytest.CaptureFixture[str],
) -> None:
    movimentos = [
        _m("r1", "0.01", entrada=True, operacao=RESGATE),
        _m("r2", "75.00", entrada=True, operacao=RESGATE, dia=date(2026, 10, 2)),
        _m("s2", "75.00", entrada=False, dia=date(2026, 10, 2)),
        _m("pix", "10.00", entrada=False),
    ]
    gravado = Gravado(tipo="receita", status="aprovado", virou_transacao=True)
    analise = analisar(movimentos, {"r2": gravado}, {"c1": "Banco A (BANK)"})

    assert [linha.movimento.id for linha in analise.linhas] == ["r1", "r2"]
    assert [linha.contraparte for linha in analise.linhas] == ["cobre_parte", "igual"]

    imprimir(analise)
    saida = capsys.readouterr().out
    assert "2026-09  Banco A (BANK)  RESGATE_APLIC_FINANCEIRA: 1 somando R$ 0,01" in saida
    assert "2026-10  Banco A (BANK)  RESGATE_APLIC_FINANCEIRA: 1 somando R$ 75,00" in saida
    assert "receita, item aprovado, virou transação" in saida
    assert "sem item no staging" in saida
    assert "Nada foi gravado." in saida
