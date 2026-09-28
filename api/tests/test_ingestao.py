"""Parsers de ingestão, contra os PDFs reais.

O gabarito não fui eu que escrevi: é o total que o próprio documento declara.
Se o parser perder uma linha, a soma deixa de bater e o teste quebra — sem
depender de eu ter contado certo na mão.

Os PDFs são extratos de verdade e ficam fora do git. Sem eles os testes de
arquivo real são pulados; os testes de unidade continuam rodando.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.enums import TipoTransacao
from app.ingestao import FormatoDesconhecido, escolher_parser, extrair_texto, processar
from app.ingestao.base import valor_brl
from app.ingestao.nubank_extrato import NubankExtratoParser
from app.ingestao.nubank_fatura import NubankFaturaParser

FATURAS = Path(__file__).resolve().parents[2] / "faturas"


def _pdfs(padrao: str) -> list[Path]:
    return sorted(FATURAS.glob(padrao)) if FATURAS.exists() else []


faturas = _pdfs("Nubank_*.pdf")
extratos = _pdfs("NU_*.pdf")

sem_pdfs = pytest.mark.skipif(
    not faturas and not extratos,
    reason="faturas/ vazia — os PDFs reais não são versionados",
)


class TestValorBRL:
    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("R$ 1.234,56", Decimal("1234.56")),
            ("1.234,56", Decimal("1234.56")),
            ("50,00", Decimal("50.00")),
            ("−R$ 1.074,01", Decimal("-1074.01")),  # minus unicode do PDF
            ("-R$ 10,00", Decimal("-10.00")),
            ("R$ 0,00", Decimal("0.00")),
        ],
    )
    def test_converte(self, texto: str, esperado: Decimal) -> None:
        assert valor_brl(texto) == esperado

    def test_nao_perde_centavo(self) -> None:
        """Decimal desde a primeira linha — float aqui já teria arredondado."""
        assert valor_brl("0,07") + valor_brl("0,07") + valor_brl("0,07") == Decimal("0.21")


class TestDeteccao:
    @sem_pdfs
    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_fatura_e_reconhecida(self, caminho: Path) -> None:
        parser = escolher_parser(extrair_texto(caminho.read_bytes()))
        assert isinstance(parser, NubankFaturaParser)

    @sem_pdfs
    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_extrato_e_reconhecido(self, caminho: Path) -> None:
        parser = escolher_parser(extrair_texto(caminho.read_bytes()))
        assert isinstance(parser, NubankExtratoParser)

    def test_formato_desconhecido_falha_alto(self) -> None:
        """Melhor recusar do que adivinhar (D-08)."""
        with pytest.raises(FormatoDesconhecido):
            escolher_parser("boleto qualquer de outro banco")


@sem_pdfs
class TestFatura:
    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_soma_bate_com_total_declarado(self, caminho: Path) -> None:
        """O teste que vale: a soma extraída == 'Total a pagar' do PDF."""
        doc = processar(caminho.read_bytes())
        assert doc.total_declarado is not None, "não achei o total no documento"
        assert doc.soma_itens == doc.total_declarado
        assert doc.confere is True

    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_sem_avisos_de_linha_perdida(self, caminho: Path) -> None:
        doc = processar(caminho.read_bytes())
        assert doc.avisos == [], f"linhas não reconhecidas: {doc.avisos}"

    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_competencia_e_o_mes_do_vencimento(self, caminho: Path) -> None:
        """Compra de 04 JUN na fatura que vence em julho é despesa de julho
        (D-02)."""
        doc = processar(caminho.read_bytes())
        assert doc.competencia is not None
        assert doc.competencia.day == 1
        assert doc.periodo_fim is not None
        assert doc.competencia >= doc.periodo_fim.replace(day=1)

    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_todo_item_tem_data_dentro_do_periodo(self, caminho: Path) -> None:
        """Pega erro de inferência de ano — o principal risco da fatura, que
        não escreve o ano na linha."""
        doc = processar(caminho.read_bytes())
        assert doc.periodo_inicio is not None and doc.periodo_fim is not None
        for item in doc.itens:
            assert doc.periodo_inicio <= item.data <= doc.periodo_fim, item.linha_bruta

    @pytest.mark.parametrize("caminho", faturas, ids=lambda p: p.name)
    def test_valores_positivos_e_com_descricao(self, caminho: Path) -> None:
        doc = processar(caminho.read_bytes())
        assert doc.itens, "nenhum item extraído"
        for item in doc.itens:
            assert item.valor > 0, item.linha_bruta
            assert item.descricao.strip(), item.linha_bruta

    def test_pagamento_da_fatura_anterior_nao_vira_lancamento(self) -> None:
        """ "Pagamento em 05 JUN" quita a fatura passada; não é compra deste
        mês. Contá-lo estourava o total exatamente no valor da fatura
        anterior."""
        for caminho in faturas:
            doc = processar(caminho.read_bytes())
            assert not any(item.descricao.lower().startswith("pagamento em") for item in doc.itens)
            assert not any("saldo restante" in item.descricao.lower() for item in doc.itens)


@sem_pdfs
class TestExtrato:
    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_entradas_e_saidas_batem_com_o_declarado(self, caminho: Path) -> None:
        doc = processar(caminho.read_bytes())
        assert doc.total_entradas == doc.total_entradas_declarado
        assert doc.total_saidas == doc.total_saidas_declarado
        assert doc.confere is True

    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_toda_transferencia_tem_direcao(self, caminho: Path) -> None:
        """Sem direção não dá para montar origem e destino, e `transacoes`
        exige as duas."""
        doc = processar(caminho.read_bytes())
        for item in doc.itens:
            if item.tipo is TipoTransacao.TRANSFERENCIA:
                assert item.direcao in {"entrada", "saida"}, item.linha_bruta

    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_pagamento_de_fatura_vira_transferencia(self, caminho: Path) -> None:
        """A regra que evita contar o cartão duas vezes (D-05).

        O gasto detalhado vem da fatura; no extrato, o pagamento é só dinheiro
        mudando de lugar.
        """
        doc = processar(caminho.read_bytes())
        pagamentos = [item for item in doc.itens if "pagamento de fatura" in item.descricao.lower()]
        for item in pagamentos:
            assert item.tipo is TipoTransacao.TRANSFERENCIA, item.linha_bruta

    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_transferencia_fica_fora_do_gasto(self, caminho: Path) -> None:
        doc = processar(caminho.read_bytes())
        so_gasto = sum(
            (item.valor for item in doc.itens if item.tipo is TipoTransacao.DESPESA),
            Decimal("0"),
        )
        assert so_gasto <= doc.total_saidas

    @pytest.mark.parametrize("caminho", extratos, ids=lambda p: p.name)
    def test_datas_dentro_do_periodo(self, caminho: Path) -> None:
        doc = processar(caminho.read_bytes())
        assert doc.periodo_inicio is not None and doc.periodo_fim is not None
        for item in doc.itens:
            assert doc.periodo_inicio <= item.data <= doc.periodo_fim, item.linha_bruta


@sem_pdfs
def test_pdf_nunca_sai_da_maquina() -> None:
    """Guarda de arquitetura (D-08).

    O módulo de ingestão não pode ter cliente HTTP nem SDK de modelo: o
    `pdfplumber` extrai local, e só texto — nunca o arquivo — segue adiante.
    """
    import app.ingestao as pacote

    fonte = Path(pacote.__file__).parent
    proibidos = ("import requests", "import httpx", "import anthropic", "import openai")
    for arquivo in fonte.glob("*.py"):
        conteudo = arquivo.read_text(encoding="utf-8")
        for proibido in proibidos:
            assert proibido not in conteudo, f"{arquivo.name} faz rede: {proibido}"
