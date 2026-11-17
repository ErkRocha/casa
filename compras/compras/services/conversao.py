"""Conversão de unidades do cardápio (modelo-cardapio.md, "Unidades").

Funções puras, tudo em `Decimal` (nunca float). A tabela é fixa no código;
o que ela não cobre devolve `None`, e quem chama põe o item na lista sem
quantidade, com aviso.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from compras.enums import MedidaBase, UnidadeMedida

UM = Decimal(1)
_MIL = Decimal(1000)
_TRES_CASAS = Decimal("0.001")
_SEIS_CASAS = Decimal("0.000001")

#: Unidade da receita -> (dimensão, quanto vale na base dessa dimensão).
_PARA_BASE: dict[UnidadeMedida, tuple[MedidaBase, Decimal]] = {
    UnidadeMedida.G: (MedidaBase.G, Decimal(1)),
    UnidadeMedida.KG: (MedidaBase.G, _MIL),
    UnidadeMedida.ML: (MedidaBase.ML, Decimal(1)),
    UnidadeMedida.L: (MedidaBase.ML, _MIL),
    UnidadeMedida.COLHER_SOPA: (MedidaBase.ML, Decimal(15)),
    UnidadeMedida.COLHER_CHA: (MedidaBase.ML, Decimal(5)),
    UnidadeMedida.XICARA: (MedidaBase.ML, Decimal(240)),
    UnidadeMedida.UN: (MedidaBase.UN, Decimal(1)),
}

#: `unidade_padrao` que se converte direto da base: (base exigida, divisor).
_COMPRA_DIRETA: dict[str, tuple[MedidaBase, Decimal]] = {
    "kg": (MedidaBase.G, _MIL),
    "g": (MedidaBase.G, Decimal(1)),
    "l": (MedidaBase.ML, _MIL),
    "ml": (MedidaBase.ML, Decimal(1)),
}


def tres_casas(valor: Decimal) -> Decimal:
    """`numeric(12,3)`: o que a lista guarda."""
    return valor.quantize(_TRES_CASAS, rounding=ROUND_HALF_UP)


def para_base_produto(
    quantidade: Decimal,
    unidade: UnidadeMedida,
    medida_base: MedidaBase | None,
    medida_por_unidade: Decimal | None,
) -> Decimal | None:
    """A quantidade da receita na base do produto, ou `None` se não converte.

    1. mesma dimensão (g com g, ml com ml, un com un): tabela fixa;
    2. receita em `un`, produto em g/ml: vezes `medida_por_unidade`;
    3. receita em g/ml, produto em `un`: dividido por `medida_por_unidade`;
    4. massa com volume, ou falta o dado: não converte.
    """
    if medida_base is None or unidade == UnidadeMedida.A_GOSTO:
        return None
    dimensao, fator = _PARA_BASE[unidade]
    valor = quantidade * fator
    if dimensao == medida_base:
        return valor
    if medida_por_unidade is None or medida_por_unidade <= 0:
        return None
    if dimensao == MedidaBase.UN and medida_base in (MedidaBase.G, MedidaBase.ML):
        return valor * medida_por_unidade
    if medida_base == MedidaBase.UN and dimensao in (MedidaBase.G, MedidaBase.ML):
        return valor / medida_por_unidade
    return None


def para_compra(
    total_base: Decimal,
    medida_base: MedidaBase | None,
    medida_por_unidade: Decimal | None,
    unidade_padrao: str | None,
) -> tuple[Decimal, str] | None:
    """O total na base vira a unidade em que o produto se compra.

    `kg`, `g`, `l` e `ml` (sem diferença de caixa) convertem direto. Qualquer
    outra (`un`, `pct`...) divide por `medida_por_unidade` e arredonda **para
    cima**: embalagem não se compra pela metade. `None` se falta o dado.
    """
    if medida_base is None:
        return None
    rotulo = (unidade_padrao or "un").strip() or "un"
    direta = _COMPRA_DIRETA.get(rotulo.lower())
    if direta is not None:
        base_exigida, divisor = direta
        if medida_base != base_exigida:
            return None
        return tres_casas(total_base / divisor), rotulo

    por_unidade = medida_por_unidade
    if por_unidade is None and medida_base == MedidaBase.UN:
        por_unidade = Decimal(1)
    if por_unidade is None or por_unidade <= 0:
        return None
    # Seis casas antes de arredondar: a divisão de frações (1/3 de receita) deixa
    # resíduo de 1e-28, que não pode custar uma embalagem a mais.
    exato = (total_base / por_unidade).quantize(_SEIS_CASAS, rounding=ROUND_HALF_UP)
    unidades = exato.to_integral_value(rounding=ROUND_CEILING)
    return tres_casas(unidades), rotulo


def converte(
    quantidade: Decimal,
    unidade: UnidadeMedida,
    medida_base: MedidaBase | None,
    medida_por_unidade: Decimal | None,
    unidade_padrao: str | None,
) -> bool:
    """A linha chega à lista com quantidade? `a_gosto` não tem o que converter."""
    if unidade == UnidadeMedida.A_GOSTO:
        return True
    base = para_base_produto(quantidade, unidade, medida_base, medida_por_unidade)
    if base is None:
        return False
    return para_compra(base, medida_base, medida_por_unidade, unidade_padrao) is not None


def motivo_sem_conversao(
    unidade: UnidadeMedida, medida_base: MedidaBase | None, medida_por_unidade: Decimal | None
) -> str:
    """Por que a linha não converte, em uma frase para a fila "cadastre a medida"."""
    if medida_base is None:
        return "sem medida_base"
    if medida_por_unidade is None:
        return "sem medida_por_unidade"
    return f"{unidade.value} não converte para {medida_base.value}"
