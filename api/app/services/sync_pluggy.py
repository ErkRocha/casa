"""Sincronização da Pluggy para o staging (fase 5b, passo 6; D-16).

Para cada mapeamento ativo: lê transações e faturas na Pluggy, converte pelo
passo 5 e grava em `importacao_itens` pelo mesmo `IngestaoService` do PDF.
**Nunca escreve em `transacoes`** (regra 5): a sync só enche a revisão.

Duas fases, de propósito:

1. **Planejar** — só leitura, na Pluggy e no banco. Monta, por conta, os
   itens novos, já com as marcas de duplicata e os encargos. Um erro aqui
   fica na conta que falhou; as outras seguem.
2. **Gravar** — uma importação por execução, com todos os itens das contas
   que planejaram sem erro, numa transação só. A simulação (`simular=True`)
   para depois da fase 1 e não grava nada, nem `ultimo_sync_em`.

O comprovante da importação é o JSON bruto das respostas da Pluggy, guardado
como `application/json`, como o PDF é guardado.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from app.conversao_pluggy import (
    FUSO,
    converter_lote,
    e_pagamento_de_fatura,
)
from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido
from app.models import Categoria, ContaPluggy, ImportacaoItem
from app.pluggy.modelos import Conta, Fatura, Transacao
from app.services.cadastros import normalizar_nome, primeiro_dia_do_mes
from app.services.ingestao import IngestaoService, ItemLote, _ContextoEnriquecimento

#: Quanto a janela volta antes do último sync. A Pluggy atualiza a cada 24h e
#: pode consolidar uma transação dias depois da data dela.
SOBREPOSICAO = timedelta(days=7)
CENTAVO = Decimal("0.01")
CONFIANCA_DUPLICATA = Decimal("0.50")
CONFIANCA_ENCARGOS = Decimal("0.70")
AUTOR = "sync_pluggy"

#: Nomes de categoria aceitos para os encargos, comparados sem acento e em
#: maiúsculas. Só nome exato: na dúvida, o item vai sem categoria.
CATEGORIAS_ENCARGOS = ("JUROS E ENCARGOS", "ENCARGOS", "JUROS", "TARIFAS E ENCARGOS")


class LeitorPluggy(Protocol):
    """O pedaço do `PluggyCliente` que a sync usa. Os testes passam um falso."""

    def listar_contas(self, item_id: str, tipo: str | None = None) -> list[Conta]: ...

    def listar_transacoes(self, account_id: str, desde: date, ate: date) -> list[Transacao]: ...

    def listar_faturas(self, account_id: str) -> list[Fatura]: ...


@dataclass(slots=True)
class Encargo:
    bill_id: str
    competencia: date
    valor: Decimal


@dataclass(slots=True)
class ResultadoConta:
    """O que a sync fez (ou faria) com uma conta mapeada."""

    mapeamento_id: int
    rotulo: str
    janela_inicio: date | None = None
    janela_fim: date | None = None
    novos: int = 0
    ja_existentes: int = 0
    pendentes_ignoradas: int = 0
    fora_da_janela: int = 0
    possiveis_duplicatas: int = 0
    encargos: list[Encargo] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erro: str | None = None
    #: Itens novos, para a gravação e para a amostra da simulação.
    itens: list[ItemLote] = field(default_factory=list)
    #: Transações `POSTED` de cartão cuja competência saiu de fatura achada,
    #: e as que caíram no fallback (id da transação).
    com_fatura: int = 0
    fallback_competencia: list[str] = field(default_factory=list)
    #: Só na simulação: cada item novo com a sugestão que receberia.
    amostra: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ResultadoSync:
    simulado: bool
    contas: list[ResultadoConta] = field(default_factory=list)
    importacao_id: int | None = None

    @property
    def itens_novos(self) -> int:
        return sum(c.novos for c in self.contas if c.erro is None)


class SyncPluggyService:
    def __init__(
        self,
        session: Session,
        leitor: LeitorPluggy,
        *,
        hoje: date,
        respostas_brutas: Callable[[], Sequence[Any]] | None = None,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.leitor = leitor
        self.hoje = hoje
        self._respostas_brutas = respostas_brutas or (lambda: [])
        self._agora = agora or (lambda: datetime.now(UTC))
        self._contas_por_item: dict[str, list[Conta]] = {}

    # -- entrada ----------------------------------------------------------

    def sincronizar(self, *, simular: bool = False) -> ResultadoSync:
        resultado = ResultadoSync(simulado=simular)
        mapeamentos = list(
            self.session.scalars(
                select(ContaPluggy)
                .where(ContaPluggy.deleted_em.is_(None), ContaPluggy.ativo.is_(True))
                .order_by(ContaPluggy.id)
            )
        )
        contexto = _ContextoEnriquecimento.carregar(self.session)
        categoria_encargos = self._categoria_encargos()

        for mapa in mapeamentos:
            conta = ResultadoConta(mapeamento_id=mapa.id, rotulo=_rotulo(mapa))
            try:
                self._planejar(mapa, conta, categoria_encargos)
            except Exception as exc:  # erro de uma conta não derruba as outras
                conta.erro = f"{type(exc).__name__}: {exc}"
                conta.itens = []
            resultado.contas.append(conta)

        _marcar_duplicatas_no_lote(resultado.contas)
        if simular:
            # A amostra mostra a sugestão que o item teria no staging, pelo
            # mesmo código da gravação, sem gravar.
            ingestao = IngestaoService(self.session)
            for conta in resultado.contas:
                for lote in conta.itens:
                    sugestao = ingestao.sugerir(
                        lote.extraido,
                        contexto,
                        forma_fixa_id=lote.forma_pagamento_id,
                        pessoa_padrao_id=lote.pessoa_padrao_id,
                        categoria_fixa_id=lote.categoria_id,
                    )
                    i = lote.extraido
                    conta.amostra.append(
                        {
                            "data": i.data,
                            "valor": i.valor,
                            "tipo": i.tipo.value,
                            "competencia": i.competencia,
                            "forma_pagamento_id": sugestao.forma_pagamento_id,
                            "pessoa_id": sugestao.pessoa_id,
                            "categoria_id": sugestao.categoria_id,
                            "confianca_conversao": i.confianca,
                            "confianca_staging": min(i.confianca, sugestao.confianca),
                            "id_externo": i.id_externo,
                            "observacao": i.observacao,
                        }
                    )
            return resultado

        self._gravar(resultado, mapeamentos)
        return resultado

    # -- fase 1: planejar ------------------------------------------------

    def _planejar(
        self, mapa: ContaPluggy, resultado: ResultadoConta, categoria_encargos: int | None
    ) -> None:
        conta = self._conta_remota(mapa)
        inicio = mapa.sincronizar_desde
        if mapa.ultimo_sync_em is not None:
            inicio = max(inicio, mapa.ultimo_sync_em.astimezone(FUSO).date() - SOBREPOSICAO)
        resultado.janela_inicio, resultado.janela_fim = inicio, self.hoje

        # Cartão lê desde o corte, e não só a janela: os encargos comparam a
        # fatura inteira com as compras dela. Um dia a mais para trás porque
        # o filtro da Pluggy é em UTC e o corte é pela data de São Paulo.
        desde_api = (mapa.sincronizar_desde if conta.e_cartao else inicio) - timedelta(days=1)
        transacoes = self.leitor.listar_transacoes(conta.id, desde_api, self.hoje)
        faturas = self.leitor.listar_faturas(conta.id) if conta.e_cartao else []

        forma = mapa.forma_pagamento
        lote = converter_lote(
            transacoes,
            conta,
            faturas,
            dia_fechamento=forma.dia_fechamento,
            dia_vencimento=forma.dia_vencimento,
        )
        resultado.pendentes_ignoradas = lote.pendentes_ignoradas
        resultado.avisos.extend(lote.avisos)

        ids_faturas = {f.id for f in faturas}
        fatura_da = {
            t.id: (t.credit_card_metadata.bill_id if t.credit_card_metadata else None)
            for t in transacoes
        }
        candidatos: list[ItemExtraido] = []
        for item in lote.itens:
            if item.data < inicio:
                resultado.fora_da_janela += 1
                continue
            candidatos.append(item)
            if conta.e_cartao and item.tipo is TipoTransacao.DESPESA:
                if fatura_da.get(item.id_externo or "") in ids_faturas:
                    resultado.com_fatura += 1
                else:
                    resultado.fallback_competencia.append(item.id_externo or "?")

        if conta.e_cartao:
            for encargo_item, encargo in self._encargos(mapa, transacoes, faturas, resultado):
                candidatos.append(encargo_item)
                resultado.encargos.append(encargo)

        existentes = self._ids_existentes([c.id_externo for c in candidatos if c.id_externo])
        novos = [c for c in candidatos if c.id_externo not in existentes]
        resultado.ja_existentes = len(candidatos) - len(novos)
        resultado.encargos = [
            e for e in resultado.encargos if f"bill:{e.bill_id}:encargos" not in existentes
        ]

        self._marcar_duplicatas_no_staging(mapa, novos)

        pessoa = mapa.conta.titular_id
        resultado.itens = [
            ItemLote(
                extraido=item,
                forma_pagamento_id=mapa.forma_pagamento_id,
                pessoa_padrao_id=pessoa,
                categoria_id=(
                    categoria_encargos
                    if item.id_externo and item.id_externo.startswith("bill:")
                    else None
                ),
            )
            for item in novos
        ]
        resultado.novos = len(resultado.itens)

    def _conta_remota(self, mapa: ContaPluggy) -> Conta:
        if mapa.pluggy_item_id not in self._contas_por_item:
            self._contas_por_item[mapa.pluggy_item_id] = self.leitor.listar_contas(
                mapa.pluggy_item_id
            )
        for conta in self._contas_por_item[mapa.pluggy_item_id]:
            if conta.id == mapa.pluggy_account_id:
                return conta
        raise LookupError(
            f"A conta {mapa.pluggy_account_id} não aparece mais na conexão "
            f"{mapa.pluggy_item_id} da Pluggy."
        )

    def _ids_existentes(self, ids: Sequence[str]) -> set[str]:
        """Ids já no staging, em qualquer status, entre linhas vivas (D-16)."""
        if not ids:
            return set()
        return set(
            self.session.scalars(
                select(ImportacaoItem.id_externo).where(
                    ImportacaoItem.id_externo.in_(ids), ImportacaoItem.deleted_em.is_(None)
                )
            )
        )

    def _encargos(
        self,
        mapa: ContaPluggy,
        transacoes: Sequence[Transacao],
        faturas: Sequence[Fatura],
        resultado: ResultadoConta,
    ) -> list[tuple[ItemExtraido, Encargo]]:
        """Diferença entre o total da fatura e as compras dela.

        Só fatura fechada e inteira dentro do corte: uma fatura que começou
        antes de `sincronizar_desde` tem compras que a Pluggy não entregou, e
        a diferença seria compra faltando, não encargo. Pagamento fica fora
        da soma pelo mesmo critério da conversão. Diferença abaixo de um
        centavo (os totais vêm com 4 casas) é arredondamento.
        """
        por_fatura: dict[str, list[Transacao]] = defaultdict(list)
        for t in transacoes:
            meta = t.credit_card_metadata
            if t.status == "POSTED" and meta and meta.bill_id and not e_pagamento_de_fatura(t):
                por_fatura[meta.bill_id].append(t)

        encargos: list[tuple[ItemExtraido, Encargo]] = []
        for fatura in faturas:
            fechamento = _dia_civil(fatura.bill_closing_date) if fatura.bill_closing_date else None
            if fechamento is None or fechamento >= self.hoje:
                continue  # aberta, ou sem data para saber
            if fechamento < mapa.sincronizar_desde:
                continue
            compras = por_fatura.get(fatura.id, [])
            if not compras:
                continue
            if any(_data_sp(t.date) < mapa.sincronizar_desde for t in compras):
                continue  # fatura dividida pelo corte

            soma = sum((Decimal(t.amount) for t in compras), Decimal("0"))
            diferenca = Decimal(fatura.total_amount) - soma
            competencia = primeiro_dia_do_mes(_dia_civil(fatura.due_date))
            mes = f"{competencia:%m/%Y}"
            if diferenca <= -CENTAVO:
                resultado.avisos.append(
                    f"Fatura {mes}: as compras ({soma}) passam do total da fatura "
                    f"({fatura.total_amount}). Nenhum encargo gerado."
                )
                continue
            if diferenca < CENTAVO:
                continue

            valor = diferenca.quantize(CENTAVO)
            encargo = Encargo(bill_id=fatura.id, competencia=competencia, valor=valor)
            item = ItemExtraido(
                linha_bruta=f"Encargos da fatura {mes}",
                linha_num=0,
                data=fechamento,
                valor=valor,
                descricao=f"Encargos da fatura {mes}",
                tipo=TipoTransacao.DESPESA,
                confianca=CONFIANCA_ENCARGOS,
                observacao=(
                    f"Deduzido: total da fatura {mes} ({fatura.total_amount}) menos a soma "
                    f"das compras dela na Pluggy ({soma}). A Pluggy não entrega juros, "
                    "multa e IOF de atraso como transação. Confira na fatura do banco."
                ),
                id_externo=f"bill:{fatura.id}:encargos",
                competencia=competencia,
            )
            encargos.append((item, encargo))
        return encargos

    def _marcar_duplicatas_no_staging(
        self, mapa: ContaPluggy, novos: Sequence[ItemExtraido]
    ) -> None:
        """Mesma data, valor e descrição de um item já no staging desta conta.

        A conta chega pelo `forma_pagamento_sugerida_id`: na sync, a forma
        vem sempre do mapeamento, e cada mapeamento tem a sua.
        """
        chaves = {(i.data, i.valor, i.linha_bruta) for i in novos}
        if not chaves:
            return
        gemeos: dict[tuple[date, Decimal, str], list[str]] = defaultdict(list)
        linhas = self.session.execute(
            select(
                ImportacaoItem.data,
                ImportacaoItem.valor,
                ImportacaoItem.descricao_original,
                ImportacaoItem.id_externo,
            ).where(
                ImportacaoItem.deleted_em.is_(None),
                ImportacaoItem.id_externo.is_not(None),
                ImportacaoItem.forma_pagamento_sugerida_id == mapa.forma_pagamento_id,
                tuple_(
                    ImportacaoItem.data, ImportacaoItem.valor, ImportacaoItem.descricao_original
                ).in_(list(chaves)),
            )
        )
        for data, valor, descricao, id_externo in linhas:
            gemeos[(data, valor, descricao or "")].append(id_externo)

        for item in novos:
            outros = [
                i
                for i in gemeos.get((item.data, item.valor, item.linha_bruta), [])
                if i != item.id_externo
            ]
            if outros:
                _marcar(item, outros, "já está no staging")

    # -- fase 2: gravar --------------------------------------------------

    def _gravar(self, resultado: ResultadoSync, mapeamentos: Sequence[ContaPluggy]) -> None:
        self.session.execute(text("SELECT set_config('app.autor', :autor, true)"), {"autor": AUTOR})
        sem_erro = {c.mapeamento_id for c in resultado.contas if c.erro is None}
        itens = [lote for c in resultado.contas if c.erro is None for lote in c.itens]

        if itens:
            agora = self._agora()
            importacao = IngestaoService(self.session).importar_lote(
                arquivo_nome=f"pluggy_{agora.astimezone(FUSO):%Y%m%dT%H%M%S}.json",
                conteudo=self._comprovante(resultado, agora),
                arquivo_tipo="application/json",
                origem="pluggy",
                parser_usado="pluggy_sync",
                itens=itens,
                aviso=_resumo_avisos(resultado.contas),
            )
            resultado.importacao_id = importacao.id

        agora = self._agora()
        for mapa in mapeamentos:
            if mapa.id in sem_erro:
                mapa.ultimo_sync_em = agora
        self.session.flush()

    def _comprovante(self, resultado: ResultadoSync, agora: datetime) -> bytes:
        """O JSON bruto recebido, como a Pluggy mandou, mais o resumo."""
        respostas = []
        for r in self._respostas_brutas():
            try:
                corpo: Any = json.loads(r.conteudo)
            except (ValueError, AttributeError):
                corpo = None
            respostas.append(
                {
                    "metodo": getattr(r, "metodo", None),
                    "caminho": getattr(r, "caminho", None),
                    "params": getattr(r, "params", None),
                    "status": getattr(r, "status", None),
                    "corpo": corpo,
                }
            )
        documento = {
            "gerado_em": agora.isoformat(),
            "contas": [
                {
                    "mapeamento_id": c.mapeamento_id,
                    "janela": [str(c.janela_inicio), str(c.janela_fim)],
                    "novos": c.novos,
                    "erro": c.erro,
                }
                for c in resultado.contas
            ],
            "respostas": respostas,
        }
        return json.dumps(documento, ensure_ascii=False, default=str, indent=1).encode("utf-8")

    def _categoria_encargos(self) -> int | None:
        for categoria in self.session.scalars(
            select(Categoria).where(Categoria.deleted_em.is_(None)).order_by(Categoria.id)
        ):
            if normalizar_nome(categoria.nome) in CATEGORIAS_ENCARGOS:
                return categoria.id
        return None


# --------------------------------------------------------------------------


def _marcar_duplicatas_no_lote(contas: Sequence[ResultadoConta]) -> None:
    """Mesma conta, data, valor e descrição, com ids diferentes, no lote."""
    for conta in contas:
        grupos: dict[tuple[date, Decimal, str], list[ItemExtraido]] = defaultdict(list)
        for lote in conta.itens:
            i = lote.extraido
            grupos[(i.data, i.valor, i.linha_bruta)].append(i)
        for grupo in grupos.values():
            ids = {i.id_externo for i in grupo}
            if len(ids) < 2:
                continue
            for item in grupo:
                _marcar(item, sorted(x for x in ids if x and x != item.id_externo), "no mesmo lote")
        conta.possiveis_duplicatas = sum(
            1
            for lote in conta.itens
            if lote.extraido.observacao and "Possível duplicata" in lote.extraido.observacao
        )


def _marcar(item: ItemExtraido, outros: Sequence[str], onde: str) -> None:
    nota = (
        f"Possível duplicata da Pluggy ({onde}): mesma data, valor e descrição de "
        f"{', '.join(outros)}. Confira no app do banco antes de aprovar os dois."
    )
    if item.observacao and nota in item.observacao:
        return
    item.observacao = f"{item.observacao} {nota}" if item.observacao else nota
    item.confianca = min(item.confianca, CONFIANCA_DUPLICATA)


def _resumo_avisos(contas: Sequence[ResultadoConta]) -> str | None:
    avisos = [f"{c.rotulo}: {a}" for c in contas for a in c.avisos]
    return " ".join(avisos) or None


def _rotulo(mapa: ContaPluggy) -> str:
    return f"{mapa.conta.nome} / {mapa.forma_pagamento.apelido}"


def _data_sp(momento: datetime) -> date:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(FUSO).date()


def _dia_civil(momento: datetime) -> date:
    if momento.tzinfo is None:
        return momento.date()
    return momento.astimezone(UTC).date()
