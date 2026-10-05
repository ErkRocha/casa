"""Mapeamento de contas da Pluggy (fase 5b, passo 4; D-16).

Liga uma conta da Pluggy a uma `conta` daqui e à forma de pagamento padrão
dos itens que ela vai gerar. Conta da Pluggy sem mapeamento é ignorada pela
sync, nunca adivinhada.

O encaixe espelha o que o PDF já faz: cartão de crédito não é `conta`
própria, é uma forma `credito` cuja `conta_id` é a conta corrente que paga a
fatura. Uma conta `CREDIT` da Pluggy, portanto, aponta para essa conta
corrente, com a forma de crédito daquele cartão. Por isso a validação central
daqui é a mesma para cartão e conta corrente: a forma tem que ser da conta.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select

from app.models import Conta, ContaPluggy, FormaPagamento, Importacao, Transacao
from app.services.base import CrudService, RegraViolada

#: Campos que o PATCH não pode zerar: são NOT NULL, e o erro do banco seria
#: menos claro que este.
_OBRIGATORIOS = ("conta_id", "forma_pagamento_id", "sincronizar_desde")


class ContaPluggyService(CrudService[ContaPluggy]):
    model = ContaPluggy
    nome_recurso = "mapeamento de conta Pluggy"

    def criar(self, dados: dict[str, Any]) -> ContaPluggy:
        self._checa_conta_e_forma(dados["conta_id"], dados["forma_pagamento_id"])
        return super().criar(dados)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> ContaPluggy:
        for campo in _OBRIGATORIOS:
            if campo in dados and dados[campo] is None:
                raise RegraViolada(f"'{campo}' é obrigatório no mapeamento.")

        obj = self.get(id_)
        if "conta_id" in dados or "forma_pagamento_id" in dados:
            self._checa_conta_e_forma(
                dados.get("conta_id", obj.conta_id),
                dados.get("forma_pagamento_id", obj.forma_pagamento_id),
            )
        return super().atualizar(id_, dados)

    def remover(self, id_: int) -> None:
        """Desativa: soft delete, e `ativo` falso junto.

        As duas coisas porque `ativo` é o que a sync consulta, e `deleted_em`
        é o que libera o `pluggy_account_id` para um mapeamento novo.
        """
        self.get(id_).ativo = False
        super().remover(id_)

    # -- regras ----------------------------------------------------------

    def _checa_conta_e_forma(self, conta_id: int, forma_pagamento_id: int) -> None:
        """A forma padrão tem que sair da conta mapeada.

        Sem isto, um mapeamento da conta do banco A com a forma de um cartão do
        banco B geraria itens cujo `forma_pagamento_id` aponta para outra
        conta — e é essa forma que entra no `hash_dedup` da promoção.
        """
        conta = self.session.get(Conta, conta_id)
        if conta is None or conta.deleted_em is not None:
            raise RegraViolada(f"Conta {conta_id} não existe.")
        if not conta.ativo:
            raise RegraViolada(f"A conta '{conta.nome}' está inativa.")

        forma = self.session.get(FormaPagamento, forma_pagamento_id)
        if forma is None or forma.deleted_em is not None:
            raise RegraViolada(f"Forma de pagamento {forma_pagamento_id} não existe.")
        if not forma.ativo:
            # O enriquecimento só carrega formas ativas: um mapeamento para
            # forma inativa geraria itens que a revisão não sabe mostrar.
            raise RegraViolada(f"A forma de pagamento '{forma.apelido}' está inativa.")
        if forma.conta_id != conta_id:
            raise RegraViolada(
                f"A forma de pagamento '{forma.apelido}' pertence à conta "
                f"{forma.conta_id}, não à conta '{conta.nome}' ({conta_id}). "
                "Escolha uma forma desta conta ou ajuste a conta da forma."
            )

    def avisos(self, obj: ContaPluggy) -> list[str]:
        """Sobreposição com PDF já promovido (D-16, uma origem por conta).

        O `hash_dedup` inclui a descrição original, e a da Pluggy não é a do
        PDF: a mesma compra, vinda das duas origens, passaria pela segunda
        barreira. Aqui só se avisa — bloquear impediria justamente o caso em
        que o PDF é o fallback de uma Pluggy que falhou.

        A transação chega à conta por `transacoes.conta_id` ou, como na
        importação de PDF (que não preenche a conta), pela conta da forma de
        pagamento.
        """
        total, primeira, ultima = self.session.execute(
            select(func.count(), func.min(Transacao.data), func.max(Transacao.data))
            .select_from(Transacao)
            .join(Importacao, Importacao.id == Transacao.importacao_id)
            .outerjoin(FormaPagamento, FormaPagamento.id == Transacao.forma_pagamento_id)
            .where(
                Transacao.deleted_em.is_(None),
                Transacao.data >= obj.sincronizar_desde,
                Importacao.origem.is_distinct_from("pluggy"),
                or_(Transacao.conta_id == obj.conta_id, FormaPagamento.conta_id == obj.conta_id),
            )
        ).one()
        if not total:
            return []
        return [
            f"Já existem {total} transação(ões) importadas de PDF nesta conta a partir de "
            f"{_br(obj.sincronizar_desde)} (de {_br(primeira)} a {_br(ultima)}). "
            "A partir dessa data a Pluggy passa a ser a origem da conta, e a mesma "
            "compra pode entrar duas vezes: a descrição da Pluggy difere da do PDF, e o "
            "hash_dedup não as reconhece como iguais. Confira essas transações ou mova "
            "'sincronizar_desde' para depois delas."
        ]

    def ids_mapeados(self) -> set[str]:
        """`pluggy_account_id` de todo mapeamento vivo, ativo ou não."""
        return set(
            self.session.scalars(
                select(ContaPluggy.pluggy_account_id).where(ContaPluggy.deleted_em.is_(None))
            )
        )


def _br(d: date) -> str:
    return f"{d:%d/%m/%Y}"
