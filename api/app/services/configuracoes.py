"""As telas de configuração (D-22): contas e cartões, uso das categorias e
categorias que a Pluggy envia. Só leitura; as edições usam os CRUDs que já
existem (`/contas`, `/formas-pagamento`, `/categorias`, `/regras`,
`/categorias-pluggy`).

**Contas por banco.** Um banco é uma conexão da Pluggy (`pluggy_item_id`).
O cartão aparece dentro da conta que paga a fatura: é forma `credito` dela
(Fase 5b). A situação vem de `contas_pluggy` e do último movimento; conta
sem mapeamento é manual.

**Cartões virtuais** não têm forma própria (caem na forma do cartão, Fase
5b). Os finais vêm do `cardNumber` das compras nos comprovantes recentes da
sync, que guardam a transação da Pluggy inteira.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.enums import TipoPagamento
from app.models import Conta, ContaPluggy, FormaPagamento, Importacao
from app.schemas.configuracoes import (
    CategoriaPluggyUso,
    ContasECartoes,
    GrupoContas,
    ItemContaCartao,
    SituacaoConta,
    UsoCategoria,
    UsoCategorias,
)
from app.services.cadastros import primeiro_dia_do_mes
from app.services.categorias_pluggy import e_transferencia_pluggy
from app.services.comprovante_pluggy import ler_comprovante

#: Sem movimento há mais que isto, a conta aparece como "sem movimento".
DIAS_SEM_MOVIMENTO = 365
#: Quantos comprovantes recentes da sync entram na busca de cartão virtual.
COMPROVANTES_RECENTES = 5
TITULO_MANUAIS = "Sem conexão com o banco"
#: As transações consolidadas dentro do comprovante da sync (lax: resposta
#: fora do formato só não casa).
CAMINHO_TRANSACOES = (
    '$.respostas[*] ? (@.caminho == "/v2/transactions").corpo.results[*] ? (@.status == "POSTED")'
)

_FINAL = re.compile(r"(\d{4})\s*$")

#: Último dia com lançamento por forma de pagamento.
_ULTIMO_POR_FORMA = """
    SELECT forma_pagamento_id, max(data) AS ultimo
    FROM transacoes
    WHERE deleted_em IS NULL AND forma_pagamento_id IS NOT NULL
    GROUP BY forma_pagamento_id
"""

#: Despesas e receitas do mês por categoria; a raiz soma as filhas.
_USO_CATEGORIAS = """
    WITH base AS (
      SELECT categoria_id, categoria_raiz_id
      FROM vw_transacoes_completa
      WHERE competencia = CAST(:c AS date) AND tipo <> 'transferencia'
    ),
    contagem AS (
      SELECT categoria_id AS id, count(*) AS n FROM base
      WHERE categoria_id IS NOT NULL GROUP BY categoria_id
      UNION ALL
      SELECT categoria_raiz_id, count(*) FROM base
      WHERE categoria_id IS NOT NULL AND categoria_raiz_id <> categoria_id
      GROUP BY categoria_raiz_id
    )
    SELECT id AS categoria_id, sum(n)::int AS lancamentos
    FROM contagem GROUP BY id
"""

_SEM_CATEGORIA = """
    SELECT count(*)::int FROM vw_transacoes_completa
    WHERE competencia = CAST(:c AS date) AND tipo <> 'transferencia' AND categoria_id IS NULL
"""

#: As categorias das transações consolidadas nos comprovantes da sync,
#: contadas no banco a partir do JSON guardado (uma vez por transação, mesmo
#: que ela apareça em mais de um comprovante), junto do mapeamento vivo.
_CATEGORIAS_PLUGGY = """
    WITH docs AS (
      SELECT convert_from(i.arquivo_conteudo, 'UTF8')::jsonb AS doc
      FROM importacoes i
      WHERE i.origem = 'pluggy' AND i.deleted_em IS NULL
        AND i.arquivo_tipo = 'application/json' AND i.arquivo_conteudo IS NOT NULL
    ),
    vistas AS (
      SELECT DISTINCT ON (t ->> 'id')
        t ->> 'categoryId' AS pluggy_id,
        t ->> 'category' AS nome
      FROM docs,
        jsonb_path_query(doc, CAST(:caminho AS jsonpath)) AS t
    ),
    contagem AS (
      SELECT pluggy_id, max(nome) AS nome, count(*)::int AS transacoes
      FROM vistas WHERE pluggy_id IS NOT NULL
      GROUP BY pluggy_id
    ),
    mapas AS (
      SELECT cp.id, cp.pluggy_categoria_id, cp.pluggy_categoria_nome, cp.categoria_id, cp.ativo,
             c.nome AS categoria_nome
      FROM categorias_pluggy cp
      LEFT JOIN categorias c ON c.id = cp.categoria_id
      WHERE cp.deleted_em IS NULL
    )
    SELECT
      coalesce(ct.pluggy_id, m.pluggy_categoria_id) AS pluggy_categoria_id,
      coalesce(m.pluggy_categoria_nome, ct.nome, '') AS pluggy_categoria_nome,
      coalesce(ct.transacoes, 0) AS transacoes,
      m.id AS mapeamento_id,
      m.categoria_id,
      m.categoria_nome,
      m.ativo
    FROM contagem ct
    FULL OUTER JOIN mapas m ON m.pluggy_categoria_id = ct.pluggy_id
    ORDER BY coalesce(ct.transacoes, 0) DESC, 2
