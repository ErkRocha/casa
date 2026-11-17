"""O roteiro de preparo: calculado na leitura, não guardado (D-30).

Sai das refeições, das receitas e das sessões já gravadas; guardar uma cópia
só criaria o trabalho de mantê-la igual.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from compras.models import Receita, Refeicao, Semana, SessaoPreparo
from compras.normalizar import normalizar
from compras.schemas_cardapio import (
    AvisoRefeicao,
    DestinoPasso,
    NoDia,
    Passo,
    ReceitaNoRoteiro,
    Roteiro,
    SessaoNoRoteiro,
)
from compras.services.conversao import tres_casas
from compras.services.refeicoes import RefeicaoService

_DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_DUAS_CASAS = Decimal("0.01")


def _duas_casas(valor: Decimal) -> Decimal:
    return valor.quantize(_DUAS_CASAS, rounding=ROUND_HALF_UP)


def _dias_txt(n: int) -> str:
    return f"{n} dia" if n == 1 else f"{n} dias"


class RoteiroService:
    """Regras de `modelo-cardapio.md`, "Preparo", em ordem:

    1. entram as refeições com receita que pode antecipar; o resto vai para
       "no dia";
    2. a sessão de cada uma é a mais recente com `data <=` o dia dela (a do
       próprio dia vale); sem sessão até o dia, "no dia";
    3. um passo por receita em cada sessão, com a soma das porções;
    4. validade: até `dura_dias` na geladeira; passou e congela, congelador
       com "tirar" no dia anterior; passou e não congela, aviso (a refeição
       continua no passo: o casal decide);
    5. passos do que demora mais primeiro, empate pelo nome;
    6. cada passo diz quantas porções vão para cada destino, e para que dia.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def montar(self, semana: Semana) -> Roteiro:
        refeicoes_service = RefeicaoService(self.session)
        refeicoes = [r for r in refeicoes_service.da_semana(semana.id) if r.receita_id is not None]
        receitas = {
            r.id: r
            for r in self.session.scalars(
                select(Receita).where(Receita.id.in_({r.receita_id for r in refeicoes}))
            )
        }
        porcoes = refeicoes_service.porcoes([r.id for r in refeicoes])
        sessoes = list(
            self.session.scalars(
                select(SessaoPreparo)
                .where(SessaoPreparo.semana_id == semana.id, SessaoPreparo.deleted_em.is_(None))
                .order_by(SessaoPreparo.data, SessaoPreparo.id)
            )
        )

        no_dia: list[NoDia] = []
        grupos: dict[tuple[int, int], list[Refeicao]] = {}
        for refeicao in refeicoes:
            assert refeicao.receita_id is not None
            receita = receitas[refeicao.receita_id]
            sessao = self._sessao_de(sessoes, refeicao.dia) if receita.pode_antecipar else None
            if sessao is None:
                no_dia.append(
                    NoDia(
                        refeicao_id=refeicao.id,
                        dia=refeicao.dia,
                        tipo=refeicao.tipo,
                        receita=self._resumo(receita),
                    )
                )
            else:
                grupos.setdefault((sessao.id, receita.id), []).append(refeicao)

        avisos: list[AvisoRefeicao] = []
        passos_da_sessao: dict[int, list[Passo]] = {s.id: [] for s in sessoes}
        datas = {s.id: s.data for s in sessoes}
        for (sessao_id, receita_id), deste_grupo in grupos.items():
            passo, avisos_do_passo = self._passo(
                receitas[receita_id], datas[sessao_id], deste_grupo, porcoes
            )
            passos_da_sessao[sessao_id].append(passo)
            avisos.extend(avisos_do_passo)

        saida = []
        for sessao in sessoes:
            passos = sorted(
                passos_da_sessao[sessao.id],
                key=lambda p: (-(p.receita.tempo_preparo_min or 0), normalizar(p.receita.nome)),
            )
            saida.append(SessaoNoRoteiro(data=sessao.data, rotulo=sessao.rotulo, passos=passos))
        return Roteiro(sessoes=saida, no_dia=no_dia, avisos=avisos)

    # -- apoio -----------------------------------------------------------

    @staticmethod
    def _sessao_de(sessoes: list[SessaoPreparo], dia: date) -> SessaoPreparo | None:
        """A mais recente com data até o dia. `sessoes` já vem em ordem de data."""
        achada = None
        for sessao in sessoes:
            if sessao.data <= dia:
                achada = sessao
        return achada

    @staticmethod
    def _resumo(receita: Receita) -> ReceitaNoRoteiro:
        return ReceitaNoRoteiro(
            id=receita.id, nome=receita.nome, tempo_preparo_min=receita.tempo_preparo_min
        )

    def _passo(
        self,
        receita: Receita,
        data_da_sessao: date,
        refeicoes: list[Refeicao],
        porcoes: dict[int, Decimal],
    ) -> tuple[Passo, list[AvisoRefeicao]]:
        dura = receita.dura_dias or 0
        destinos: list[DestinoPasso] = []
        avisos: list[AvisoRefeicao] = []
        na_geladeira = Decimal(0)
        no_congelador = Decimal(0)
        for refeicao in sorted(refeicoes, key=lambda r: (r.dia, r.tipo, r.id)):
            quantas = porcoes[refeicao.id]
            dias = (refeicao.dia - data_da_sessao).days
            descongelar_em = None
            onde: Literal["geladeira", "congelador"] = "geladeira"
            if dias > dura:
                if receita.pode_congelar:
                    onde = "congelador"
                    descongelar_em = refeicao.dia - timedelta(days=1)
                else:
                    dia_txt = _DIAS_DA_SEMANA[refeicao.dia.weekday()]
                    avisos.append(
                        AvisoRefeicao(
                            refeicao_id=refeicao.id,
                            texto=(
                                f"{receita.nome} não dura até {dia_txt} "
                                f"(dura {_dias_txt(dura)}) e não congela; faça uma sessão "
                                "mais perto ou prepare no dia"
                            ),
                        )
                    )
            if onde == "geladeira":
                na_geladeira += quantas
            else:
                no_congelador += quantas
            destinos.append(
                DestinoPasso(
                    refeicao_id=refeicao.id,
                    dia=refeicao.dia,
                    tipo=refeicao.tipo,
                    porcoes=_duas_casas(quantas),
                    onde=onde,
                    descongelar_em=descongelar_em,
                )
            )
        total = na_geladeira + no_congelador
        passo = Passo(
            receita=self._resumo(receita),
            porcoes=_duas_casas(total),
            fator=tres_casas(total / receita.rendimento_porcoes),
            porcoes_geladeira=_duas_casas(na_geladeira),
            porcoes_congelador=_duas_casas(no_congelador),
            destinos=destinos,
            avisos=[a.texto for a in avisos],
        )
        return passo, avisos
