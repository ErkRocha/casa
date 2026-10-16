"""O que está esperando decisão na revisão, por motivo (D-21, D-22).

Desde a D-21 a sync promove sozinha o item limpo; o que fica no staging tem
um motivo. Aqui ele é deduzido do próprio item, no banco, na mesma ordem de
`promocao_pluggy.MOTIVOS` — o primeiro que se aplica é o do item. A leitura
crua da Pluggy (a confiança da conversão) não fica no staging, então o
motivo "confiança" não tem como ser reconhecido aqui: item pendente sem
nenhum dos outros motivos aparece como "outros" (PDF, por exemplo).

As decisões da tela de revisão (D-22) moram aqui também: duplicata (manter
só um, são dois) e transferência (confirmar, não é transferência). Elas
gravam pelo `IngestaoService`, que continua sendo o único caminho do staging
para `transacoes` (D-07).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from sqlalchemy import Row, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_MESMA_PESSOA, OBS_PAGAMENTO_NA_CONTA, OBS_PAGAMENTO_NO_CARTAO
from app.enums import StatusItem, TipoPagamento, TipoTransacao
from app.models import Conta, FormaPagamento, Importacao, ImportacaoItem
from app.schemas.revisar import (
    ConfirmarTransferencia,
    ContaResumo,
    ErroItem,
    GrupoDuplicata,
    ItemRevisar,
    MotivoRevisao,
    ResultadoRevisao,
    RevisarResumo,
    TipoTransferencia,
    TransferenciaRevisar,
)
from app.services.base import Conflito, NaoEncontrado, RegraViolada, _mensagem_integridade
from app.services.comprovante_pluggy import ler_comprovante
from app.services.ingestao import IngestaoService, descricao_curta
from app.services.promocao_pluggy import MARCA_DUPLICATA, MOTIVOS, NOTA_DUPLICATA

#: Os motivos que a revisão reconhece, na ordem de leitura e de checagem.
MOTIVOS_REVISAO: dict[str, str] = {
    "possivel_duplicata": MOTIVOS["possivel_duplicata"],
    "encargos": MOTIVOS["encargos"],
    "pagamento_fatura_cartao": MOTIVOS["pagamento_fatura_cartao"],
    "transferencia": MOTIVOS["transferencia"],
    "observacao": MOTIVOS["observacao"],
    "sem_categoria": MOTIVOS["sem_categoria"],
    "outros": "outros",
}

#: Classificação de um item de `importacao_itens` (alias `i`). Fragmento
#: reaproveitado pela listagem da revisão.
MOTIVO_SQL = """
    CASE
      WHEN strpos(coalesce(i.observacao, ''), :marca_duplicata) > 0 THEN 'possivel_duplicata'
      WHEN i.id_externo LIKE 'bill:%' THEN 'encargos'
      WHEN i.tipo_sugerido = 'transferencia'
        AND strpos(coalesce(i.observacao, ''), :marca_cartao) > 0 THEN 'pagamento_fatura_cartao'
      WHEN i.tipo_sugerido = 'transferencia' THEN 'transferencia'
      WHEN coalesce(i.observacao, '') <> '' THEN 'observacao'
      WHEN i.categoria_sugerida_id IS NULL THEN 'sem_categoria'
      ELSE 'outros'
    END
"""

#: Pendente, vivo e de importação viva.
PENDENTES_SQL = """
    FROM importacao_itens i
    JOIN importacoes imp ON imp.id = i.importacao_id AND imp.deleted_em IS NULL
    WHERE i.status = 'pendente' AND i.deleted_em IS NULL
"""

_RESUMO = f"""
    SELECT {MOTIVO_SQL} AS motivo, count(*) AS quantidade
    {PENDENTES_SQL}
    GROUP BY 1
