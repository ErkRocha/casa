"""Schemas da tela de relatórios (fase 6). Só leitura."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class RelatorioResumo(BaseModel):
    """Uma linha da lista: o mês e como o texto foi feito."""

    id: int
    competencia: date
    #: "mensal" | "anual" | "avulso".
    tipo: str
    #: Escrito por modelo (com IA) ou só dos números (seco).
    com_ia: bool
    #: Arquivo de prompt usado (regra 9), ex. "relatorio_mensal_v1".
    prompt_versao: str
    #: Quando foi gerado.
    criado_em: datetime


class RelatorioDetalhe(RelatorioResumo):
    #: Markdown escrito pelo modelo ou pelo gerador seco. Conteúdo não
    #: confiável: a tela renderiza sem HTML bruto.
    conteudo: str
    #: O dossiê exatamente como o modelo o recebeu (`dados_base`). É contra
    #: estes números que se confere o texto (regra 7). Nulo se não foi salvo.
    dossie: dict[str, Any] | None
    #: Janela de competências considerada: [inicio, fim), fim exclusivo.
    periodo_inicio: date | None
    periodo_fim: date | None
    #: Telemetria da geração (D-12): backend, modelo, tentativas, duração.
    execucao: dict[str, Any]
