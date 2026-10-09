"""Schemas do mapeamento de contas da Pluggy (fase 5b, passo 4).

Os ids da Pluggy não entram no `Update`: trocar a conta da Pluggy de um
mapeamento é criar outro, e desativar o antigo. Assim a auditoria mostra as
duas coisas separadas, em vez de um mapeamento que muda de identidade.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

IdPluggy = Annotated[str, Field(min_length=1, max_length=100)]


class ContaPluggyCreate(BaseModel):
    pluggy_item_id: IdPluggy
    pluggy_account_id: IdPluggy
    conta_id: int
    #: Tem que pertencer a `conta_id`. Para cartão, a forma `credito` dele.
    forma_pagamento_id: int
    #: A partir desta data a Pluggy é a origem da conta; antes, o PDF.
    sincronizar_desde: date
    ativo: bool = True


class ContaPluggyUpdate(BaseModel):
    conta_id: int | None = None
    forma_pagamento_id: int | None = None
    sincronizar_desde: date | None = None
    ativo: bool | None = None


class ContaPluggyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criado_em: datetime
    atualizado_em: datetime | None = None
    pluggy_item_id: str
    pluggy_account_id: str
    conta_id: int
    forma_pagamento_id: int
    sincronizar_desde: date
    ultimo_sync_em: datetime | None = None
    ativo: bool
    #: Sobreposição com PDF já promovido nesta conta (D-16). Aviso, não
    #: bloqueio: o mapeamento é gravado mesmo assim.
    avisos: list[str] = Field(default_factory=list)


# --- categorias (D-21) -------------------------------------------------------


class CategoriaPluggyCreate(BaseModel):
    #: `categoryId` da Pluggy, 8 dígitos (ex. `11000000`).
    pluggy_categoria_id: Annotated[str, Field(min_length=1, max_length=20, pattern=r"^\d+$")]
    #: `category`, a descrição em inglês (ex. "Groceries").
    pluggy_categoria_nome: Annotated[str, Field(min_length=1, max_length=200)]
    categoria_id: int
    ativo: bool = True


class CategoriaPluggyUpdate(BaseModel):
    """Trocar o id da Pluggy é criar outro mapeamento, como em `contas_pluggy`."""

    pluggy_categoria_nome: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    categoria_id: int | None = None
    ativo: bool | None = None


class CategoriaPluggyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criado_em: datetime
    atualizado_em: datetime | None = None
    pluggy_categoria_id: str
    pluggy_categoria_nome: str
    categoria_id: int
    ativo: bool
