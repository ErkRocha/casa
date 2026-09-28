"""Geração e leitura dos relatórios (fase 6).

A divisão de responsabilidade aqui é a espinha da D-11 e da regra 7:

* **ler** os números é trabalho da sessão read-only (`app.insights.db`);
* **escrever** o relatório é trabalho deste service, com a sessão normal.

O agente nunca cruza essa linha. Ele recebe JSON e devolve JSON; quem grava é
código de aplicação, com a credencial de aplicação. Não é detalhe de
implementação — é a razão de o modelo não conseguir corromper dado nenhum
mesmo que a saída dele venha adversarial.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.insights import tools
from app.insights.db import sessao_leitura
from app.insights.deteccoes import alertas_deterministicos, relatorio_sem_ia
from app.insights.harness import Execucao, carregar_prompt, gerar_validado
from app.models import Relatorio
from app.schemas.insights import Dossie, RelatorioGerado
from app.services.base import CrudService, RegraViolada

PROMPT_MENSAL = "relatorio_mensal_v1"

#: Versão usada quando o texto sai só dos números, sem modelo. Fica gravada
#: igual: seis meses depois, "por que este relatório é tão seco?" tem que ter
#: resposta na própria linha.
PROMPT_SEM_IA = "deterministico_v1"


class RelatorioService(CrudService[Relatorio]):
    model = Relatorio
    nome_recurso = "relatório"

    def __init__(self, session: Session, hoje: date | None = None) -> None:
        super().__init__(session)
        self.hoje = hoje or date.today()

    # -- leitura -----------------------------------------------------------

    def vigente(self, competencia: date, tipo: str = "mensal") -> Relatorio | None:
        encontrado: Relatorio | None = self.session.scalar(
            self._base_query()
            .where(Relatorio.competencia == competencia)
            .where(Relatorio.tipo == tipo)
        )
        return encontrado

    def ultimos(self, limite: int = 12) -> list[Relatorio]:
        return list(
            self.session.scalars(
                self._base_query().order_by(Relatorio.competencia.desc()).limit(limite)
            )
        )

    # -- geração -----------------------------------------------------------

    def gerar_mensal(
        self,
        competencia: date,
        sem_ia: bool = False,
        meses: int = tools.JANELA_PADRAO,
    ) -> Relatorio:
        """Monta o dossiê, escreve o texto e grava — nessa ordem.

        Se o modelo falhar, nada é gravado: um relatório pela metade é pior
        que nenhum, porque parece completo na listagem.
        """
        if competencia != competencia.replace(day=1):
            raise RegraViolada("A competência tem que ser o primeiro dia do mês.")
        if competencia > self.hoje.replace(day=1):
            raise RegraViolada("Não dá para fechar um mês que ainda não começou.")

        # A leitura acontece numa sessão à parte, com a role read-only. É a
        # única forma de o dossiê ser, por construção, o resultado de uma
        # consulta que não podia ter efeito colateral.
        with sessao_leitura() as leitura:
            dossie = tools.montar_dossie(leitura, competencia, meses, self.hoje)

        if dossie.resumo.transacoes == 0:
            raise RegraViolada(
                f"Nenhum lançamento em {competencia:%m/%Y}. Importe o mês antes de fechá-lo."
            )

        if sem_ia:
            conteudo = relatorio_sem_ia(dossie)
            execucao = Execucao(backend="nenhum", modelo="nenhum", prompt_versao=PROMPT_SEM_IA)
            prompt_versao = PROMPT_SEM_IA
        else:
            conteudo, execucao = self._escrever_com_modelo(dossie)
            prompt_versao = PROMPT_MENSAL

        return self._gravar(
            competencia=competencia,
            conteudo=conteudo,
            dossie=dossie,
            prompt_versao=prompt_versao,
            execucao=execucao,
            meses=meses,
        )

    def _escrever_com_modelo(self, dossie: Dossie) -> tuple[str, Execucao]:
        from app.config import get_settings

        cfg = get_settings()
        alertas = alertas_deterministicos(dossie)

        prompt = carregar_prompt(
            PROMPT_MENSAL,
            {
                "DOSSIE": dossie.model_dump_json(indent=2),
                "ALERTAS": json.dumps(
                    [a.model_dump() for a in alertas], ensure_ascii=False, indent=2
                ),
            },
        )

        execucao = Execucao(
            backend=cfg.insights_backend,
            modelo=cfg.insights_modelo,
            prompt_versao=PROMPT_MENSAL,
        )
        gerado = gerar_validado(prompt, RelatorioGerado, execucao)
        return gerado.como_markdown(dossie.competencia), execucao

    def _gravar(
        self,
        competencia: date,
        conteudo: str,
        dossie: Dossie,
        prompt_versao: str,
        execucao: Execucao,
        meses: int,
        tipo: str = "mensal",
    ) -> Relatorio:
        """Substitui o relatório vigente do mês, preservando o anterior.

        Soft delete em vez de UPDATE: regerar o mês depois de corrigir uma
        categorização é normal, e comparar as duas versões é justamente como
        se descobre que a correção mudou a conclusão.
        """
        anterior = self.vigente(competencia, tipo)
        if anterior is not None:
            anterior.deleted_em = func.now()
            self.session.flush()

        return self.criar(
            {
                "competencia": competencia,
                "tipo": tipo,
                "conteudo": conteudo,
                "dados_base": json.loads(dossie.model_dump_json()),
                "periodo_dados": _intervalo(competencia, meses),
                "prompt_versao": prompt_versao,
                "execucao": execucao.como_dict(),
            }
        )


def _intervalo(competencia: date, meses: int) -> str:
    """Janela considerada, no formato de `daterange` do Postgres.

    Fechado no início e aberto no fim: `[2025-08-01,2026-08-01)` são os doze
    meses até julho, sem ambiguidade sobre o mês da ponta.
    """
    inicio = tools.somar_meses(competencia, -meses)
    fim = tools.somar_meses(competencia, 1)
    return f"[{inicio.isoformat()},{fim.isoformat()})"


def dossie_bruto(competencia: date, meses: int = tools.JANELA_PADRAO) -> dict[str, Any]:
    """Só os números, sem gerar relatório. Serve para conferir uma afirmação."""
    with sessao_leitura() as leitura:
        bruto: dict[str, Any] = json.loads(
            tools.montar_dossie(leitura, competencia, meses).model_dump_json()
        )
    return bruto
