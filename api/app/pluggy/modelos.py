"""Respostas da Pluggy, tipadas.

Os nomes dos campos seguem a API em snake_case (`accountId` vira
`account_id`), para que o caminho até a documentação seja direto. Só estão
aqui campos que a documentação descreve; o resto fica acessível em
`model_extra`, porque `extra="allow"` — a Pluggy acrescenta campo sem aviso, e
campo novo não pode derrubar a sync.

**Dinheiro é `Decimal` desde o primeiro byte** (regra 1). O JSON da Pluggy
traz valor como número, e `json.loads` comum o transformaria em `float` antes
de qualquer validação — o centavo já estaria perdido quando o Pydantic visse o
valor. O cliente decodifica com `parse_float=Decimal`, então aqui só chega
`Decimal` ou `int`. Isso vale também para dinheiro dentro de campo não tipado
(`financeCharges`, `paymentData`, extras).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Modelo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="allow", frozen=True)


# --- items ------------------------------------------------------------------


class Conector(_Modelo):
    id: int
    name: str
    type: str | None = None
    is_open_finance: bool | None = None


class Item(_Modelo):
    """Uma conexão. No MeuPluggy, é o *proxy item* criado na aplicação."""

    id: str
    status: str | None = None
    execution_status: str | None = None
    connector: Conector | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_updated_at: datetime | None = None
    next_auto_sync_at: datetime | None = None
    products: list[str] = Field(default_factory=list)


# --- contas -----------------------------------------------------------------


class DadosBancarios(_Modelo):
    transfer_number: str | None = None
    closing_balance: Decimal | None = None


class DadosCredito(_Modelo):
    level: str | None = None
    brand: str | None = None
    balance_close_date: datetime | None = None
    balance_due_date: datetime | None = None
    available_credit_limit: Decimal | None = None
    credit_limit: Decimal | None = None
    minimum_payment: Decimal | None = None
    status: str | None = None
    holder_type: str | None = None


class Conta(_Modelo):
    id: str
    item_id: str
    #: `BANK` ou `CREDIT`.
    type: str
    #: Ex. `CHECKING_ACCOUNT`, `SAVINGS_ACCOUNT`, `CREDIT_CARD`.
    subtype: str | None = None
    name: str | None = None
    marketing_name: str | None = None
    number: str | None = None
    balance: Decimal | None = None
    currency_code: str | None = None
    owner: str | None = None
    tax_number: str | None = None
    bank_data: DadosBancarios | None = None
    credit_data: DadosCredito | None = None

    @property
    def e_cartao(self) -> bool:
        return self.type == "CREDIT"


# --- transações ---------------------------------------------------------------


class MetadadosCartao(_Modelo):
    installment_number: int | None = None
    total_installments: int | None = None
    total_amount: Decimal | None = None
    payee_mcc: int | None = Field(default=None, alias="payeeMCC")
    purchase_date: datetime | None = None
    #: Pode diferir do cartão da conta: cartão adicional ou virtual.
    card_number: str | None = None
    #: Fatura a que a transação pertence. Documentado como "só em conectores
    #: Open Finance"; via MeuPluggy, a confirmar com resposta real.
    bill_id: str | None = None


class Transacao(_Modelo):
    id: str
    account_id: str
    date: datetime
    amount: Decimal
    description: str | None = None
    description_raw: str | None = None
    currency_code: str | None = None
    amount_in_account_currency: Decimal | None = None
    balance: Decimal | None = None
    #: `PENDING` ou `POSTED`. Fica `str`, não enum: valor novo não pode
    #: derrubar a leitura — quem decide o que fazer com ele é a conversão.
    status: str | None = None
    #: `DEBIT` ou `CREDIT`.
    type: str | None = None
    category: str | None = None
    category_id: str | None = None
    provider_code: str | None = None
    provider_id: str | None = None
    operation_type: str | None = None
    payment_data: dict[str, Any] | None = None
    credit_card_metadata: MetadadosCartao | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def pendente(self) -> bool:
        return self.status == "PENDING"


# --- faturas ------------------------------------------------------------------


class Fatura(_Modelo):
    id: str
    due_date: datetime
    total_amount: Decimal
    bill_closing_date: datetime | None = None
    total_amount_currency_code: str | None = None
    minimum_payment_amount: Decimal | None = None
    allows_installments: bool | None = None
    finance_charges: list[dict[str, Any]] = Field(default_factory=list)
    payments: list[dict[str, Any]] = Field(default_factory=list)
