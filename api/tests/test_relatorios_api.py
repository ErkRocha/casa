"""Tela de relatórios (fase 6): a API de leitura.

Só leitura: lista paginada, mais recente primeiro, e o detalhe com o texto e
o dossiê de números que o produziu. Nenhuma rota escreve.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Auditoria, Relatorio
from app.services.insights import RelatorioService

DOSSIE = {"competencia": "2026-07-01", "resumo": {"despesas": "750.00", "transacoes": 4}}


def _relatorio(
    session: Session,
    competencia: date,
    *,
    prompt: str = "relatorio_mensal_v1",
    conteudo: str = "# Julho\n\nTexto.",
    dossie: dict[str, Any] | None = None,
    tipo: str = "mensal",
) -> Relatorio:
    r = Relatorio(
        competencia=competencia,
        tipo=tipo,
        conteudo=conteudo,
        dados_base=DOSSIE if dossie is None else dossie,
        periodo_dados=f"[{competencia.replace(year=competencia.year - 1)},{competencia})",
        prompt_versao=prompt,
        execucao={"backend": "claude_code", "modelo": "x", "tentativas": 1},
    )
    session.add(r)
    session.commit()
    return r


class TestLista:
    def test_mais_recente_primeiro_com_ia_ou_seco(
        self, client: TestClient, session: Session
    ) -> None:
        _relatorio(session, date(2026, 5, 1), prompt="deterministico_v1")
        _relatorio(session, date(2026, 7, 1))
        _relatorio(session, date(2026, 6, 1))

        corpo = client.get("/relatorios").json()

        assert corpo["total"] == 3
        assert [i["competencia"] for i in corpo["items"]] == [
            "2026-07-01",
            "2026-06-01",
            "2026-05-01",
        ]
        assert [i["com_ia"] for i in corpo["items"]] == [True, True, False]
        primeiro = corpo["items"][0]
        assert primeiro["prompt_versao"] == "relatorio_mensal_v1"
        assert primeiro["tipo"] == "mensal"
        assert "criado_em" in primeiro
        # A lista não carrega o texto nem os números: é leve.
        assert "conteudo" not in primeiro and "dossie" not in primeiro

    def test_paginada(self, client: TestClient, session: Session) -> None:
        for mes in range(1, 6):
            _relatorio(session, date(2026, mes, 1))
        pagina = client.get("/relatorios", params={"limit": 2, "offset": 2}).json()
        assert pagina["total"] == 5
        assert [i["competencia"] for i in pagina["items"]] == ["2026-03-01", "2026-02-01"]

    def test_relatorio_substituido_nao_aparece(self, client: TestClient, session: Session) -> None:
        """Regerar o mês apaga (soft) o anterior: a lista mostra o vigente."""
        antigo = _relatorio(session, date(2026, 7, 1), conteudo="versão velha")
        antigo.deleted_em = func.now()
        session.commit()
        novo = _relatorio(session, date(2026, 7, 1), conteudo="versão nova")

        itens = client.get("/relatorios").json()["items"]
        assert [i["id"] for i in itens] == [novo.id]
        assert client.get(f"/relatorios/{antigo.id}").status_code == 404

    def test_vazio(self, client: TestClient) -> None:
        assert client.get("/relatorios").json() == {
            "items": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
        }


class TestDetalhe:
    def test_texto_dossie_e_periodo(self, client: TestClient, session: Session) -> None:
        r = _relatorio(session, date(2026, 7, 1))
        corpo = client.get(f"/relatorios/{r.id}").json()

        assert corpo["conteudo"] == "# Julho\n\nTexto."
        assert corpo["dossie"] == DOSSIE
        assert corpo["com_ia"] is True
        assert (corpo["periodo_inicio"], corpo["periodo_fim"]) == ("2025-07-01", "2026-07-01")
        assert corpo["execucao"]["backend"] == "claude_code"

    def test_sem_dossie_salvo_vem_nulo(self, client: TestClient, session: Session) -> None:
        r = _relatorio(session, date(2026, 7, 1), dossie={})
        assert client.get(f"/relatorios/{r.id}").json()["dossie"] is None

    def test_inexistente_e_404(self, client: TestClient) -> None:
        assert client.get("/relatorios/999").status_code == 404

    def test_texto_vai_como_veio(self, client: TestClient, session: Session) -> None:
        """A API não sanitiza nem interpreta: quem renderiza sem HTML é a tela."""
        texto = "# Mês\n\n<script>alert(1)</script> **negrito**"
        r = _relatorio(session, date(2026, 7, 1), conteudo=texto)
        assert client.get(f"/relatorios/{r.id}").json()["conteudo"] == texto


def test_dossie_de_um_relatorio_gerado_de_verdade(
    client: TestClient, session: Session, semeado: None
) -> None:
    """Do gerador seco até a tela: os números gravados chegam inteiros."""
    resposta = client.post(
        "/transacoes",
        json={"data": "2026-07-05", "valor": "123.45", "tipo": "despesa", "descricao": "Mercado"},
    )
    assert resposta.status_code == 201, resposta.text
    gerado = RelatorioService(session, hoje=date(2026, 8, 10)).gerar_mensal(
        date(2026, 7, 1), sem_ia=True
    )
    session.commit()

    corpo = client.get(f"/relatorios/{gerado.id}").json()
    assert corpo["com_ia"] is False
    assert corpo["prompt_versao"] == "deterministico_v1"
    assert corpo["dossie"]["resumo"]["despesas"] == "123.45"
    assert corpo["dossie"]["competencia"] == "2026-07-01"
    assert corpo["conteudo"] == gerado.conteudo


def test_nenhuma_rota_de_relatorios_escreve(client: TestClient, session: Session) -> None:
    """Só GET: gerar continua pelo CLI no host (`make relatorio`)."""
    metodos = {
        metodo
        for rota in app.routes
        if getattr(rota, "path", "").startswith("/relatorios")
        for metodo in getattr(rota, "methods", set())
    }
    assert metodos <= {"GET", "HEAD"}, metodos

    r = _relatorio(session, date(2026, 7, 1))
    antes = session.scalar(select(func.count()).select_from(Auditoria))
    client.get("/relatorios")
    client.get(f"/relatorios/{r.id}")
    assert session.scalar(select(func.count()).select_from(Auditoria)) == antes
    for metodo in ("post", "put", "patch", "delete"):
        assert getattr(client, metodo)(f"/relatorios/{r.id}").status_code == 405


@pytest.mark.parametrize("caminho", ["/relatorios", "/relatorios/1"])
def test_rotas_aparecem_no_openapi(client: TestClient, caminho: str) -> None:
    rota = caminho.replace("/1", "/{id_}")
    assert rota in client.get("/openapi.json").json()["paths"]