"""


class ConfiguracoesService:
    def __init__(self, session: Session, hoje: date | None = None) -> None:
        self.session = session
        self.hoje = hoje or date.today()

    # -- contas e cartões --------------------------------------------------

    def contas(self) -> ContasECartoes:
        contas = {
            c.id: c
            for c in self.session.scalars(
                select(Conta).where(Conta.deleted_em.is_(None)).order_by(Conta.nome)
            )
        }
        formas = {
            f.id: f
            for f in self.session.scalars(
                select(FormaPagamento)
                .where(FormaPagamento.deleted_em.is_(None))
                .order_by(FormaPagamento.apelido)
            )
        }
        ultimo = {
            linha.forma_pagamento_id: linha.ultimo
            for linha in self.session.execute(text(_ULTIMO_POR_FORMA))
        }
        mapas = self._mapeamentos(contas, formas)
        virtuais = self._cartoes_virtuais(
            [m for m in mapas if formas[m.forma_pagamento_id].tipo is TipoPagamento.CREDITO],
            formas,
        )

        formas_da_conta: dict[int, list[FormaPagamento]] = defaultdict(list)
        for forma in formas.values():
            if forma.conta_id is not None:
                formas_da_conta[forma.conta_id].append(forma)

        # O banco de cada conta: o do mapeamento dela; sem ele, o do cartão
        # que ela paga. O cartão vai para o banco da conta que paga a fatura.
        contas_com_banco: dict[int, ContaPluggy] = {}
        for m in mapas:
            if formas[m.forma_pagamento_id].tipo is not TipoPagamento.CREDITO:
                contas_com_banco.setdefault(m.conta_id, m)
        grupo_da_conta: dict[int, str] = {m.conta_id: m.pluggy_item_id for m in mapas}
        grupo_da_conta.update({cid: m.pluggy_item_id for cid, m in contas_com_banco.items()})

        grupos: dict[str, list[ItemContaCartao]] = defaultdict(list)
        desde: dict[str, list[date]] = defaultdict(list)
        for m in mapas:
            grupo = grupo_da_conta[m.conta_id]
            if m.deleted_em is None and m.ativo:
                desde[grupo].append(m.sincronizar_desde)
            forma = formas[m.forma_pagamento_id]
            if forma.tipo is TipoPagamento.CREDITO:
                grupos[grupo].append(
                    self._item_cartao(m, forma, contas[m.conta_id], ultimo, virtuais)
                )

        manuais: list[ItemContaCartao] = []
        for conta in contas.values():
            item = self._item_conta(
                conta, formas_da_conta[conta.id], contas_com_banco.get(conta.id), ultimo
            )
            if conta.id in grupo_da_conta:
                grupos[grupo_da_conta[conta.id]].append(item)
            else:
                manuais.append(item)

        resultado = [
            GrupoContas(
                titulo=_titulo([i.nome for i in itens if i.tipo == "conta"] or [itens[0].nome]),
                pluggy_item_id=item_id,
                desde=min(desde[item_id]) if desde[item_id] else None,
                situacao=_situacao_do_grupo(itens),
                itens=sorted(itens, key=lambda i: (i.tipo != "conta", i.nome)),
            )
            for item_id, itens in grupos.items()
        ]
        resultado.sort(key=lambda g: g.titulo)
        if manuais:
            resultado.append(
                GrupoContas(
                    titulo=TITULO_MANUAIS,
                    pluggy_item_id=None,
                    desde=None,
                    situacao="manual",
                    itens=manuais,
                )
            )
        return ContasECartoes(grupos=resultado)

    def _mapeamentos(
        self, contas: dict[int, Conta], formas: dict[int, FormaPagamento]
    ) -> list[ContaPluggy]:
        """Um mapeamento por conta da Pluggy: o vivo, ou o último desativado."""
        por_conta: dict[str, ContaPluggy] = {}
        for m in self.session.scalars(select(ContaPluggy).order_by(ContaPluggy.id)):
            if m.conta_id not in contas or m.forma_pagamento_id not in formas:
                continue
            atual = por_conta.get(m.pluggy_account_id)
            if atual is None or atual.deleted_em is not None or m.deleted_em is None:
                por_conta[m.pluggy_account_id] = m
        return list(por_conta.values())

    def _item_cartao(
        self,
        m: ContaPluggy,
        forma: FormaPagamento,
        conta: Conta,
        ultimo: dict[int, date],
        virtuais: dict[str, list[str]],
    ) -> ItemContaCartao:
        movimento = ultimo.get(forma.id)
        return ItemContaCartao(
            tipo="cartao",
            conta_id=conta.id,
            forma_pagamento_id=forma.id,
            nome=forma.apelido,
            tipo_conta=None,
            titular=forma.titular.nome if forma.titular else None,
            situacao=self._situacao(m, movimento),
            formas=[],
            cartoes=[],
            paga_por=conta.nome,
            cartoes_virtuais=virtuais.get(m.pluggy_account_id, []),
            ultimo_movimento=movimento,
        )

    def _item_conta(
        self,
        conta: Conta,
        formas: list[FormaPagamento],
        m: ContaPluggy | None,
        ultimo: dict[int, date],
    ) -> ItemContaCartao:
        de_conta = [f for f in formas if f.tipo is not TipoPagamento.CREDITO]
        datas = [ultimo[f.id] for f in de_conta if f.id in ultimo]
        movimento = max(datas) if datas else None
        tipos = sorted({f.tipo for f in de_conta}, key=lambda t: list(TipoPagamento).index(t))
        return ItemContaCartao(
            tipo="conta",
            conta_id=conta.id,
            forma_pagamento_id=None,
            nome=conta.nome,
            tipo_conta=conta.tipo,
            titular=conta.titular.nome if conta.titular else None,
            situacao=self._situacao(m, movimento) if m is not None else "manual",
            formas=tipos,
            cartoes=[f.apelido for f in formas if f.tipo is TipoPagamento.CREDITO],
            paga_por=None,
            cartoes_virtuais=[],
            ultimo_movimento=movimento,
        )

    def _situacao(self, m: ContaPluggy, movimento: date | None) -> SituacaoConta:
        if m.deleted_em is not None or not m.ativo:
            return "pausado"
        if movimento is None or movimento < self.hoje - timedelta(days=DIAS_SEM_MOVIMENTO):
            return "sem_movimento"
        return "sincronizando"

    def _cartoes_virtuais(
        self, cartoes: list[ContaPluggy], formas: dict[int, FormaPagamento]
    ) -> dict[str, list[str]]:
        """Finais diferentes do principal nas compras recentes de cada cartão."""
        if not cartoes:
            return {}
        principal = {
            m.pluggy_account_id: _final(formas[m.forma_pagamento_id].apelido) for m in cartoes
        }
        vistos: dict[str, set[str]] = defaultdict(set)
        conteudos = self.session.scalars(
            select(Importacao.arquivo_conteudo)
            .where(
                Importacao.origem == "pluggy",
                Importacao.deleted_em.is_(None),
                Importacao.arquivo_tipo == "application/json",
            )
            .order_by(Importacao.id.desc())
            .limit(COMPROVANTES_RECENTES)
        )
        for conteudo in conteudos:
            for t in ler_comprovante(conteudo).transacoes.values():
                meta = t.credit_card_metadata
                if t.account_id not in principal or meta is None or not meta.card_number:
                    continue
                final = _final(re.sub(r"\D", "", meta.card_number))
                if final and final != principal[t.account_id]:
                    vistos[t.account_id].add(final)
        return {conta: sorted(finais) for conta, finais in vistos.items()}

    # -- categorias --------------------------------------------------------

    def uso_categorias(self, competencia: date | None = None) -> UsoCategorias:
        mes = primeiro_dia_do_mes(competencia or self.hoje)
        linhas = self.session.execute(text(_USO_CATEGORIAS), {"c": mes}).all()
        sem = self.session.scalar(text(_SEM_CATEGORIA), {"c": mes})
        return UsoCategorias(
            competencia=mes,
            sem_categoria=int(sem or 0),
            categorias=[
                UsoCategoria(categoria_id=linha.categoria_id, lancamentos=linha.lancamentos)
                for linha in linhas
            ],
        )

    def categorias_pluggy(self) -> list[CategoriaPluggyUso]:
        return [
            CategoriaPluggyUso(
                **dict(linha._mapping),
                transferencia=e_transferencia_pluggy(
                    linha.pluggy_categoria_id, linha.pluggy_categoria_nome
                ),
            )
            for linha in self.session.execute(
                text(_CATEGORIAS_PLUGGY), {"caminho": CAMINHO_TRANSACOES}
            )
        ]


def _final(texto: str) -> str | None:
    casou = _FINAL.search(texto)
    return casou.group(1) if casou else None


def _titulo(nomes: list[str]) -> str:
    """O nome do banco: as palavras que os nomes das contas têm em comum.

    "Sicredi Conta Corrente" e "Sicredi Poupança" dão "Sicredi"; uma conta
    só dá o próprio nome.
    """
    palavras = [n.split() for n in nomes]
    comuns: list[str] = []
    for grupo in zip(*palavras, strict=False):
        if len({p.lower() for p in grupo}) != 1:
            break
        comuns.append(grupo[0])
    return " ".join(comuns) or nomes[0]


def _situacao_do_grupo(itens: list[ItemContaCartao]) -> Any:
    situacoes = {i.situacao for i in itens}
    if situacoes <= {"pausado"}:
        return "pausada"
    if "pausado" in situacoes:
        return "parcial"
    return "funcionando"
