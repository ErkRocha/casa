"""Sessões de preparo: quando se cozinha antes (D-30).

A semana nasce com uma, no domingo anterior; o casal muda o dia ou acrescenta
outra. As refeições de uma sessão apagada passam para a anterior ou para "no
dia": o roteiro é calculado na leitura, então nada precisa ser movido.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.models import Semana, SessaoPreparo
from compras.services.base import Conflito, NaoEncontrado, RegraViolada


class SessaoService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    def get(self, id_: int) -> SessaoPreparo:
        sessao = self.session.scalar(
            select(SessaoPreparo)
            .where(SessaoPreparo.id == id_, SessaoPreparo.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        if sessao is None:
            raise NaoEncontrado("sessão de preparo", id_)
        return sessao

    def criar(self, semana: Semana, data: date, rotulo: str | None) -> SessaoPreparo:
        self._na_janela(semana, data)
        self._livre(semana.id, data, ignorar=None)
        sessao = SessaoPreparo(semana_id=semana.id, data=data, rotulo=rotulo)
        self.session.add(sessao)
        self.session.flush()
        return self.get(sessao.id)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> SessaoPreparo:
        sessao = self.get(id_)
        semana = self.session.get(Semana, sessao.semana_id)
        assert semana is not None
        if dados.get("data") is not None:
            self._na_janela(semana, dados["data"])
            self._livre(semana.id, dados["data"], ignorar=id_)
            sessao.data = dados["data"]
        if "rotulo" in dados:
            sessao.rotulo = dados["rotulo"]
        self.session.flush()
        return self.get(id_)

    def remover(self, id_: int) -> SessaoPreparo:
        sessao = self.get(id_)
        sessao.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(sessao)
        return sessao

    # -- apoio -----------------------------------------------------------

    @staticmethod
    def _na_janela(semana: Semana, data: date) -> None:
        """Do sábado anterior ao domingo da semana."""
        if not semana.inicio - timedelta(days=2) <= data <= semana.inicio + timedelta(days=6):
            raise RegraViolada(
                f"a sessão vai de {(semana.inicio - timedelta(days=2)).isoformat()} "
                f"a {(semana.inicio + timedelta(days=6)).isoformat()}"
            )

    def _livre(self, semana_id: int, data: date, ignorar: int | None) -> None:
        outra = self.session.scalar(
            select(SessaoPreparo.id).where(
                SessaoPreparo.semana_id == semana_id,
                SessaoPreparo.data == data,
                SessaoPreparo.deleted_em.is_(None),
            )
        )
        if outra is not None and outra != ignorar:
            raise Conflito(f"Já existe uma sessão de preparo em {data.isoformat()}.")