"""

#: O item com os nomes que a tela mostra. Vivo e de importação viva; o
#: status fica para quem usa.
_COLUNAS = f"""
    SELECT i.id, i.importacao_id, {MOTIVO_SQL} AS motivo, i.status::text AS status,
           i.data, i.valor, i.tipo_sugerido::text AS tipo_sugerido, i.competencia_sugerida,
           i.linha_bruta, i.descricao_original, i.observacao, i.id_externo,
           i.categoria_sugerida_id, c.nome AS categoria_nome,
           i.pessoa_sugerida_id, p.nome AS pessoa_nome,
           i.forma_pagamento_sugerida_id, f.tipo::text AS forma_pagamento_tipo,
           f.apelido AS forma_pagamento_apelido, f.conta_id, ct.nome AS conta_nome,
           i.transacao_id
    FROM importacao_itens i
    JOIN importacoes imp ON imp.id = i.importacao_id AND imp.deleted_em IS NULL
    LEFT JOIN categorias c ON c.id = i.categoria_sugerida_id
    LEFT JOIN pessoas p ON p.id = i.pessoa_sugerida_id
    LEFT JOIN formas_pagamento f ON f.id = i.forma_pagamento_sugerida_id
    LEFT JOIN contas ct ON ct.id = f.conta_id
    WHERE i.deleted_em IS NULL
"""

_PENDENTES_POR_MOTIVO = f"""
    SELECT * FROM ({_COLUNAS} AND i.status = 'pendente') x
    WHERE x.motivo = ANY(:motivos)
    ORDER BY x.data DESC NULLS LAST, x.id
"""

_UM_ITEM = f"{_COLUNAS} AND i.id = :id"

#: Os grupos de possível duplicata: cada item pendente marcado pela sync,
#: com os gêmeos de mesma conta, data, valor e descrição — pendentes ou já
#: transação viva.
_DUPLICATAS = f"""
    WITH base AS ({_COLUNAS} AND i.status IN ('pendente', 'aprovado')),
    marcados AS (
      SELECT DISTINCT data, valor, coalesce(descricao_original, '') AS descricao, conta_id
      FROM base
      WHERE status = 'pendente' AND motivo = 'possivel_duplicata'
    )
    SELECT b.*
    FROM base b
    JOIN marcados m
      ON m.data = b.data AND m.valor = b.valor
     AND m.descricao = coalesce(b.descricao_original, '')
     AND m.conta_id IS NOT DISTINCT FROM b.conta_id
    WHERE b.status = 'pendente'
       OR EXISTS (
         SELECT 1 FROM transacoes t WHERE t.id = b.transacao_id AND t.deleted_em IS NULL
       )
    ORDER BY b.data DESC, b.valor DESC, b.status, b.id
