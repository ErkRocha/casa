"""Nota fiscal (NFC-e): leitura, associação de itens a produtos e apelidos.

O fluxo da leitura (docs/compras/api.md, "Nota fiscal e preços"):

1. a entrada (URL do QR code ou chave) é conferida: dígito verificador, UF e
   modelo; a mesma chave já lida devolve a nota que existe, sem buscar;
2. a consulta pública é buscada e o conteúdo guardado **inteiro**, mesmo
   quando o leitor não o entende;
3. o mercado sai do CNPJ da chave;
4. o leitor interpreta o conteúdo; falhou, a nota fica com `status = erro` e
   pode ser relida;
5. cada item tenta achar o produto: GTIN aprendido > apelido do texto no
   mesmo mercado > apelido sem mercado > apelido de outro mercado, se todos
   concordam. Sem nada disso, fica sem produto, na fila de "associar".

Corrigir o produto de um item grava (ou reforça) o apelido: a próxima nota
com o mesmo texto já vem associada (D-09 aplicada a produto).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.db import definir_autor
from compras.enums import OrigemAssociacao, StatusNota
from compras.financas import Financas, TransacaoResumo
from compras.models import Apelido, NotaFiscal, NotaItem, Produto
from compras.nfce.chave import Chave, validar
from compras.nfce.consulta import ConsultaFalhou, ConsultaPublica
from compras.nfce.entrada import EntradaInvalida, interpretar
from compras.nfce.leitor import FormatoDesconhecido, LeitorNota
from compras.nfce.leitor_svrs import FUSO
from compras.normalizar import normalizar
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.mercados import MercadoService
from compras.services.produtos import ProdutoService

#: Autor da auditoria no que a leitura grava sozinha (modelo-dados.md).
AUTOR_LEITURA = "leitura_nfce"


@dataclass(frozen=True, slots=True)
class Associacao:
    produto_id: int
    origem: OrigemAssociacao


class NotaService:
    def __init__(
        self,
        session: Session,
        consulta: ConsultaPublica | None = None,
        leitor: LeitorNota | None = None,
    ) -> None:
        self.session = session
        self.consulta = consulta
        self.leitor = leitor
        self.mercados = MercadoService(session)

    # --- leitura ------------------------------------------------------------

    def ler(self, texto: str, quem: str) -> tuple[NotaFiscal, bool]:
        """(nota, lida agora). A mesma chave devolve a nota existente."""
        try:
            entrada = interpretar(texto)
        except EntradaInvalida as exc:
            raise RegraViolada(str(exc)) from exc

        existente = self._por_chave(entrada.chave.numero)
        if existente is not None:
            return existente, False

        definir_autor(self.session, AUTOR_LEITURA)
        mercado = self.mercados.por_cnpj(entrada.chave.cnpj, entrada.chave.cnpj_formatado)
        nota = NotaFiscal(
            chave_acesso=entrada.chave.numero,
            mercado_id=mercado.id,
            url_consulta=entrada.url_consulta,
            status=StatusNota.ERRO,
            erro_mensagem="ainda não lida",
            desconto_total=Decimal("0"),
            lida_por=quem,
        )
        try:
            with self.session.begin_nested():
                self.session.add(nota)
                self.session.flush()
        except IntegrityError:
            # A mesma nota lida ao mesmo tempo pelos dois celulares.
            outra = self._por_chave(entrada.chave.numero)
            if outra is None:
                raise
            return outra, False

        self._buscar_e_interpretar(nota, entrada.chave)
        definir_autor(self.session, quem)
        return nota, True

    def reler(self, id_: int, quem: str, buscar_de_novo: bool = False) -> NotaFiscal:
        """Lê de novo uma nota com erro: interpreta o conteúdo guardado, ou
        busca de novo se não há conteúdo (ou se pedido). Nota lida: 409."""
        nota = self.get(id_)
        if nota.status == StatusNota.LIDA:
            raise Conflito("A nota já foi lida; não há o que reler.")
        chave = validar(nota.chave_acesso)
        definir_autor(self.session, AUTOR_LEITURA)
        if buscar_de_novo or nota.conteudo_original is None:
            self._buscar_e_interpretar(nota, chave)
        else:
            self._interpretar(nota, chave, nota.conteudo_original, nota.conteudo_tipo)
        definir_autor(self.session, quem)
        return nota

    def _buscar_e_interpretar(self, nota: NotaFiscal, chave: Chave) -> None:
        assert self.consulta is not None, "NotaService sem consulta pública"
        try:
            resposta = self.consulta.buscar(nota.url_consulta)
        except ConsultaFalhou as exc:
            nota.status = StatusNota.ERRO
            nota.erro_mensagem = f"Consulta à SEFAZ: {exc}"
            self.session.flush()
            return
        self._interpretar(nota, chave, resposta.conteudo, resposta.tipo)

    def _interpretar(
        self, nota: NotaFiscal, chave: Chave, conteudo: bytes, tipo: str | None
    ) -> None:
        assert self.leitor is not None, "NotaService sem leitor"
        nota.conteudo_original = conteudo
        nota.conteudo_tipo = tipo
        nota.leitor_versao = self.leitor.versao
        try:
            lida = self.leitor.ler(conteudo, tipo)
        except FormatoDesconhecido as exc:
            nota.status = StatusNota.ERRO
            nota.erro_mensagem = f"Leitor {self.leitor.versao}: {exc}"
            self.session.flush()
            return
        if lida.cnpj and lida.cnpj != chave.cnpj:
            nota.status = StatusNota.ERRO
            nota.erro_mensagem = (
                f"O CNPJ da página ({lida.cnpj}) não é o da chave ({chave.cnpj}): "
                "a consulta devolveu outra nota."
            )
            self.session.flush()
            return

        assert nota.mercado_id is not None
        mercado = self.mercados.get(nota.mercado_id)
        self.mercados.completar(
            mercado, lida.razao_social, lida.endereco, lida.cidade, chave.cnpj_formatado
        )
        nota.status = StatusNota.LIDA
        nota.erro_mensagem = None
        nota.emitida_em = lida.emitida_em
        nota.valor_total = lida.valor_total
        nota.desconto_total = lida.desconto_total
        for lido in lida.itens:
            item = NotaItem(
                nota_fiscal_id=nota.id,
                linha_num=lido.linha_num,
                codigo=lido.codigo,
                gtin=lido.gtin,
                descricao_original=lido.descricao,
                quantidade=lido.quantidade,
                unidade=lido.unidade,
                valor_unitario=lido.valor_unitario,
                valor_total=lido.valor_total,
                desconto=lido.desconto,
            )
            achada = self.associacao_automatica(lido.descricao, lido.gtin, mercado.id)
            if achada is not None:
                item.produto_id = achada.produto_id
                item.origem_associacao = achada.origem
            self.session.add(item)
        self.session.flush()

    # --- associação -----------------------------------------------------------

    def associacao_automatica(
        self, descricao: str, gtin: str | None, mercado_id: int | None
    ) -> Associacao | None:
        """GTIN > texto no mesmo mercado > texto sem mercado > texto em outros
        mercados, só se todos apontam para o mesmo produto."""
        vivos = (
            select(Apelido.produto_id)
            .join(Produto, Produto.id == Apelido.produto_id)
            .where(Apelido.deleted_em.is_(None), Produto.deleted_em.is_(None))
        )
        if gtin:
            produto_id = self.session.scalar(vivos.where(Apelido.gtin == gtin))
            if produto_id is not None:
                return Associacao(produto_id, OrigemAssociacao.GTIN)
        texto = normalizar(descricao)
        por_texto = vivos.where(Apelido.texto_normalizado == texto)
        if mercado_id is not None:
            produto_id = self.session.scalar(por_texto.where(Apelido.mercado_id == mercado_id))
            if produto_id is not None:
                return Associacao(produto_id, OrigemAssociacao.APELIDO)
        produto_id = self.session.scalar(por_texto.where(Apelido.mercado_id.is_(None)))
        if produto_id is not None:
            return Associacao(produto_id, OrigemAssociacao.APELIDO)
        candidatos = set(self.session.scalars(por_texto))
        if len(candidatos) == 1:
            return Associacao(candidatos.pop(), OrigemAssociacao.APELIDO)
        return None

    def associar_item(self, nota_id: int, item_id: int, produto_id: int) -> NotaItem:
        """O usuário diz qual é o produto do item. Grava ou reforça o apelido."""
        nota = self.get(nota_id)
        item = self.session.scalar(
            select(NotaItem).where(
                NotaItem.id == item_id,
                NotaItem.nota_fiscal_id == nota.id,
                NotaItem.deleted_em.is_(None),
            )
        )
        if item is None:
            raise NaoEncontrado("item da nota", item_id)
        produto = ProdutoService(self.session).get(produto_id)

        criado_por = "usuario" if item.produto_id is None else "correcao"
        item.produto_id = produto.id
        item.origem_associacao = OrigemAssociacao.USUARIO
        self._aprender(
            texto=normalizar(item.descricao_original),
            gtin=None,
            mercado_id=nota.mercado_id,
            produto_id=produto.id,
            criado_por=criado_por,
        )
        if item.gtin:
            # O GTIN é o mesmo em toda loja: vale sem mercado.
            self._aprender(
                texto=None, gtin=item.gtin, mercado_id=None, produto_id=produto.id,
                criado_por=criado_por,
            )  # fmt: skip
        self.session.flush()
        return item

    def _aprender(
        self,
        *,
        texto: str | None,
        gtin: str | None,
        mercado_id: int | None,
        produto_id: int,
        criado_por: str,
    ) -> None:
        consulta = select(Apelido).where(Apelido.deleted_em.is_(None))
        if gtin is not None:
            consulta = consulta.where(Apelido.gtin == gtin)
        else:
            consulta = consulta.where(
                Apelido.texto_normalizado == texto,
                Apelido.mercado_id.is_(None)
                if mercado_id is None
                else Apelido.mercado_id == mercado_id,
            )
        existente = self.session.scalar(consulta.with_for_update())
        if existente is not None:
            if existente.produto_id == produto_id:
                existente.acertos += 1
            else:
                # Correção: o apelido passa a apontar para o produto novo.
                existente.produto_id = produto_id
                existente.acertos = 1
                existente.criado_por = "correcao"
            return
        try:
            with self.session.begin_nested():
                self.session.add(
                    Apelido(
                        produto_id=produto_id,
                        texto_normalizado=texto,
                        gtin=gtin,
                        mercado_id=mercado_id,
                        acertos=1,
                        criado_por=criado_por,
                    )
                )
                self.session.flush()
        except IntegrityError:
            # Outro pedido criou o mesmo apelido agora: reforça o dele.
            self._aprender(
                texto=texto, gtin=gtin, mercado_id=mercado_id, produto_id=produto_id,
                criado_por=criado_por,
            )  # fmt: skip

    # --- consultas -------------------------------------------------------------

    def _por_chave(self, chave: str) -> NotaFiscal | None:
        return self.session.scalar(
            select(NotaFiscal).where(
                NotaFiscal.chave_acesso == chave, NotaFiscal.deleted_em.is_(None)
            )
        )

    def get(self, id_: int) -> NotaFiscal:
        nota = self.session.scalar(
            select(NotaFiscal).where(NotaFiscal.id == id_, NotaFiscal.deleted_em.is_(None))
        )
        if nota is None:
            raise NaoEncontrado("nota", id_)
        return nota

    def listar(self, limite: int) -> list[NotaFiscal]:
        return list(
            self.session.scalars(
                select(NotaFiscal)
                .where(NotaFiscal.deleted_em.is_(None))
                .order_by(NotaFiscal.emitida_em.desc().nulls_first(), NotaFiscal.id.desc())
                .limit(limite)
            )
        )

    def itens(self, nota_id: int) -> list[NotaItem]:
        return list(
            self.session.scalars(
                select(NotaItem)
                .where(NotaItem.nota_fiscal_id == nota_id, NotaItem.deleted_em.is_(None))
                .order_by(NotaItem.linha_num)
            )
        )

    def soma_itens(self, nota_id: int) -> Decimal:
        """Soma dos itens menos os descontos de item, pelo banco (regra 10)."""
        soma = self.session.scalar(
            select(func.coalesce(func.sum(NotaItem.valor_total - NotaItem.desconto), 0)).where(
                NotaItem.nota_fiscal_id == nota_id, NotaItem.deleted_em.is_(None)
            )
        )
        return Decimal(soma or 0)

    def sem_produto(self, limite: int) -> list[NotaItem]:
        """A fila de "associar": itens vivos, de notas vivas, sem produto."""
        return list(
            self.session.scalars(
                select(NotaItem)
                .join(NotaFiscal, NotaFiscal.id == NotaItem.nota_fiscal_id)
                .where(
                    NotaItem.produto_id.is_(None),
                    NotaItem.deleted_em.is_(None),
                    NotaFiscal.deleted_em.is_(None),
                )
                .order_by(NotaFiscal.emitida_em.desc().nulls_last(), NotaItem.linha_num)
                .limit(limite)
            )
        )

    def remover(self, id_: int) -> NotaFiscal:
        """Soft delete da nota e dos itens. Ler a mesma chave depois lê de novo."""
        nota = self.get(id_)
        agora = func.now()
        for item in self.itens(nota.id):
            item.deleted_em = agora
        nota.deleted_em = agora
        self.session.flush()
        self.session.refresh(nota)
        return nota

    # --- finanças ----------------------------------------------------------------

    def sugestoes_transacao(self, id_: int, financas: Financas) -> list[TransacaoResumo]:
        """Despesas de finanças do mesmo dia e com o mesmo valor da nota.

        Só sugestão: nada é vinculado sem o usuário confirmar.
        """
        nota = self.get(id_)
        if nota.status != StatusNota.LIDA or nota.emitida_em is None or nota.valor_total is None:
            raise RegraViolada("A nota precisa estar lida, com data e valor, para sugerir.")
        dia: date = nota.emitida_em.astimezone(FUSO).date()
        return financas.despesas(dia, nota.valor_total)

    def vincular_transacao(
        self, id_: int, transacao_id: int | None, financas: Financas
    ) -> NotaFiscal:
        """Confirma (ou desfaz, com nulo) a transação de finanças da nota. A
        transação precisa existir em finanças; o id fica sem FK (D-25)."""
        nota = self.get(id_)
        if transacao_id is not None and not financas.existe(transacao_id):
            raise RegraViolada(f"A transação {transacao_id} não existe em finanças.")
        nota.transacao_id = transacao_id
        self.session.flush()
        return nota
