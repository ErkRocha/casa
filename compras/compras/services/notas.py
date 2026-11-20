"""Nota fiscal (NFC-e): leitura, associação de itens a produtos e apelidos.

O fluxo da leitura (docs/compras/api.md, "Nota fiscal e preços"):

1. a entrada (URL do QR code ou chave) é conferida: dígito verificador, UF e
   modelo; a mesma chave já lida devolve a nota que existe, sem buscar;
2. a consulta pública é buscada e o conteúdo guardado **inteiro**, mesmo
   quando o leitor não o entende;
3. o mercado sai do CNPJ da chave;
4. o leitor interpreta o conteúdo; falhou, a nota fica com `status = erro` e
   pode ser relida;
5. cada item tenta achar a variante (D-33): GTIN > `(mercado, código)` >
   apelido do texto no mesmo mercado > apelido sem mercado > apelido de outro
   mercado, se todos concordam. Sem nada disso, fica sem variante, na fila de
   "associar". O produto do item é o da variante.

Associar um item grava (ou reforça) o código do mercado e o apelido do
texto: a próxima nota com o mesmo código ou texto já vem associada (D-09).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.db import definir_autor
from compras.enums import OrigemAssociacao, StatusNota
from compras.models import (
    Apelido,
    NotaFiscal,
    NotaItem,
    Produto,
    Variante,
    VarianteCodigo,
)
from compras.nfce.chave import Chave, validar
from compras.nfce.consulta import ConsultaFalhou, ConsultaPublica
from compras.nfce.entrada import EntradaInvalida, interpretar, urls_de_consulta
from compras.nfce.leitor import FormatoDesconhecido, LeitorNota
from compras.normalizar import normalizar
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.mercados import MercadoService
from compras.services.produtos import ProdutoService
from compras.services.variantes import VarianteService

#: Autor da auditoria no que a leitura grava sozinha (modelo-dados.md).
AUTOR_LEITURA = "leitura_nfce"


@dataclass(frozen=True, slots=True)
class Associacao:
    variante_id: int
    produto_id: int
    origem: OrigemAssociacao


def codigo_sem_zeros(codigo: str | None) -> str | None:
    """O código interno como `variante_codigos` o guarda: sem zeros à esquerda."""
    limpo = (codigo or "").strip().lstrip("0")
    return limpo or None


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

    def reler_forma_pagamento(self, id_: int, sobrescrever: bool = False) -> NotaFiscal:
        """Relê só `forma_pagamento_nota` da página guardada.

        Para nota lida antes de o leitor saber a forma (o QR code antes de
        20/11/2026). Não toca nos itens, nos totais nem na despesa ligada, e
        não busca na SEFAZ. Nota com erro: 409 (use `reler`). Sem página
        guardada ou página que o leitor não entende: 422. Campo já preenchido:
        409, a não ser com `sobrescrever`. Página sem forma: nada muda. O
        autor da auditoria é quem pediu (o `X-Quem` da requisição).
        """
        nota = self.get(id_)
        if nota.status != StatusNota.LIDA:
            raise Conflito("A nota não foi lida: use reler.")
        if not nota.conteudo_original:
            raise RegraViolada("A nota não tem a página guardada.")
        if nota.forma_pagamento_nota and not sobrescrever:
            raise Conflito(
                f"A nota já tem forma de pagamento ({nota.forma_pagamento_nota}); "
                "use sobrescrever para trocar."
            )
        assert self.leitor is not None, "NotaService sem leitor"
        try:
            lida = self.leitor.ler(nota.conteudo_original, nota.conteudo_tipo)
        except FormatoDesconhecido as exc:
            raise RegraViolada(f"Leitor {self.leitor.versao}: {exc}") from exc
        if lida.forma_pagamento and lida.forma_pagamento != nota.forma_pagamento_nota:
            nota.forma_pagamento_nota = lida.forma_pagamento
            self.session.flush()
        return nota

    def _buscar_e_interpretar(self, nota: NotaFiscal, chave: Chave) -> None:
        assert self.consulta is not None, "NotaService sem consulta pública"
        # A URL do QR code primeiro; a da chave é a reserva. Qualquer resultado
        # que não seja nota lida leva à próxima. Itens só são gravados na
        # leitura bem-sucedida, então uma tentativa falha não deixa nada a duplicar.
        urls = urls_de_consulta(nota.url_consulta, chave.numero)
        erros: list[str] = []
        for url in urls:
            try:
                resposta = self.consulta.buscar(url)
            except ConsultaFalhou as exc:
                nota.status = StatusNota.ERRO
                nota.erro_mensagem = f"Consulta à SEFAZ: {exc}"
                self.session.flush()
            else:
                self._interpretar(nota, chave, resposta.conteudo, resposta.tipo)
            if nota.status == StatusNota.LIDA:
                return
            erros.append(nota.erro_mensagem or "erro sem mensagem")
        if len(erros) > 1:
            nota.erro_mensagem = (
                f"Pelo QR code: {erros[0].rstrip('.')}. Pela chave: {erros[1].rstrip('.')}."
            )
            self.session.flush()

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
        nota.leitor_versao = lida.versao or self.leitor.versao
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
        nota.forma_pagamento_nota = lida.forma_pagamento
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
            achada = self.associacao_automatica(lido.descricao, lido.gtin, mercado.id, lido.codigo)
            if achada is not None:
                item.variante_id = achada.variante_id
                item.produto_id = achada.produto_id
                item.origem_associacao = achada.origem
            self.session.add(item)
        self.session.flush()

    # --- associação -----------------------------------------------------------

    def associacao_automatica(
        self, descricao: str, gtin: str | None, mercado_id: int | None, codigo: str | None = None
    ) -> Associacao | None:
        """GTIN > `(mercado, código)` > texto no mesmo mercado > texto sem
        mercado > texto em outros mercados, só se todos apontam para a mesma
        variante. O código ganha do texto: o mercado abrevia a mesma coisa de
        jeitos diferentes, e o código não muda. O produto vivo é condição."""
        vivas = (
            select(Variante.id, Variante.produto_id)
            .join(Produto, Produto.id == Variante.produto_id)
            .where(Variante.deleted_em.is_(None), Produto.deleted_em.is_(None))
        )
        if gtin:
            achada = self.session.execute(vivas.where(Variante.gtin == gtin)).first()
            if achada is not None:
                return Associacao(achada[0], achada[1], OrigemAssociacao.GTIN)
        sem_zeros = codigo_sem_zeros(codigo)
        if mercado_id is not None and sem_zeros is not None:
            achada = self.session.execute(
                vivas.join(VarianteCodigo, VarianteCodigo.variante_id == Variante.id).where(
                    VarianteCodigo.mercado_id == mercado_id,
                    VarianteCodigo.codigo == sem_zeros,
                    VarianteCodigo.deleted_em.is_(None),
                )
            ).first()
            if achada is not None:
                return Associacao(achada[0], achada[1], OrigemAssociacao.APELIDO)

        por_texto = vivas.join(Apelido, Apelido.variante_id == Variante.id).where(
            Apelido.deleted_em.is_(None), Apelido.texto_normalizado == normalizar(descricao)
        )
        if mercado_id is not None:
            achada = self.session.execute(por_texto.where(Apelido.mercado_id == mercado_id)).first()
            if achada is not None:
                return Associacao(achada[0], achada[1], OrigemAssociacao.APELIDO)
        achada = self.session.execute(por_texto.where(Apelido.mercado_id.is_(None))).first()
        if achada is not None:
            return Associacao(achada[0], achada[1], OrigemAssociacao.APELIDO)
        candidatas = {(v, p) for v, p in self.session.execute(por_texto)}
        if len(candidatas) == 1:
            variante_id, produto_id = candidatas.pop()
            return Associacao(variante_id, produto_id, OrigemAssociacao.APELIDO)
        return None

    def _item(self, nota: NotaFiscal, item_id: int) -> NotaItem:
        item = self.session.scalar(
            select(NotaItem).where(
                NotaItem.id == item_id,
                NotaItem.nota_fiscal_id == nota.id,
                NotaItem.deleted_em.is_(None),
            )
        )
        if item is None:
            raise NaoEncontrado("item da nota", item_id)
        return item

    def associar_item(self, nota_id: int, item_id: int, produto_id: int, quem: str) -> NotaItem:
        """Compatibilidade: o item é deste produto. Equivale a
        `associar_variante(produto_id=..., nova={})`."""
        return self.associar_variante(nota_id, item_id, quem, produto_id=produto_id, nova={})

    def associar_variante(
        self,
        nota_id: int,
        item_id: int,
        quem: str,
        *,
        variante_id: int | None = None,
        produto_id: int | None = None,
        nova: dict[str, Any] | None = None,
    ) -> NotaItem:
        """O usuário diz qual é a variante do item: uma que existe, ou uma nova
        para o produto. Grava (ou reforça) o código do mercado e o apelido do
        texto, e leva o GTIN do item para a variante que ainda não tem um."""
        nota = self.get(nota_id)
        item = self._item(nota, item_id)
        variantes = VarianteService(self.session, quem)
        if variante_id is not None:
            variante = variantes.get(variante_id)
            if variante.gtin is None and item.gtin and variantes.por_gtin(item.gtin) is None:
                variante.gtin = item.gtin
        else:
            assert produto_id is not None
            produto = ProdutoService(self.session).get(produto_id)
            variante = self._variante_para(variantes, produto, item, nova or {})

        primeira = item.variante_id is None
        criado_por = "usuario" if primeira else "correcao"
        item.variante_id = variante.id
        item.produto_id = variante.produto_id
        item.origem_associacao = OrigemAssociacao.USUARIO
        self._aprender(
            texto=normalizar(item.descricao_original),
            mercado_id=nota.mercado_id,
            variante=variante,
            criado_por=criado_por,
        )
        codigo = codigo_sem_zeros(item.codigo)
        if nota.mercado_id is not None and codigo is not None:
            self._aprender_codigo(variante, nota.mercado_id, codigo, quem)
        self.session.flush()
        if primeira and nota.conferida_em is not None:
            # A nota já foi conferida sem esta linha: o efeito dela vem agora.
            from compras.services.conferencia import ConferenciaService

            ConferenciaService(self.session, quem).linha_associada_depois(nota, item)
        self.session.refresh(item)
        return item

    def _variante_para(
        self, variantes: VarianteService, produto: Produto, item: NotaItem, nova: dict[str, Any]
    ) -> Variante:
        """A variante do produto com o nome da nota (ou o dado em `nova`): a que
        já existe, ou uma criada agora. KG na nota marca `pesada`, sem perguntar;
        a medida só é gravada se `nova` a trouxer (a sugestão da descrição vai
        na resposta, para o usuário confirmar)."""
        nome = nova.get("nome") or item.descricao_original
        normalizado = normalizar(nome)
        existente = self.session.scalar(
            select(Variante)
            .where(
                Variante.produto_id == produto.id,
                Variante.nome_normalizado == normalizado,
                Variante.deleted_em.is_(None),
                (Variante.gtin.is_(None)) | (Variante.gtin == item.gtin),
            )
            .order_by(Variante.id)
            .limit(1)
        )
        if existente is not None:
            if existente.medida_base is None and (nova.get("medida_base") or nova.get("pesada")):
                variantes.atualizar(
                    existente.id,
                    {k: v for k, v in nova.items() if k in ("medida_base", "conteudo", "pesada")},
                )
            return existente
        pesada = nova.get("pesada")
        if pesada is None:
            pesada = (item.unidade or "").strip().upper() == "KG"
        gtin = item.gtin if item.gtin and variantes.por_gtin(item.gtin) is None else None
        return variantes.criar(
            produto_id=produto.id,
            nome=nome,
            marca=nova.get("marca"),
            gtin=gtin,
            medida_base=nova.get("medida_base"),
            conteudo=nova.get("conteudo"),
            pesada=bool(pesada),
        )

    def _aprender(
        self,
        *,
        texto: str,
        mercado_id: int | None,
        variante: Variante,
        criado_por: str,
    ) -> None:
        consulta = select(Apelido).where(
            Apelido.deleted_em.is_(None),
            Apelido.texto_normalizado == texto,
            Apelido.mercado_id.is_(None)
            if mercado_id is None
            else Apelido.mercado_id == mercado_id,
        )
        existente = self.session.scalar(consulta.with_for_update())
        if existente is not None:
            if existente.variante_id == variante.id:
                existente.acertos += 1
            else:
                # Correção: o apelido passa a apontar para a variante nova.
                existente.variante_id = variante.id
                existente.produto_id = variante.produto_id
                existente.acertos = 1
                existente.criado_por = "correcao"
            return
        try:
            with self.session.begin_nested():
                self.session.add(
                    Apelido(
                        variante_id=variante.id,
                        produto_id=variante.produto_id,
                        texto_normalizado=texto,
                        mercado_id=mercado_id,
                        acertos=1,
                        criado_por=criado_por,
                    )
                )
                self.session.flush()
        except IntegrityError:
            # Outro pedido criou o mesmo apelido agora: reforça o dele.
            self._aprender(
                texto=texto, mercado_id=mercado_id, variante=variante, criado_por=criado_por
            )

    def _aprender_codigo(
        self, variante: Variante, mercado_id: int, codigo: str, quem: str, tentativa: int = 0
    ) -> None:
        """O código do mercado aponta para esta variante. Se apontava para
        outra, foi correção: passa para esta."""
        existente = self.session.scalar(
            select(VarianteCodigo)
            .where(
                VarianteCodigo.mercado_id == mercado_id,
                VarianteCodigo.codigo == codigo,
                VarianteCodigo.deleted_em.is_(None),
            )
            .with_for_update()
        )
        if existente is not None:
            existente.variante_id = variante.id
            return
        try:
            with self.session.begin_nested():
                self.session.add(
                    VarianteCodigo(
                        variante_id=variante.id,
                        mercado_id=mercado_id,
                        codigo=codigo,
                        criado_por=quem,
                    )
                )
                self.session.flush()
        except IntegrityError:
            if tentativa >= 1:
                raise
            self._aprender_codigo(variante, mercado_id, codigo, quem, tentativa + 1)

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

    def listar(
        self,
        limite: int,
        deslocamento: int = 0,
        conferida: bool | None = None,
        com_transacao: bool | None = None,
    ) -> tuple[list[NotaFiscal], int]:
        """Paginada, com o total. `conferida` e `com_transacao` servem às filas
        "notas sem conferência" e "notas sem despesa"; ligada à compra pendente
        do cartão conta como ligada."""
        filtro: list[Any] = [NotaFiscal.deleted_em.is_(None)]
        if conferida is not None:
            filtro.append(
                NotaFiscal.conferida_em.is_not(None)
                if conferida
                else NotaFiscal.conferida_em.is_(None)
            )
        if com_transacao is not None:
            ligada = NotaFiscal.transacao_id.is_not(None) | NotaFiscal.pendente_id_externo.is_not(
                None
            )
            filtro.append(ligada if com_transacao else ~ligada)
        total = self.session.scalar(select(func.count()).select_from(NotaFiscal).where(*filtro))
        notas = self.session.scalars(
            select(NotaFiscal)
            .where(*filtro)
            .order_by(NotaFiscal.emitida_em.desc().nulls_first(), NotaFiscal.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return list(notas), int(total or 0)

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

    def precos_da_nota(self, nota_id: int) -> dict[int, dict[str, Any]]:
        """Preço pago, desconto rateado e comparável de cada item associado
        (`vw_preco_variante`), por id do item."""
        linhas = self.session.execute(
            text(
                "SELECT nota_item_id, desconto_rateado, preco_pago, preco_pago_estimado, "
                "preco_comparavel, por FROM compras.vw_preco_variante "
                "WHERE nota_fiscal_id = :nota"
            ),
            {"nota": nota_id},
        )
        return {int(linha.nota_item_id): dict(linha._mapping) for linha in linhas}

    def sem_produto(self, limite: int) -> list[NotaItem]:
        """A fila de "associar": itens vivos, de notas vivas, sem variante."""
        return list(
            self.session.scalars(
                select(NotaItem)
                .join(NotaFiscal, NotaFiscal.id == NotaItem.nota_fiscal_id)
                .where(
                    NotaItem.variante_id.is_(None),
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
