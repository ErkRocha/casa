"""Rastro do documento e deduplicação de extrato sobreposto.

Três perguntas que o usuário fez e que estes testes respondem em código:

1. a transação sabe de que arquivo veio?
2. dá para reabrir o PDF depois?
3. reenviar o extrato do mesmo mês duplica lançamento?

A terceira é a que tem armadilha. A proteção é o índice único sobre
`hash_dedup`, que inclui `forma_pagamento_id` — então qualquer coisa que faça
a mesma linha receber uma forma diferente entre duas importações desliga a
proteção sem levantar erro nenhum.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoPagamento
from app.models import FormaPagamento, Importacao, Transacao
from app.services.ingestao import _ContextoEnriquecimento

FATURAS = Path(__file__).resolve().parents[2] / "faturas"
faturas = sorted(FATURAS.glob("Nubank_*.pdf")) if FATURAS.exists() else []
sem_pdfs = pytest.mark.skipif(not faturas, reason="faturas/ vazia")


def importar(client: TestClient, caminho: Path) -> dict:
    resposta = client.post(
        "/importacoes",
        files={"arquivo": (caminho.name, caminho.read_bytes(), "application/pdf")},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestSugestaoDeterministica:
    """A sugestão não pode depender da ordem física das linhas no Postgres."""

    def test_credito_padrao_e_o_de_menor_id(self, session: Session, semeado: None) -> None:
        """Regressão de um bug real.

        `credito_padrao` era `next(f for f in formas if tipo é credito)` sobre
        uma query sem `ORDER BY`. Com um cartão de crédito por pessoa, qual
        deles vinha primeiro passou a depender da ordem física da tabela — que
        muda a cada UPDATE. Como `forma_pagamento_id` entra no `hash_dedup`, a
        mesma linha reimportada podia gerar hash diferente e escapar da
        deduplicação.
        """
        contexto = _ContextoEnriquecimento.carregar(session)
        creditos = [f for f in contexto.formas if f.tipo is TipoPagamento.CREDITO]
        assert len(creditos) >= 2, "o seed cria um cartão de crédito por pessoa"

        assert contexto.credito_padrao is not None
        assert contexto.credito_padrao.id == min(f.id for f in creditos)

        # E a lista inteira sai ordenada, não na ordem que o heap devolver.
        ids = [f.id for f in contexto.formas]
        assert ids == sorted(ids)

    def test_recarregar_da_a_mesma_resposta(self, session: Session, semeado: None) -> None:
        """O teste que pega o bug: duas cargas, mesma sugestão.

        Um UPDATE em `formas_pagamento` move a linha para o fim do heap. Antes
        do `ORDER BY`, isso bastava para a segunda carga escolher outro cartão.
        """
        primeira = _ContextoEnriquecimento.carregar(session)
        alvo = primeira.credito_padrao
        assert alvo is not None

        # Mexe em todas as formas, invertendo a ordem física da tabela.
        for forma in session.scalars(select(FormaPagamento).order_by(FormaPagamento.id.desc())):
            # Reatribuir o mesmo valor basta: o UPDATE é o ponto, não a mudança.
            forma.apelido = f"{forma.apelido}"
            session.flush()

        segunda = _ContextoEnriquecimento.carregar(session)
        assert segunda.credito_padrao is not None
        assert segunda.credito_padrao.id == alvo.id


@sem_pdfs
class TestRastroDoDocumento:
    def test_transacao_guarda_de_qual_importacao_veio(
        self, client: TestClient, semeado: None, session: Session
    ) -> None:
        importacao = importar(client, faturas[0])
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        pendentes = [i["id"] for i in itens if i["status"] == "pendente"][:3]

        client.post("/importacoes/itens/aprovar", json={"ids": pendentes})

        transacoes = client.get("/transacoes").json()["items"]
        assert transacoes, "esperava transações promovidas"
        for transacao in transacoes:
            assert transacao["importacao_id"] == importacao["id"]
            assert transacao["importacao_arquivo"] == faturas[0].name
            assert transacao["importacao_tem_arquivo"] is True

    def test_o_pdf_pode_ser_reaberto(self, client: TestClient, semeado: None) -> None:
        importacao = importar(client, faturas[0])

        resposta = client.get(f"/importacoes/{importacao['id']}/arquivo")
        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "application/pdf"
        # Byte a byte igual ao que subiu: é comprovante, não aproximação.
        assert resposta.content == faturas[0].read_bytes()
        assert "inline" in resposta.headers["content-disposition"]

    def test_importacao_sem_arquivo_guardado_da_404(
        self, client: TestClient, semeado: None, session: Session
    ) -> None:
        """Importação anterior à migration 0004 não tem o PDF."""
        importacao = importar(client, faturas[0])
        alvo = session.get(Importacao, importacao["id"])
        assert alvo is not None
        alvo.arquivo_conteudo = None
        session.commit()

        assert client.get(f"/importacoes/{importacao['id']}/arquivo").status_code == 404

    def test_lancamento_manual_nao_tem_origem(self, client: TestClient, semeado: None) -> None:
        """Nulo aqui é informação: distingue digitado de importado."""
        client.post(
            "/transacoes",
            json={
                "data": "2026-07-05",
                "valor": "10.00",
                "tipo": "despesa",
                "descricao": "Digitado à mão",
            },
        )
        transacao = client.get("/transacoes").json()["items"][0]
        assert transacao["importacao_id"] is None
        assert transacao["importacao_arquivo"] is None
        # Falso, e não nulo: a view calcula `arquivo_conteudo IS NOT NULL`, e
        # num LEFT JOIN sem correspondência isso dá falso. Quem distingue
        # "digitado à mão" de "importado sem arquivo guardado" é o
        # `importacao_id` acima, não este campo.
        assert transacao["importacao_tem_arquivo"] is False


@sem_pdfs
class TestExtratoReenviado:
    """O cenário da semana 1 e da semana 2."""

    def test_o_mesmo_arquivo_e_barrado_na_importacao(
        self, client: TestClient, semeado: None
    ) -> None:
        importar(client, faturas[0])
        resposta = client.post(
            "/importacoes",
            files={"arquivo": (faturas[0].name, faturas[0].read_bytes(), "application/pdf")},
        )
        assert resposta.status_code == 409
        assert "já foi importado" in resposta.json()["detail"]

    def test_linha_ja_no_banco_entra_marcada_como_duplicada(
        self, client: TestClient, semeado: None, session: Session
    ) -> None:
        """O ponto do passo: ver o que é novo **antes** de aprovar.

        Simula o reenvio driblando o bloqueio por hash de arquivo — que é
        exatamente o que acontece de verdade quando o extrato da semana 2
        contém as linhas da semana 1 mais algumas novas.
        """
        primeira = importar(client, faturas[0])
        itens = client.get(f"/importacoes/{primeira['id']}").json()["itens"]
        pendentes = [i["id"] for i in itens if i["status"] == "pendente"]
        assert pendentes, "esperava itens pendentes"

        client.post("/importacoes/itens/aprovar", json={"ids": pendentes[:5]})
        promovidas = session.scalars(select(Transacao).where(Transacao.deleted_em.is_(None))).all()
        assert promovidas

        # Libera o arquivo para poder reimportá-lo.
        alvo = session.get(Importacao, primeira["id"])
        assert alvo is not None
        alvo.hash_arquivo = "outro-hash-para-simular-extrato-maior"
        session.commit()

        segunda = importar(client, faturas[0])
        itens_2 = client.get(f"/importacoes/{segunda['id']}").json()["itens"]

        duplicados = [i for i in itens_2 if i["status"] == "duplicado"]
        assert len(duplicados) >= 5, (
            "as linhas já promovidas tinham que vir marcadas como duplicadas, "
            "sem depender de o usuário aprovar para descobrir"
        )
        assert all("Já existe no banco" in (i["motivo_rejeicao"] or "") for i in duplicados)

    def test_aprovar_duplicata_nao_insere_de_novo(
        self, client: TestClient, semeado: None, session: Session
    ) -> None:
        """A garantia final é do índice único, não da marcação na tela."""
        primeira = importar(client, faturas[0])
        itens = client.get(f"/importacoes/{primeira['id']}").json()["itens"]
        pendentes = [i["id"] for i in itens if i["status"] == "pendente"][:5]
        client.post("/importacoes/itens/aprovar", json={"ids": pendentes})

        quantidade_antes = len(
            session.scalars(select(Transacao).where(Transacao.deleted_em.is_(None))).all()
        )

        alvo = session.get(Importacao, primeira["id"])
        assert alvo is not None
        alvo.hash_arquivo = "outro-hash"
        session.commit()

        segunda = importar(client, faturas[0])
        itens_2 = client.get(f"/importacoes/{segunda['id']}").json()["itens"]
        # Aprova tudo, inclusive o que já veio marcado como duplicado.
        resultado = client.post(
            "/importacoes/itens/aprovar", json={"ids": [i["id"] for i in itens_2]}
        ).json()

        depois = len(session.scalars(select(Transacao).where(Transacao.deleted_em.is_(None))).all())
        # A invariante que importa: entraram exatamente as que o serviço disse
        # ter promovido — nenhuma linha repetida escorreu junto.
        assert depois - quantidade_antes == resultado["promovidos"]
        assert resultado["duplicados"] >= 5
