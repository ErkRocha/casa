"""Pessoas do cardápio: quem come, e quanto por padrão (D-30)."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras import tempo
from compras.models import Pessoa, Refeicao, RefeicaoPessoa
from compras.schemas_cardapio import PessoaLeitura
from compras.services.base import Conflito, NaoEncontrado
from compras.services.identidades import IdentidadeService


def leitura(p: Pessoa) -> PessoaLeitura:
    return PessoaLeitura(
        id=p.id,
        nome=p.nome,
        porcao_padrao=p.porcao_padrao,
        identidade_id=p.identidade_id,
        login=p.identidade.login if p.identidade is not None else None,
        criado_em=p.criado_em,
        atualizado_em=p.atualizado_em,
        deleted_em=p.deleted_em,
    )


class PessoaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    def listar(self) -> list[Pessoa]:
        return list(
            self.session.scalars(
                select(Pessoa)
                .where(Pessoa.deleted_em.is_(None))
                .order_by(func.lower(Pessoa.nome), Pessoa.id)
                .execution_options(populate_existing=True)
            )
        )

    def get(self, id_: int) -> Pessoa:
        pessoa = self.session.scalar(
            select(Pessoa)
            .where(Pessoa.id == id_, Pessoa.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        if pessoa is None:
            raise NaoEncontrado("pessoa", id_)
        return pessoa

    def por_nome(self, nome: str) -> Pessoa | None:
        return self.session.scalar(
            select(Pessoa).where(
                func.lower(Pessoa.nome) == nome.strip().lower(), Pessoa.deleted_em.is_(None)
            )
        )

    def criar(
        self, nome: str, porcao_padrao: Decimal = Decimal(1), identidade_id: int | None = None
    ) -> Pessoa:
        if self.por_nome(nome) is not None:
            raise Conflito(f'Já existe a pessoa "{nome}".')
        self._identidade_livre(identidade_id, ignorar=None)
        pessoa = Pessoa(nome=nome.strip(), porcao_padrao=porcao_padrao, identidade_id=identidade_id)
        self._salvar(pessoa, nome, novo=True)
        return self.get(pessoa.id)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Pessoa:
        pessoa = self.get(id_)
        if dados.get("nome") is not None:
            outra = self.por_nome(dados["nome"])
            if outra is not None and outra.id != id_:
                raise Conflito(f'Já existe a pessoa "{outra.nome}".')
            pessoa.nome = dados["nome"].strip()
        if dados.get("porcao_padrao") is not None:
            pessoa.porcao_padrao = dados["porcao_padrao"]
        if "identidade_id" in dados:
            self._identidade_livre(dados["identidade_id"], ignorar=id_)
            pessoa.identidade_id = dados["identidade_id"]
        self._salvar(pessoa, pessoa.nome)
        return self.get(id_)

    def remover(self, id_: int) -> Pessoa:
        """Soft delete. Some das refeições de hoje em diante; as passadas mantêm a linha."""
        pessoa = self.get(id_)
        futuras = select(Refeicao.id).where(Refeicao.dia >= tempo.hoje())
        self.session.execute(
            update(RefeicaoPessoa)
            .where(
                RefeicaoPessoa.pessoa_id == id_,
                RefeicaoPessoa.deleted_em.is_(None),
                RefeicaoPessoa.refeicao_id.in_(futuras),
            )
            .values(deleted_em=func.now())
        )
        pessoa.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(pessoa)
        return pessoa

    # -- apoio -----------------------------------------------------------

    def _identidade_livre(self, identidade_id: int | None, ignorar: int | None) -> None:
        if identidade_id is None:
            return
        IdentidadeService(self.session).get(identidade_id)
        dona = self.session.scalar(
            select(Pessoa).where(Pessoa.identidade_id == identidade_id, Pessoa.deleted_em.is_(None))
        )
        if dona is not None and dona.id != ignorar:
            raise Conflito(f'Esse login já é de "{dona.nome}".')

    def _salvar(self, pessoa: Pessoa, nome: str, novo: bool = False) -> None:
        try:
            with self.session.begin_nested():
                if novo:
                    self.session.add(pessoa)
                self.session.flush()
        except IntegrityError as erro:
            raise Conflito(f'Já existe a pessoa "{nome}", ou o login já está em uso.') from erro
