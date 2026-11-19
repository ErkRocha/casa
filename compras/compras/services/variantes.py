"""Variantes: o item exato que se compra, com marca, tamanho e código por mercado.

Uma variante pertence a um produto. Sem GTIN na nota (o caso da Consulta
Completa da SEFAZ-RS), a identidade dela num mercado é o código interno
(`variante_codigos`); o mesmo produto em dois mercados nasce como duas
variantes até alguém dizer que são a mesma coisa ("juntar").
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.enums import MedidaBase
from compras.models import Apelido, Mercado, NotaItem, Produto, Variante, VarianteCodigo
from compras.normalizar import normalizar
from compras.schemas import VarianteCodigoLeitura, VarianteLeitura
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.produtos import ProdutoService


def validar_medida(pesada: bool, medida_base: MedidaBase | None, conteudo: Decimal | None) -> None:
    """As regras do check da tabela, com mensagem para quem usa a API."""
    if pesada:
        if medida_base not in (None, MedidaBase.G):
            raise RegraViolada("Variante pesada é medida em g.")
        if conteudo is not None:
            raise RegraViolada("Variante pesada não tem conteúdo: a quantidade da nota é o peso.")
    elif medida_base is None and conteudo is not None:
        raise RegraViolada("O conteúdo precisa de `medida_base`.")
    elif medida_base is not None and conteudo is None:
        raise RegraViolada("Com `medida_base`, informe o `conteudo` de uma unidade.")


class VarianteService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    # --- leitura ----------------------------------------------------------------

    def get(self, id_: int) -> Variante:
        variante = self.session.scalar(
            select(Variante).where(Variante.id == id_, Variante.deleted_em.is_(None))
        )
        if variante is None:
            raise NaoEncontrado("variante", id_)
        return variante

    def por_gtin(self, gtin: str) -> Variante | None:
        return self.session.scalar(
            select(Variante).where(Variante.gtin == gtin, Variante.deleted_em.is_(None))
        )

    def codigos(self, ids: list[int]) -> dict[int, list[VarianteCodigoLeitura]]:
        achados: dict[int, list[VarianteCodigoLeitura]] = {i: [] for i in ids}
        if not ids:
            return achados
        linhas = self.session.execute(
            select(VarianteCodigo.variante_id, Mercado.id, Mercado.nome, VarianteCodigo.codigo)
            .join(Mercado, Mercado.id == VarianteCodigo.mercado_id)
            .where(VarianteCodigo.variante_id.in_(ids), VarianteCodigo.deleted_em.is_(None))
            .order_by(Mercado.nome, VarianteCodigo.codigo)
        )
        for variante_id, mercado_id, mercado_nome, codigo in linhas:
            achados[variante_id].append(
                VarianteCodigoLeitura(
                    mercado_id=mercado_id, mercado_nome=mercado_nome, codigo=codigo
                )
            )
        return achados

    def leituras(self, variantes: list[Variante]) -> list[VarianteLeitura]:
        codigos = self.codigos([v.id for v in variantes])
        return [VarianteLeitura.de(v, codigos[v.id]) for v in variantes]

    def listar(
        self,
        produto_id: int | None,
        gtin: str | None,
        busca: str | None,
        sem_medida: bool | None,
        limite: int,
        offset: int = 0,
    ) -> list[Variante]:
        """Para associar: contém o texto no nome da variante, no do produto ou
        no do mercado onde ela tem código; quem começa com ele vem antes."""
        consulta = (
            select(Variante)
            .join(Produto, Produto.id == Variante.produto_id)
            .where(Variante.deleted_em.is_(None))
        )
        if produto_id is not None:
            consulta = consulta.where(Variante.produto_id == produto_id)
        if gtin:
            consulta = consulta.where(Variante.gtin == gtin)
        if sem_medida is not None:
            consulta = consulta.where(
                Variante.medida_base.is_(None) if sem_medida else Variante.medida_base.is_not(None)
            )
        ordem: list[Any] = []
        termo = normalizar(busca or "")
        if termo:
            do_mercado = exists().where(
                VarianteCodigo.variante_id == Variante.id,
                VarianteCodigo.deleted_em.is_(None),
                VarianteCodigo.mercado_id == Mercado.id,
                func.upper(Mercado.nome).contains(termo, autoescape=True),
            )
            consulta = consulta.where(
                or_(
                    Variante.nome_normalizado.contains(termo, autoescape=True),
                    Produto.nome_normalizado.contains(termo, autoescape=True),
                    do_mercado,
                )
            )
            ordem.append(
                func.coalesce(
                    Variante.nome_normalizado.startswith(termo, autoescape=True), False
                ).desc()
            )
        ordem += [Variante.nome_normalizado, Variante.id]
        return list(self.session.scalars(consulta.order_by(*ordem).limit(limite).offset(offset)))

    # --- escrita ----------------------------------------------------------------

    def criar(
        self,
        *,
        produto_id: int,
        nome: str,
        marca: str | None = None,
        gtin: str | None = None,
        medida_base: MedidaBase | None = None,
        conteudo: Decimal | None = None,
        pesada: bool = False,
    ) -> Variante:
        produto = ProdutoService(self.session).get(produto_id)
        if pesada and medida_base is None:
            medida_base = MedidaBase.G
        validar_medida(pesada, medida_base, conteudo)
        if gtin:
            self._exigir_gtin_livre(gtin)
        variante = Variante(
            produto_id=produto.id,
            nome=nome,
            nome_normalizado=normalizar(nome),
            marca=marca,
            gtin=gtin or None,
            medida_base=medida_base,
            conteudo=conteudo,
            pesada=pesada,
            criado_por=self.quem,
        )
        try:
            with self.session.begin_nested():
                self.session.add(variante)
                self.session.flush()
        except IntegrityError as erro:
            if gtin:
                self._exigir_gtin_livre(gtin)
            raise Conflito("Não foi possível criar a variante.") from erro
        self.session.refresh(variante)
        return variante

    def _exigir_gtin_livre(self, gtin: str) -> None:
        existente = self.por_gtin(gtin)
        if existente is not None:
            raise Conflito(
                f'O código de barras {gtin} já é da variante "{existente.nome}".',
                {"variante": self.leituras([existente])[0].model_dump(mode="json")},
            )

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Variante:
        variante = self.get(id_)
        if dados.get("produto_id") is not None:
            produto = ProdutoService(self.session).get(dados["produto_id"])
            # O trigger leva os itens de nota e os apelidos junto.
            variante.produto_id = produto.id
        if dados.get("nome") is not None:
            variante.nome = dados["nome"]
            variante.nome_normalizado = normalizar(dados["nome"])
        if "marca" in dados:
            variante.marca = dados["marca"]

        pesada = dados["pesada"] if dados.get("pesada") is not None else variante.pesada
        medida_base = dados.get("medida_base", variante.medida_base)
        conteudo = dados.get("conteudo", variante.conteudo)
        if pesada and not variante.pesada:
            # Passou a pesada: g, sem conteúdo, a menos que peça outra coisa.
            medida_base = dados.get("medida_base") or MedidaBase.G
            conteudo = None
        elif not pesada and variante.pesada and "medida_base" not in dados:
            # Deixou de ser pesada sem dizer o tamanho: volta a "sem medida".
            medida_base = None
            conteudo = None
        validar_medida(pesada, medida_base, conteudo)
        variante.pesada = pesada
        variante.medida_base = medida_base
        variante.conteudo = conteudo
        self.session.flush()
        self.session.refresh(variante)
        return variante

    def remover(self, id_: int) -> Variante:
        """Soft delete; 409 se há item de nota ligado. Os códigos e apelidos
        dela, que só existem para apontar para ela, vão junto."""
        variante = self.get(id_)
        ligados = self.session.scalar(
            select(func.count())
            .select_from(NotaItem)
            .where(NotaItem.variante_id == variante.id, NotaItem.deleted_em.is_(None))
        )
        if ligados:
            raise Conflito(
                f'A variante "{variante.nome}" tem {ligados} item(ns) de nota; '
                "junte-a a outra ou mude o produto em vez de apagar."
            )
        agora = func.now()
        for tabela in (VarianteCodigo, Apelido):
            self.session.execute(
                update(tabela)
                .where(tabela.variante_id == variante.id, tabela.deleted_em.is_(None))
                .values(deleted_em=agora)
            )
        variante.deleted_em = agora
        self.session.flush()
        self.session.refresh(variante)
        return variante

    def juntar(self, mantida_id: int, outra_id: int) -> Variante:
        """Fica a `mantida`; a `outra` é apagada (soft delete) depois de passar
        para a primeira os códigos, os apelidos e os itens de nota. Não mexe
        na nota nem no preço pago: só no agrupamento."""
        if mantida_id == outra_id:
            raise RegraViolada("Uma variante não se junta a ela mesma.")
        travadas = {
            v.id: v
            for v in self.session.scalars(
                select(Variante)
                .where(Variante.id.in_([mantida_id, outra_id]), Variante.deleted_em.is_(None))
                .order_by(Variante.id)
                .with_for_update()
            )
        }
        for id_ in (mantida_id, outra_id):
            if id_ not in travadas:
                raise NaoEncontrado("variante", id_)
        mantida, outra = travadas[mantida_id], travadas[outra_id]
        if mantida.produto_id != outra.produto_id:
            raise RegraViolada(
                "As variantes são de produtos diferentes. Troque o produto de uma delas "
                "(PATCH /variantes/{id}) antes de juntar."
            )
        if mantida.gtin and outra.gtin:
            raise RegraViolada(
                "As duas variantes têm código de barras (diferentes): não são a mesma coisa."
            )

        gtin = outra.gtin
        if gtin:
            outra.gtin = None
            self.session.flush()  # libera o unique parcial do GTIN
        if mantida.gtin is None and gtin:
            mantida.gtin = gtin
        if mantida.medida_base is None and outra.medida_base is not None:
            mantida.medida_base = outra.medida_base
            mantida.conteudo = outra.conteudo
            mantida.pesada = outra.pesada

        for tabela in (VarianteCodigo, Apelido, NotaItem):
            self.session.execute(
                update(tabela).where(tabela.variante_id == outra.id).values(variante_id=mantida.id)
            )
        outra.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(mantida)
        return mantida
