"""Decisão do retroativo da D-21 por transação — sem banco.

O que mais importa aqui: a edição do usuário vence sempre, inclusive quando
a sugestão coincidiria com o que ele escolheu.
"""

from __future__ import annotations

import itertools

import pytest

from app.enums import TipoPagamento, TipoTransacao
from app.services.retroativo_pluggy import (
    EDITADA_PELO_USUARIO,
    decidir_categoria,
    decidir_forma,
)

DESPESA, RECEITA = TipoTransacao.DESPESA, TipoTransacao.RECEITA


class TestCategoria:
    def test_sem_categoria_e_sem_edicao_ganha_a_sugerida(self) -> None:
        assert decidir_categoria(
            categoria_atual=None, tipo=DESPESA, editada=False, sugerida=(7, DESPESA)
        ) == (7, None)

    def test_editada_nunca_muda(self) -> None:
        assert decidir_categoria(
            categoria_atual=None, tipo=DESPESA, editada=True, sugerida=(7, DESPESA)
        ) == (None, EDITADA_PELO_USUARIO)

    def test_com_categoria_nunca_muda(self) -> None:
        assert decidir_categoria(
            categoria_atual=3, tipo=DESPESA, editada=False, sugerida=(7, DESPESA)
        ) == (None, "já tem categoria")

    def test_tipo_diferente_nao_entra(self) -> None:
        assert decidir_categoria(
            categoria_atual=None, tipo=RECEITA, editada=False, sugerida=(7, DESPESA)
        ) == (None, "categoria sugerida de outro tipo")

    def test_transferencia_nao_tem_categoria(self) -> None:
        novo, motivo = decidir_categoria(
            categoria_atual=None,
            tipo=TipoTransacao.TRANSFERENCIA,
            editada=False,
            sugerida=(7, TipoTransacao.TRANSFERENCIA),
        )
        assert novo is None and motivo == "transferência não tem categoria"

    def test_sem_sugestao_fica_sem(self) -> None:
        assert decidir_categoria(
            categoria_atual=None, tipo=DESPESA, editada=False, sugerida=None
        ) == (None, "sem categoria pela ordem da D-21")

    @pytest.mark.parametrize(
        ("atual", "tipo", "sugerida"),
        list(
            itertools.product(
                [None, 3],
                list(TipoTransacao),
                [None, (7, DESPESA), (8, RECEITA)],
            )
        ),
    )
    def test_editada_nunca_ganha_categoria_em_combinacao_nenhuma(
        self,
        atual: int | None,
        tipo: TipoTransacao,
        sugerida: tuple[int, TipoTransacao] | None,
    ) -> None:
        novo, _ = decidir_categoria(
            categoria_atual=atual, tipo=tipo, editada=True, sugerida=sugerida
        )
        assert novo is None


class TestForma:
    def _decidir(self, **mudar: object) -> str | None:
        args: dict[str, object] = {
            "e_cartao": False,
            "forma_tipo": TipoPagamento.DEBITO,
            "forma_atual_id": 1,
            "resolvida_id": 2,
            "nova": False,
            "editada": False,
            "colide": False,
        }
        args.update(mudar)
        return decidir_forma(**args)  # type: ignore[arg-type]

    def test_debito_boleto_e_transferencia_mudam(self) -> None:
        for tipo in (TipoPagamento.DEBITO, TipoPagamento.BOLETO, TipoPagamento.TRANSFERENCIA):
            assert self._decidir(forma_tipo=tipo) is None

    def test_forma_nova_muda(self) -> None:
        assert self._decidir(resolvida_id=None, nova=True) is None

    def test_editada_nunca_muda(self) -> None:
        assert self._decidir(editada=True) == EDITADA_PELO_USUARIO
        assert self._decidir(editada=True, resolvida_id=None, nova=True) == EDITADA_PELO_USUARIO

    @pytest.mark.parametrize("tipo", [TipoPagamento.PIX, None, TipoPagamento.CREDITO])
    def test_pix_e_operacao_sem_forma_ficam(self, tipo: TipoPagamento | None) -> None:
        assert self._decidir(forma_tipo=tipo) == "operação sem forma a corrigir"

    def test_cartao_fica(self) -> None:
        assert self._decidir(e_cartao=True) == "cartão: forma do mapeamento"

    def test_ja_certa_fica(self) -> None:
        assert self._decidir(resolvida_id=1) == "forma já certa"

    def test_colisao_fica(self) -> None:
        assert self._decidir(colide=True) == "colidiria com transação idêntica"