"""

#: Até quantos dias as duas pontas de uma transferência podem estar
#: separadas: Pix cai na hora, TED de sexta cai na segunda.
DIAS_ENTRE_PONTAS = 3

#: As notas que fazem de um item uma transferência na revisão.
NOTAS_DE_TRANSFERENCIA = (OBS_PAGAMENTO_NO_CARTAO, OBS_PAGAMENTO_NA_CONTA, OBS_MESMA_PESSOA)

MOTIVO_LADO_DO_CARTAO = (
    "Lado do cartão do pagamento de fatura: o gasto já está nas compras do cartão (D-05)."
)
MOTIVO_FATURA_DA_PROPRIA_CONTA = (
    "Pagamento de fatura de um cartão da própria conta: o gasto já está nas "
    "compras do cartão, e não há outra conta para registrar a transferência (D-05)."
)
MENSAGEM_ITENS_IDENTICOS = (
    "Para o banco os itens são a mesma transação: mesma data, valor, descrição "
    "original e forma de pagamento. O índice de deduplicação aceita só uma "
    "transação assim (D-07); registrar as duas exige mudar o schema."
)


def parametros_motivo() -> dict[str, str]:
    return {"marca_duplicata": MARCA_DUPLICATA, "marca_cartao": OBS_PAGAMENTO_NO_CARTAO}


class RevisaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- leitura -----------------------------------------------------------

    def resumo(self) -> RevisarResumo:
        contagem = {
            linha.motivo: int(linha.quantidade)
            for linha in self.session.execute(text(_RESUMO), parametros_motivo())
        }
        motivos = [
            MotivoRevisao(motivo=chave, rotulo=rotulo, quantidade=contagem[chave])
            for chave, rotulo in MOTIVOS_REVISAO.items()
            if contagem.get(chave)
        ]
        return RevisarResumo(total=sum(m.quantidade for m in motivos), motivos=motivos)

    def itens(self, motivo: str | None = None) -> list[ItemRevisar]:
        """Pendentes de um motivo (ou de todos), mais recentes primeiro."""
        return [_item(linha) for linha in self._pendentes([motivo] if motivo else MOTIVOS_REVISAO)]

    def item(self, item_id: int) -> ItemRevisar:
        linha = self.session.execute(
            text(_UM_ITEM), {**parametros_motivo(), "id": item_id}
        ).one_or_none()
        if linha is None:
            raise NaoEncontrado("item de importação", item_id)
        return _item(linha)

    def duplicatas(self) -> list[GrupoDuplicata]:
        grupos: dict[tuple[Any, ...], list[Row[Any]]] = defaultdict(list)
        for linha in self.session.execute(text(_DUPLICATAS), parametros_motivo()):
            chave = (linha.data, linha.valor, linha.descricao_original or "", linha.conta_id)
            grupos[chave].append(linha)

        resultado = []
        for (data, valor, _, _), linhas in grupos.items():
            itens = [_item(linha) for linha in linhas]
            formas = [i.forma_pagamento_sugerida_id for i in itens]
            resultado.append(
                GrupoDuplicata(
                    data=data,
                    valor=valor,
                    descricao=itens[0].descricao,
                    itens=itens,
                    ja_lancado=any(i.status is StatusItem.APROVADO for i in itens),
                    # O `hash_dedup` leva data, valor, descrição original e
                    # forma: no grupo, só a forma pode diferir.
                    podem_ser_dois=len(set(formas)) == len(formas),
                )
            )
        return resultado

    def transferencias(self) -> list[TransferenciaRevisar]:
        """Transferências pendentes, com origem e destino sugeridos.

        O staging não guarda as contas de uma transferência. O que dá para
        saber: a conta do item (pela forma de pagamento), o sentido do
        dinheiro (pela transação da Pluggy no comprovante) e, quando as duas
        pontas estão na revisão, a conta da outra ponta.
        """
        linhas = list(self._pendentes(["transferencia", "pagamento_fatura_cartao"]))
        direcoes = self._direcoes(linhas)
        itens = {linha.id: _item(linha) for linha in linhas}
        tipos = {i.id: _tipo_transferencia(i.observacao) for i in itens.values()}
        pares = _parear(list(itens.values()), direcoes, tipos)
        cartoes = self._cartoes_por_conta()

        resultado = []
        for item in itens.values():
            tipo = tipos[item.id]
            direcao = direcoes.get(item.id)
            par = itens.get(pares[item.id]) if item.id in pares else None
            fatura_de: str | None = None
            ao_confirmar: Literal["transferencia", "descartar"] = "transferencia"

            if tipo in ("pagamento_fatura_cartao", "pagamento_fatura_conta"):
                # Pagamento de fatura: sai da conta que paga e vai para a conta
                # do cartão. O cartão é forma da conta que paga a fatura, então
                # sem a outra ponta vale a conta do próprio cartão.
                lado_cartao = item if tipo == "pagamento_fatura_cartao" else par
                lado_conta = par if tipo == "pagamento_fatura_cartao" else item
                if lado_cartao is not None:
                    fatura_de = lado_cartao.forma_pagamento_apelido
                    destino = _conta(lado_cartao)
                elif item.conta_id in cartoes:
                    fatura_de = " ou ".join(cartoes[item.conta_id])
                    destino = _conta(item)
                else:
                    destino = None
                origem = _conta(lado_conta) if lado_conta is not None else destino
            else:
                conta = _conta(item)
                conta_par = _conta(par) if par is not None else None
                origem, destino = (
                    (conta, conta_par)
                    if direcao == "saida"
                    else (conta_par, conta)
                    if direcao == "entrada"
                    else (None, None)
                )

            if origem is not None and destino is not None and origem.id == destino.id:
                # Fatura de cartão da própria conta: a transferência não teria
                # para onde ir, e o gasto já veio pelas compras (D-05).
                destino, ao_confirmar = None, "descartar"

            resultado.append(
                TransferenciaRevisar(
                    item=item,
                    tipo=tipo,
                    direcao=direcao,
                    origem=origem,
                    destino=destino,
                    fatura_de=fatura_de,
                    par_item_id=par.id if par is not None else None,
                    ao_confirmar=ao_confirmar,
                )
            )
        return resultado

    # -- decisões ----------------------------------------------------------

    def resolver_duplicata(
        self, manter_ids: Sequence[int], descartar_ids: Sequence[int]
    ) -> ResultadoRevisao:
        """ "Manter só um" ou "são dois" (D-22).

        Os descartados viram `rejeitado`, com o item que ficou no motivo. Os
        mantidos perdem a nota de possível duplicata e, se não sobra outro
        motivo, são aprovados; senão seguem na revisão pelo próximo motivo.
        """
        ids = [*manter_ids, *descartar_ids]
        if len(set(ids)) != len(ids):
            raise RegraViolada("Cada item entra uma vez só: ou fica, ou sai.")
        grupo = next(
            (g for g in self.duplicatas() if set(ids) <= {i.id for i in g.itens}),
            None,
        )
        if grupo is None:
            raise RegraViolada("Os itens não são de um mesmo grupo de possível duplicata.")

        por_id = {i.id: i for i in grupo.itens}
        for item_id in descartar_ids:
            if por_id[item_id].status is not StatusItem.PENDENTE:
                raise RegraViolada(
                    f"Item {item_id} já é a transação #{por_id[item_id].transacao_id}. "
                    "Para tirá-la, exclua a transação em Lançamentos."
                )
        mantidos = [por_id[i] for i in manter_ids]
        if len(mantidos) > 1 and not grupo.podem_ser_dois:
            raise RegraViolada(MENSAGEM_ITENS_IDENTICOS)

        ingestao = IngestaoService(self.session)
        resultado = ResultadoRevisao()
        fica = mantidos[0]
        if descartar_ids:
            referencia = (
                f"a transação #{fica.transacao_id}" if fica.transacao_id else f"o item #{fica.id}"
            )
            resultado.descartados = ingestao.rejeitar(
                descartar_ids, f"Duplicata descartada na revisão: ficou {referencia}."
            )

        aprovar: list[int] = []
        for mantido in mantidos:
            if mantido.status is not StatusItem.PENDENTE:
                continue
            item = self._item_modelo(mantido.id)
            item.observacao = _sem_notas(item.observacao, [NOTA_DUPLICATA])
            if _limpo(item):
                aprovar.append(item.id)
            else:
                resultado.pendentes += 1
        self._flush()

        if aprovar:
            aprovacao = ingestao.aprovar(aprovar)
            resultado.aprovados = int(aprovacao["promovidos"])
            resultado.erros.extend(ErroItem(**erro) for erro in aprovacao["erros"])
            for item_id in aprovar:
                if self._item_modelo(item_id).status is StatusItem.DUPLICADO:
                    resultado.erros.append(
                        ErroItem(item_id=item_id, erro="Já existe transação idêntica (D-07).")
                    )
        return resultado

    def confirmar_transferencias(
        self, pedidos: Iterable[ConfirmarTransferencia]
    ) -> ResultadoRevisao:
        """Confirma uma ou várias transferências ("confirmar todas").

        Com origem e destino (pedidos ou sugeridos), grava a transferência e
        descarta a outra ponta, se ela também estava na revisão. Pagamento de
        fatura de cartão da própria conta não tem o que gravar: confirmar
        descarta o item, com o motivo (D-05). Erro num item não derruba os
        outros.
        """
        atuais = {t.item.id: t for t in self.transferencias()}
        ingestao = IngestaoService(self.session)
        resultado = ResultadoRevisao()
        feitos: set[int] = set()

        for pedido in pedidos:
            if pedido.item_id in feitos:
                continue
            atual = atuais.get(pedido.item_id)
            if atual is None:
                resultado.erros.append(
                    ErroItem(
                        item_id=pedido.item_id,
                        erro="Não está entre as transferências pendentes da revisão.",
                    )
                )
                continue

            escolheu = pedido.conta_origem_id is not None or pedido.conta_destino_id is not None
            if atual.ao_confirmar == "descartar" and not escolheu:
                motivo = (
                    MOTIVO_LADO_DO_CARTAO
                    if atual.tipo == "pagamento_fatura_cartao"
                    else MOTIVO_FATURA_DA_PROPRIA_CONTA
                )
                resultado.descartados += ingestao.rejeitar([pedido.item_id], motivo)
                feitos.add(pedido.item_id)
                continue

            origem = pedido.conta_origem_id
            if origem is None and atual.origem is not None:
                origem = atual.origem.id
            destino = pedido.conta_destino_id
            if destino is None and atual.destino is not None:
                destino = atual.destino.id
            erro = self._erro_nas_contas(origem, destino)
            if erro is not None or origem is None or destino is None:
                resultado.erros.append(
                    ErroItem(item_id=pedido.item_id, erro=erro or "Faltam as contas.")
                )
                continue

            try:
                with self.session.begin_nested():
                    transacao = ingestao.confirmar_transferencia(pedido.item_id, origem, destino)
            except IntegrityError as exc:
                resultado.erros.append(
                    ErroItem(item_id=pedido.item_id, erro=_mensagem_integridade(exc))
                )
                continue
            except RegraViolada as exc:
                resultado.erros.append(ErroItem(item_id=pedido.item_id, erro=str(exc)))
                continue
            resultado.aprovados += 1
            feitos.add(pedido.item_id)

            par = atual.par_item_id
            if par is not None and par not in feitos:
                resultado.descartados += ingestao.rejeitar(
                    [par],
                    f"Outra ponta da transferência #{transacao.id}, gravada pelo item "
                    f"#{pedido.item_id} (D-05).",
                )
                feitos.add(par)

        self._flush()
        return resultado

    def nao_e_transferencia(self, item_id: int, tipo: TipoTransacao | None) -> ItemRevisar:
        """Vira despesa ou receita e sai da aba de transferências.

        Sem tipo informado, vale o sentido do dinheiro. As notas de
        transferência saem da observação; o item segue pendente, agora pelo
        próximo motivo (sem categoria, por exemplo).
        """
        atual = next((t for t in self.transferencias() if t.item.id == item_id), None)
        if atual is None:
            raise RegraViolada(
                f"Item {item_id} não está entre as transferências pendentes da revisão."
            )
        if tipo is None:
            tipo = {"saida": TipoTransacao.DESPESA, "entrada": TipoTransacao.RECEITA}.get(
                atual.direcao or ""
            )
        if tipo is None:
            raise RegraViolada(
                "Não dá para saber se o dinheiro entrou ou saiu: diga se é despesa ou receita."
            )
        item = self._item_modelo(item_id)
        item.tipo_sugerido = tipo
        item.observacao = _sem_notas(item.observacao, NOTAS_DE_TRANSFERENCIA)
        self._flush()
        return self.item(item_id)

    # -- utilidades --------------------------------------------------------

    def _pendentes(self, motivos: Iterable[str]) -> Sequence[Row[Any]]:
        return self.session.execute(
            text(_PENDENTES_POR_MOTIVO), {**parametros_motivo(), "motivos": list(motivos)}
        ).all()

    def _direcoes(self, linhas: Sequence[Row[Any]]) -> dict[int, Literal["entrada", "saida"]]:
        """Entrada ou saída, pela transação da Pluggy guardada no comprovante.

        Um comprovante por importação, lido uma vez. Item sem id da Pluggy
        (PDF) ou fora do comprovante fica sem sentido conhecido.
        """
        por_importacao: dict[int, list[Row[Any]]] = defaultdict(list)
        for linha in linhas:
            if linha.id_externo and not linha.id_externo.startswith("bill:"):
                por_importacao[linha.importacao_id].append(linha)

        direcoes: dict[int, Literal["entrada", "saida"]] = {}
        for importacao_id, do_comprovante in por_importacao.items():
            conteudo = self.session.scalar(
                select(Importacao.arquivo_conteudo).where(Importacao.id == importacao_id)
            )
            comprovante = ler_comprovante(conteudo)
            for linha in do_comprovante:
                transacao = comprovante.transacoes.get(linha.id_externo)
                tipo = transacao.type if transacao is not None else None
                if tipo == "CREDIT":
                    direcoes[linha.id] = "entrada"
                elif tipo == "DEBIT":
                    direcoes[linha.id] = "saida"
        return direcoes

    def _cartoes_por_conta(self) -> dict[int, list[str]]:
        cartoes: dict[int, list[str]] = defaultdict(list)
        for forma in self.session.scalars(
            select(FormaPagamento)
            .where(
                FormaPagamento.tipo == TipoPagamento.CREDITO,
                FormaPagamento.conta_id.is_not(None),
                FormaPagamento.ativo.is_(True),
                FormaPagamento.deleted_em.is_(None),
            )
            .order_by(FormaPagamento.apelido)
        ):
            if forma.conta_id is not None:
                cartoes[forma.conta_id].append(forma.apelido)
        return dict(cartoes)

    def _erro_nas_contas(self, origem: int | None, destino: int | None) -> str | None:
        if origem is None or destino is None:
            return "Escolha de onde saiu e para onde foi o dinheiro."
        if origem == destino:
            return "De onde saiu e para onde foi são a mesma conta."
        for conta_id in (origem, destino):
            conta = self.session.get(Conta, conta_id)
            if conta is None or conta.deleted_em is not None:
                return f"Conta {conta_id} não existe."
        return None

    def _item_modelo(self, item_id: int) -> ImportacaoItem:
        item = self.session.get(ImportacaoItem, item_id)
        if item is None or item.deleted_em is not None:
            raise NaoEncontrado("item de importação", item_id)
        return item

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflito(_mensagem_integridade(exc)) from exc


def _item(linha: Row[Any]) -> ItemRevisar:
    return ItemRevisar.model_validate(
        {**linha._mapping, "descricao": descricao_curta(linha.linha_bruta)}
    )


def _conta(item: ItemRevisar) -> ContaResumo | None:
    if item.conta_id is None or item.conta_nome is None:
        return None
    return ContaResumo(id=item.conta_id, nome=item.conta_nome)


def _tipo_transferencia(observacao: str | None) -> TipoTransferencia:
    nota = observacao or ""
    if OBS_PAGAMENTO_NO_CARTAO in nota:
        return "pagamento_fatura_cartao"
    if OBS_PAGAMENTO_NA_CONTA in nota:
        return "pagamento_fatura_conta"
    if OBS_MESMA_PESSOA in nota:
        return "mesma_pessoa"
    return "outra"


def _parear(
    itens: Sequence[ItemRevisar],
    direcoes: dict[int, Literal["entrada", "saida"]],
    tipos: dict[int, TipoTransferencia],
) -> dict[int, int]:
    """As duas pontas do mesmo dinheiro, nos dois sentidos do dicionário.

    Mesmo valor, sentido oposto, até `DIAS_ENTRE_PONTAS` de distância e
    contas diferentes — exceto os dois lados de um pagamento de fatura, que
    ficam na mesma conta quando ela paga o próprio cartão. Mais perto na data
    casa primeiro; cada item casa uma vez.
    """
    lados_da_fatura = {"pagamento_fatura_cartao", "pagamento_fatura_conta"}
    candidatos: list[tuple[int, int, int]] = []
    for a in itens:
        for b in itens:
            if a.id >= b.id or a.data is None or b.data is None:
                continue
            if a.conta_id is None or b.conta_id is None:
                continue
            fatura = {tipos[a.id], tipos[b.id]} == lados_da_fatura
            if a.conta_id == b.conta_id and not fatura:
                continue
            sentido_a, sentido_b = direcoes.get(a.id), direcoes.get(b.id)
            if sentido_a is None or sentido_b is None or sentido_a == sentido_b:
                continue
            distancia = abs((a.data - b.data).days)
            if a.valor == b.valor and distancia <= DIAS_ENTRE_PONTAS:
                candidatos.append((distancia, a.id, b.id))

    pares: dict[int, int] = {}
    for _, a_id, b_id in sorted(candidatos):
        if a_id not in pares and b_id not in pares:
            pares[a_id], pares[b_id] = b_id, a_id
    return pares


def _sem_notas(observacao: str | None, notas: Iterable[str | re.Pattern[str]]) -> str | None:
    texto = observacao or ""
    for nota in notas:
        texto = nota.sub("", texto) if isinstance(nota, re.Pattern) else texto.replace(nota, "")
    texto = re.sub(r"\s{2,}", " ", texto).strip()
    return texto or None


def _limpo(item: ImportacaoItem) -> bool:
    """Sem motivo para seguir na revisão, depois da decisão sobre a duplicata."""
    return (
        item.tipo_sugerido is not TipoTransacao.TRANSFERENCIA
        and not (item.id_externo or "").startswith("bill:")
        and not item.observacao
        and item.categoria_sugerida_id is not None
    )
