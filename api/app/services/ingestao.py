"""Service de ingestão: importar, enriquecer, promover.

O fluxo inteiro da D-07: o arquivo vira itens em staging, o enriquecimento
sugere categoria/local/pessoa, e **nada entra em `transacoes` sem o usuário
aprovar**. Aprovar é o único caminho de escrita no dado real.

Ordem do enriquecimento (D-09, D-21): regras do usuário primeiro — exatas e
gratuitas —, depois o mapeamento de categorias da Pluggy, depois o casamento
por local já conhecido. LLM não entra aqui; é o passo 6 da fase 5.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoPagamento, TipoTransacao
from app.ingestao import FormatoDesconhecido, hash_arquivo, processar
from app.ingestao.base import ItemExtraido, sem_acento
from app.models import (
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Local,
    RegraCategorizacao,
    Transacao,
)
from app.services.base import Conflito, NaoEncontrado, RegraViolada, _mensagem_integridade
from app.services.cadastros import normalizar_nome, primeiro_dia_do_mes
from app.services.categorias_pluggy import carregar_mapa as carregar_categorias_pluggy
from app.services.regras import reforcar_regra

#: Confiança da categoria vinda do mapeamento da Pluggy: abaixo da regra do
#: usuário (0.95), que é decisão explícita, e acima do local (0.80).
CONFIANCA_CATEGORIA_PLUGGY = Decimal("0.90")


class IngestaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- importar --------------------------------------------------------

    def importar(self, arquivo_nome: str, conteudo: bytes) -> Importacao:
        """PDF -> itens em staging. Não toca em `transacoes`."""
        digest = hash_arquivo(conteudo)

        ja_existe = self.session.scalar(
            select(Importacao).where(
                Importacao.hash_arquivo == digest, Importacao.deleted_em.is_(None)
            )
        )
        if ja_existe is not None:
            raise Conflito(
                f"Este arquivo já foi importado em "
                f"{ja_existe.criado_em:%d/%m/%Y} ({ja_existe.arquivo_nome}). "
                "Reimportar o mesmo PDF duplicaria os lançamentos."
            )

        try:
            doc = processar(conteudo)
        except FormatoDesconhecido as exc:
            raise RegraViolada(str(exc)) from exc

        importacao = Importacao(
            arquivo_nome=arquivo_nome,
            hash_arquivo=digest,
            # O PDF fica guardado para poder ser reaberto meses depois, quando
            # a pergunta for "de onde veio este lançamento?". Sem ele, o
            # sistema sabe o nome do arquivo e não o conteúdo — e nome de
            # arquivo não é comprovante.
            arquivo_conteudo=conteudo,
            arquivo_tipo="application/pdf",
            origem=doc.origem,
            parser_usado=doc.parser,
            periodo_inicio=doc.periodo_inicio,
            periodo_fim=doc.periodo_fim,
            total_declarado=doc.total_declarado,
            total_itens=len(doc.itens),
            status=StatusImportacao.AGUARDANDO_REVISAO,
        )

        # A extração não fechou com o total do documento: o arquivo entra, mas
        # marcado. Melhor revisar 30 linhas sabendo que falta uma do que
        # descobrir o buraco três meses depois.
        if doc.confere is False:
            importacao.erro_mensagem = (
                f"A soma extraída ({doc.soma_itens}) não bate com o total "
                f"declarado no documento ({doc.total_declarado}). "
                "Confira as linhas antes de aprovar."
            )
        if doc.avisos:
            importacao.erro_mensagem = (importacao.erro_mensagem or "") + (
                f" {len(doc.avisos)} linha(s) com valor não foram reconhecidas."
            )

        self.session.add(importacao)
        self.session.flush()

        contexto = _ContextoEnriquecimento.carregar(self.session)
        for extraido in doc.itens:
            self.session.add(self._item(importacao, extraido, doc.competencia, contexto))

        self._flush()
        return importacao

    def importar_lote(
        self,
        *,
        arquivo_nome: str,
        conteudo: bytes,
        arquivo_tipo: str,
        origem: str,
        parser_usado: str,
        itens: Sequence[ItemLote],
        aviso: str | None = None,
    ) -> Importacao:
        """Itens já extraídos de outra origem -> staging, numa importação só.

        É o caminho da sync da Pluggy (D-16, "um caminho só"): o mesmo
        enriquecimento, a mesma marcação de duplicata e o mesmo staging do
        PDF. Muda só o que o PDF não tem — forma de pagamento fixa por item,
        vinda do mapeamento, e a pessoa padrão da conta.

        `conteudo` é o comprovante (o JSON bruto, na Pluggy), guardado como o
        PDF é guardado.
        """
        if not itens:
            raise RegraViolada("Importação sem itens não é criada.")
        if any(i.forma_pagamento_id is None for i in itens):
            raise RegraViolada("Item de lote sem forma de pagamento resolvida.")

        datas = [i.extraido.data for i in itens]
        importacao = Importacao(
            arquivo_nome=arquivo_nome,
            hash_arquivo=hash_arquivo(conteudo),
            arquivo_conteudo=conteudo,
            arquivo_tipo=arquivo_tipo,
            origem=origem,
            parser_usado=parser_usado,
            periodo_inicio=min(datas),
            periodo_fim=max(datas),
            total_itens=len(itens),
            status=StatusImportacao.AGUARDANDO_REVISAO,
            erro_mensagem=aviso,
        )
        self.session.add(importacao)
        self.session.flush()

        contexto = _ContextoEnriquecimento.carregar(self.session)
        for numero, lote in enumerate(itens, start=1):
            lote.extraido.linha_num = numero
            item = self._item(
                importacao,
                lote.extraido,
                None,
                contexto,
                forma_fixa_id=lote.forma_pagamento_id,
                pessoa_padrao_id=lote.pessoa_padrao_id,
                categoria_fixa_id=lote.categoria_id,
            )
            self.session.add(item)

        self._flush()
        return importacao

    def sugerir(
        self,
        extraido: ItemExtraido,
        contexto: _ContextoEnriquecimento,
        *,
        forma_fixa_id: int | None = None,
        pessoa_padrao_id: int | None = None,
        categoria_fixa_id: int | None = None,
    ) -> _Sugestao:
        """A sugestão que o item receberia no staging, sem gravar nada.

        Serve à gravação e à simulação da sync, que precisam mostrar a mesma
        coisa.
        """
        sugestao = contexto.sugerir_para(
            extraido.descricao,
            extraido.cartao_final,
            forma_fixa_id=forma_fixa_id,
            categoria_externa_id=extraido.categoria_externa_id,
            tipo=extraido.tipo,
        )
        # D-16: regra e titular do cartão primeiro; sem eles, o titular da
        # conta mapeada. Conta conjunta chega aqui como `None` (regra 3).
        if sugestao.pessoa_id is None:
            sugestao.pessoa_id = pessoa_padrao_id
        # Categoria fixa é de item sintético, que a origem já sabe classificar
        # (encargos de fatura): vence regra de texto, que não foi feita para ele.
        if categoria_fixa_id is not None:
            sugestao.categoria_id = categoria_fixa_id
        return sugestao

    def _transacao_gemea(
        self, extraido: ItemExtraido, forma_pagamento_id: int | None
    ) -> Transacao | None:
        """A transação viva que este item viraria, se já existir.

        Compara exatamente os campos que compõem o `hash_dedup` de
        `transacoes` — data, valor, descrição original, forma de pagamento e
        parcela. Compara campo a campo em vez de recalcular o md5 em Python:
        o hash é uma coluna gerada pelo Postgres, e manter uma segunda
        implementação dele aqui garantiria que as duas divergissem um dia.

        `parcela_num` entra como nulo porque a promoção não preenche essa
        coluna; se um dia passar a preencher, esta comparação tem que
        acompanhar — daí ela estar explícita e não omitida.

        Isto é **aviso**, não garantia. A garantia é o índice único, que roda
        no momento da inserção. Aqui o item ainda vai ser editado antes de
        aprovar, e uma troca de forma de pagamento na revisão muda o hash.
        """
        if extraido.data is None or extraido.valor is None:
            return None

        return self.session.scalar(
            select(Transacao).where(
                Transacao.deleted_em.is_(None),
                Transacao.data == extraido.data,
                Transacao.valor == extraido.valor,
                func.coalesce(Transacao.descricao_original, "") == (extraido.linha_bruta or ""),
                Transacao.forma_pagamento_id.is_not_distinct_from(forma_pagamento_id),
                Transacao.parcela_num.is_(None),
            )
        )

    def _item(
        self,
        importacao: Importacao,
        extraido: ItemExtraido,
        competencia: date | None,
        contexto: _ContextoEnriquecimento,
        *,
        forma_fixa_id: int | None = None,
        pessoa_padrao_id: int | None = None,
        categoria_fixa_id: int | None = None,
    ) -> ImportacaoItem:
        sugestao = self.sugerir(
            extraido,
            contexto,
            forma_fixa_id=forma_fixa_id,
            pessoa_padrao_id=pessoa_padrao_id,
            categoria_fixa_id=categoria_fixa_id,
        )

        # Já no banco? O item entra marcado, para a revisão distinguir o que é
        # novo do que é sobreposição. Sem isso, reimportar um extrato que cobre
        # semanas repetidas dá uma tela onde tudo parece igual, e a única
        # forma de descobrir o que era novo é aprovar e ler o resultado.
        gemea = self._transacao_gemea(extraido, sugestao.forma_pagamento_id)

        return ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta=extraido.linha_bruta,
            linha_num=extraido.linha_num,
            data=extraido.data,
            valor=extraido.valor,
            descricao_original=extraido.linha_bruta,
            tipo_sugerido=extraido.tipo,
            # Fatura: a competência é do vencimento, não da compra (D-02).
            # Extrato: o mês da própria data. A do item, quando existe, vem
            # antes da do documento: na Pluggy cada compra tem a sua fatura.
            competencia_sugerida=(
                extraido.competencia or competencia or primeiro_dia_do_mes(extraido.data)
            ),
            categoria_sugerida_id=sugestao.categoria_id,
            local_sugerido_id=sugestao.local_id,
            pessoa_sugerida_id=sugestao.pessoa_id,
            forma_pagamento_sugerida_id=sugestao.forma_pagamento_id,
            confianca=min(extraido.confianca, sugestao.confianca),
            origem_sugestao=sugestao.origem,
            # `transacao_id` fica nulo mesmo sendo duplicata: o CHECK da tabela
            # só permite preencher em item aprovado. A referência à transação
            # existente vai no texto, que é o que a tela mostra de qualquer
            # forma.
            id_externo=extraido.id_externo,
            observacao=extraido.observacao,
            status=StatusItem.DUPLICADO if gemea else StatusItem.PENDENTE,
            motivo_rejeicao=(
                f"Já existe no banco: transação #{gemea.id} de "
                f"{gemea.data:%d/%m/%Y}, {gemea.valor}."
                if gemea
                else None
            ),
        )

    # -- revisão ---------------------------------------------------------

    def get(self, importacao_id: int) -> Importacao:
        obj = self.session.get(Importacao, importacao_id)
        if obj is None or obj.deleted_em is not None:
            raise NaoEncontrado("importação", importacao_id)
        return obj

    def listar(self) -> list[Importacao]:
        return list(
            self.session.scalars(
                select(Importacao)
                .where(Importacao.deleted_em.is_(None))
                .order_by(Importacao.id.desc())
            )
        )

    def itens(self, importacao_id: int, status: StatusItem | None = None) -> list[ImportacaoItem]:
        self.get(importacao_id)
        query = select(ImportacaoItem).where(
            ImportacaoItem.importacao_id == importacao_id,
            ImportacaoItem.deleted_em.is_(None),
        )
        if status is not None:
            query = query.where(ImportacaoItem.status == status)
        return list(self.session.scalars(query.order_by(ImportacaoItem.linha_num)))

    def ajustar(self, item_id: int, dados: dict[str, Any]) -> ImportacaoItem:
        """Correção do usuário antes de aprovar.

        Toda correção aqui vira regra (D-09) — é o que faz a próxima
        importação já vir certa.
        """
        item = self._item_pendente(item_id)
        for campo, valor in dados.items():
            setattr(item, campo, valor)

        if item.categoria_sugerida_id is not None and item.descricao_original:
            self._reforcar_regra(item)

        self._flush()
        return item

    def reaplicar_regras(self, importacao_id: int | None = None) -> dict[str, int]:
        """Roda o motor de sugestão de novo sobre os itens ainda pendentes.

        Serve ao ciclo que a D-09 descreve: você corrige uma linha, a regra
        nasce, e as outras 29 linhas do mesmo estabelecimento se resolvem sem
        você tocar em cada uma.

        Só mexe em item **pendente** — o que já foi aprovado virou transação e
        não se reescreve por regra nova. E só preenche campo vazio: se você
        escolheu a categoria na mão, a regra não passa por cima.
        """
        query = select(ImportacaoItem).where(
            ImportacaoItem.status == StatusItem.PENDENTE,
            ImportacaoItem.deleted_em.is_(None),
        )
        if importacao_id is not None:
            self.get(importacao_id)
            query = query.where(ImportacaoItem.importacao_id == importacao_id)

        itens = list(self.session.scalars(query))
        contexto = _ContextoEnriquecimento.carregar(self.session)

        alterados = 0
        for item in itens:
            sugestao = contexto.sugerir_para(_descricao_curta(item), _cartao_de(item.linha_bruta))
            antes = (
                item.categoria_sugerida_id,
                item.local_sugerido_id,
                item.pessoa_sugerida_id,
            )

            item.categoria_sugerida_id = item.categoria_sugerida_id or sugestao.categoria_id
            item.local_sugerido_id = item.local_sugerido_id or sugestao.local_id
            item.pessoa_sugerida_id = item.pessoa_sugerida_id or sugestao.pessoa_id

            depois = (
                item.categoria_sugerida_id,
                item.local_sugerido_id,
                item.pessoa_sugerida_id,
            )
            if antes != depois:
                item.origem_sugestao = sugestao.origem
                item.confianca = sugestao.confianca
                alterados += 1

        self._flush()
        return {"avaliados": len(itens), "alterados": alterados}

    def rejeitar(self, ids: Sequence[int], motivo: str | None = None) -> int:
        afetados = 0
        for item_id in ids:
            item = self._item_pendente(item_id)
            item.status = StatusItem.REJEITADO
            item.motivo_rejeicao = motivo
            afetados += 1
        self._flush()
        return afetados

    # -- promoção --------------------------------------------------------

    def aprovar(self, ids: Sequence[int]) -> dict[str, Any]:
        """Promove itens para `transacoes`.

        É o único caminho por onde dado de ingestão vira dado real, e ele
        passa por aqui só porque o usuário mandou.

        Duplicata não derruba o lote: o item vira `duplicado` e os outros
        seguem. Reimportar dois meses que se sobrepõem é comum demais para
        virar erro fatal.
        """
        promovidos: list[int] = []
        duplicados: list[int] = []
        erros: list[dict[str, Any]] = []

        for item_id in ids:
            item = self._item_pendente(item_id)
            try:
                with self.session.begin_nested():
                    transacao = self._promover(item)
                    item.transacao_id = transacao.id
                    item.status = StatusItem.APROVADO
                promovidos.append(item_id)
            except IntegrityError as exc:
                mensagem = _mensagem_integridade(exc)
                if "idêntica" in mensagem:
                    item.status = StatusItem.DUPLICADO
                    item.motivo_rejeicao = "Já existe transação idêntica."
                    duplicados.append(item_id)
                else:
                    erros.append({"item_id": item_id, "erro": mensagem})
            except RegraViolada as exc:
                erros.append({"item_id": item_id, "erro": str(exc)})

        self._atualizar_contadores(ids)
        self._flush()
        return {
            "promovidos": len(promovidos),
            "duplicados": len(duplicados),
            "erros": erros,
        }

    def _promover(self, item: ImportacaoItem) -> Transacao:
        if item.data is None or item.valor is None:
            raise RegraViolada("Item sem data ou valor não pode ser promovido.")

        tipo = item.tipo_sugerido or TipoTransacao.DESPESA

        if tipo is TipoTransacao.TRANSFERENCIA:
            # `transacoes` exige origem e destino diferentes, e o parser não
            # sabe quais contas são. Sem isso o check do banco recusaria com
            # mensagem críptica; aqui a recusa explica o que fazer.
            raise RegraViolada(
                "Transferência precisa de conta de origem e destino. "
                "Edite o item e escolha as contas, ou rejeite-o — o gasto do "
                "cartão já vem detalhado pela fatura (D-05)."
            )

        transacao = Transacao(
            data=item.data,
            competencia=item.competencia_sugerida or primeiro_dia_do_mes(item.data),
            valor=item.valor,
            tipo=tipo,
            descricao=_descricao_curta(item),
            # Texto cru do extrato, imutável (regra 11).
            descricao_original=item.linha_bruta,
            categoria_id=item.categoria_sugerida_id,
            pessoa_id=item.pessoa_sugerida_id,
            forma_pagamento_id=item.forma_pagamento_sugerida_id,
            local_id=item.local_sugerido_id,
            importacao_id=item.importacao_id,
        )
        self.session.add(transacao)
        self.session.flush()
        return transacao

    def _atualizar_contadores(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        importacao_ids = set(
            self.session.scalars(
                select(ImportacaoItem.importacao_id).where(ImportacaoItem.id.in_(ids))
            )
        )
        for importacao_id in importacao_ids:
            importacao = self.session.get(Importacao, importacao_id)
            if importacao is None:
                continue
            importacao.itens_aprovados = int(
                self.session.scalar(
                    select(func.count())
                    .select_from(ImportacaoItem)
                    .where(
                        ImportacaoItem.importacao_id == importacao_id,
                        ImportacaoItem.status == StatusItem.APROVADO,
                    )
                )
                or 0
            )
            pendentes = self.session.scalar(
                select(func.count())
                .select_from(ImportacaoItem)
                .where(
                    ImportacaoItem.importacao_id == importacao_id,
                    ImportacaoItem.status == StatusItem.PENDENTE,
                    ImportacaoItem.deleted_em.is_(None),
                )
            )
            if not pendentes:
                importacao.status = StatusImportacao.CONCLUIDA

    # -- regras ----------------------------------------------------------

    def _reforcar_regra(self, item: ImportacaoItem) -> None:
        """Correção vira regra, ou reforça a que já existe (D-09)."""
        reforcar_regra(
            self.session,
            _padrao_de(item.linha_bruta),
            item.categoria_sugerida_id,
            item.pessoa_sugerida_id,
        )

    # -- utilidades ------------------------------------------------------

    def _item_pendente(self, item_id: int) -> ImportacaoItem:
        item = self.session.get(ImportacaoItem, item_id)
        if item is None or item.deleted_em is not None:
            raise NaoEncontrado("item de importação", item_id)
        if item.status is StatusItem.APROVADO:
            raise RegraViolada(
                f"Item {item_id} já foi aprovado e virou a transação "
                f"{item.transacao_id}. Para desfazer, exclua a transação."
            )
        return item

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflito(_mensagem_integridade(exc)) from exc


# --------------------------------------------------------------------------
# Enriquecimento
# --------------------------------------------------------------------------

#: Lixo de gateway que atrapalha o casamento por nome: "Ec *Melimais",
#: "Mp *Produtosglobo", "Ifd*Eleandra", "Dl*Google".
_PREFIXO_GATEWAY = re.compile(r"^(?:[a-z]{2,4}\s?\*)\s*", re.I)


def _descricao_curta(item: ImportacaoItem) -> str:
    """A descrição editável, derivada da linha crua."""
    bruta = item.linha_bruta
    # Tira data, final do cartão e valor, sobrando o estabelecimento.
    limpo = re.sub(r"^\d{2}\s+[A-Z]{3}\s+(?:•+\s*\d{4}\s+)?", "", bruta)
    limpo = re.sub(r"\s+[−-]?R?\$?\s?[\d.]+,\d{2}$", "", limpo)
    limpo = _PREFIXO_GATEWAY.sub("", limpo).strip()
    return limpo or bruta[:200]


def _cartao_de(linha_bruta: str) -> str | None:
    """Os 4 dígitos do cartão, quando a linha traz `•••• 7704`."""
    casou = re.search(r"•+\s*(\d{4})\b", linha_bruta)
    return casou.group(1) if casou else None


#: Onde a descrição do extrato deixa de ser útil como padrão.
#:
#: Uma linha de Pix continua com CPF mascarado, banco, agência e conta — tudo
#: diferente a cada transferência. Guardar isso gera regra de uso único, que
#: nunca mais casa e só enche a tabela. Cortar aqui deixa "Transferência
#: enviada pelo Pix FULANO", que é o pedaço que de fato se repete.
_DOCUMENTO_MASCARADO = re.compile(r"\s+-\s+•")


def _padrao_de(linha_bruta: str) -> str:
    """Trecho estável da linha, para virar padrão de regra.

    Data e valor mudam todo mês; o nome do estabelecimento ou da contraparte
    não.
    """
    limpo = re.sub(r"^\d{2}\s+[A-Z]{3}\s+(?:•+\s*\d{4}\s+)?", "", linha_bruta)
    limpo = re.sub(r"\s+[−-]?R?\$?\s?[\d.]+,\d{2}$", "", limpo)
    limpo = _DOCUMENTO_MASCARADO.split(limpo)[0]
    return _PREFIXO_GATEWAY.sub("", limpo).strip(" -")[:120]


@dataclass(slots=True)
class ItemLote:
    """Um item de `importar_lote`, com o que o PDF não traz.

    `forma_pagamento_id` vem do mapeamento da conta e vence o final do
    cartão; `pessoa_padrao_id` é o titular da conta (nulo = conjunta);
    `categoria_id` é a categoria fixa de item sintético (encargos de fatura):
    vence regra e local.
    """

    extraido: ItemExtraido
    #: Nulo só enquanto a sync planeja uma forma que ainda vai criar (D-21);
    #: `importar_lote` recusa item que chegue sem forma.
    forma_pagamento_id: int | None
    pessoa_padrao_id: int | None = None
    categoria_id: int | None = None


class _Sugestao:
    __slots__ = (
        "categoria_id",
        "confianca",
        "forma_pagamento_id",
        "local_id",
        "origem",
        "pessoa_id",
    )

    def __init__(self) -> None:
        self.categoria_id: int | None = None
        self.local_id: int | None = None
        self.pessoa_id: int | None = None
        self.forma_pagamento_id: int | None = None
        self.origem: str = "parser"
        self.confianca: Decimal = Decimal("0.50")


class _ContextoEnriquecimento:
    """Cadastros carregados uma vez, para não fazer SELECT por linha."""

    def __init__(
        self,
        regras: list[RegraCategorizacao],
        locais: list[Local],
        formas: list[FormaPagamento],
        categorias_pluggy: dict[str, tuple[int, TipoTransacao]] | None = None,
    ) -> None:
        self.regras = sorted(regras, key=lambda r: r.prioridade)
        self.locais = locais
        self.formas = formas
        #: `categoryId` da Pluggy -> (categoria daqui, tipo dela). D-21.
        self.categorias_pluggy = categorias_pluggy or {}
        # Menor id entre os créditos, explicitamente — e não "o primeiro que a
        # lista trouxer". `forma_pagamento_id` entra no `hash_dedup`, então
        # esta escolha é o que decide se reimportar um extrato sobreposto vai
        # reconhecer a linha repetida. Sem critério fixo, a mesma linha ganha
        # forma diferente entre duas importações, o hash muda e a duplicata
        # passa direto — a proteção some justamente no caso em que ela existe
        # para servir.
        self.credito_padrao = min(
            (f for f in formas if f.tipo is TipoPagamento.CREDITO),
            key=lambda f: f.id,
            default=None,
        )

    @classmethod
    def carregar(cls, session: Session) -> _ContextoEnriquecimento:
        """Carrega o contexto em ordem fixa.

        Os três `order_by` não são estética. A sugestão percorre estas listas
        e para no primeiro casamento, então a ordem **é** a regra de desempate
        — e o resultado alimenta o `hash_dedup`. Sem `ORDER BY`, o Postgres
        pode devolver as linhas em ordem física, que muda a cada UPDATE ou
        VACUUM: a mesma importação, rodada duas vezes, daria sugestões
        diferentes sem nada no código ter mudado.
        """
        return cls(
            list(
                session.scalars(
                    select(RegraCategorizacao)
                    .where(
                        RegraCategorizacao.deleted_em.is_(None),
                        RegraCategorizacao.ativo.is_(True),
                    )
                    .order_by(RegraCategorizacao.prioridade, RegraCategorizacao.id)
                )
            ),
            list(
                session.scalars(select(Local).where(Local.deleted_em.is_(None)).order_by(Local.id))
            ),
            list(
                session.scalars(
                    select(FormaPagamento)
                    .where(
                        FormaPagamento.deleted_em.is_(None),
                        FormaPagamento.ativo.is_(True),
                    )
                    .order_by(FormaPagamento.id)
                )
            ),
            carregar_categorias_pluggy(session),
        )

    def sugerir(self, extraido: ItemExtraido) -> _Sugestao:
        return self.sugerir_para(
            extraido.descricao,
            extraido.cartao_final,
            categoria_externa_id=extraido.categoria_externa_id,
            tipo=extraido.tipo,
        )

    def sugerir_para(
        self,
        descricao: str,
        cartao_final: str | None,
        *,
        forma_fixa_id: int | None = None,
        categoria_externa_id: str | None = None,
        tipo: TipoTransacao | None = None,
    ) -> _Sugestao:
        """O motor de sugestão, em cima de texto puro.

        Recebe primitivos em vez de `ItemExtraido` porque a reaplicação de
        regras parte de um item já gravado, não de uma linha recém-extraída —
        e as duas têm que passar exatamente pelo mesmo caminho, senão o que a
        tela promete divergiria do que a importação faz.
        """
        sugestao = _Sugestao()
        alvo = sem_acento(descricao).upper()

        # 1. Regras — exatas e gratuitas, rodam antes de tudo (D-09).
        for regra in self.regras:
            if self._casa(regra, alvo):
                sugestao.categoria_id = regra.categoria_id or sugestao.categoria_id
                sugestao.local_id = regra.local_id or sugestao.local_id
                sugestao.pessoa_id = regra.pessoa_id or sugestao.pessoa_id
                sugestao.origem = "regra"
                sugestao.confianca = Decimal("0.95")
                break

        # 2. Mapeamento de categorias da Pluggy (D-21), só quando a regra não
        #    deu categoria e o tipo da categoria mapeada é o do item.
        #    Transferência não recebe categoria: em `transacoes` ela não tem.
        if (
            sugestao.categoria_id is None
            and categoria_externa_id
            and tipo is not None
            and tipo is not TipoTransacao.TRANSFERENCIA
        ):
            mapeada = self.categorias_pluggy.get(categoria_externa_id)
            if mapeada is not None and mapeada[1] is tipo:
                sugestao.categoria_id = mapeada[0]
                sugestao.origem = "pluggy"
                sugestao.confianca = CONFIANCA_CATEGORIA_PLUGGY

        # 3. Local já conhecido: casa pelo nome normalizado e herda a
        #    categoria padrão dele, se ninguém antes deu categoria.
        if sugestao.local_id is None:
            normalizado = normalizar_nome(descricao)
            for local in self.locais:
                if local.nome_normalizado and local.nome_normalizado in normalizado:
                    sugestao.local_id = local.id
                    if sugestao.categoria_id is None and local.categoria_padrao_id:
                        sugestao.categoria_id = local.categoria_padrao_id
                        sugestao.origem = "alias"
                        sugestao.confianca = max(sugestao.confianca, Decimal("0.80"))
                    break

        # 4. Forma fixa (sync da Pluggy): a forma vem sempre do mapeamento da
        #    conta, inclusive para cartão virtual com outro final — nunca o
        #    crédito genérico do seed. O final ainda serve para achar o
        #    titular de um cartão cadastrado com aqueles 4 dígitos (D-16).
        if forma_fixa_id is not None:
            sugestao.forma_pagamento_id = forma_fixa_id
            if cartao_final and sugestao.pessoa_id is None:
                exata = next(
                    (f for f in self.formas if f.apelido.strip().endswith(cartao_final)), None
                )
                if exata is not None and exata.titular_id is not None:
                    sugestao.pessoa_id = exata.titular_id
            return sugestao

        # 4. Forma de pagamento pelo final do cartão. Casa com a forma cujo
        #    apelido termina nesses 4 dígitos ("Nubank •••• 7704"); sem ela,
        #    cai no cartão de crédito genérico do seed.
        if cartao_final:
            forma = next(
                (f for f in self.formas if f.apelido.strip().endswith(cartao_final)),
                self.credito_padrao,
            )
            if forma is not None:
                sugestao.forma_pagamento_id = forma.id
                # Cartão cadastrado com titular resolve a pessoa sozinho.
                if sugestao.pessoa_id is None and forma.titular_id is not None:
                    sugestao.pessoa_id = forma.titular_id

        return sugestao

    def _casa(self, regra: RegraCategorizacao, alvo: str) -> bool:
        padrao = sem_acento(regra.padrao).upper()
        if regra.tipo_match == "exato":
            return alvo == padrao
        if regra.tipo_match == "regex":
            try:
                return re.search(regra.padrao, alvo, re.I) is not None
            except re.error:
                # Regex inválida cadastrada pelo usuário não derruba a
                # importação inteira.
                return False
        return padrao in alvo
