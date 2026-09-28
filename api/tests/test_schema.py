"""O schema faz o que promete.

Cada teste aqui cobre uma das regras invioláveis do CLAUDE.md. São elas que a
gente não quer descobrir quebradas depois de três meses de dados.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.enums import TipoConta, TipoTransacao
from app.models import Categoria, Conta, Pessoa, Transacao


def _categoria(session: Session, nome: str = "Mercado") -> Categoria:
    cat = Categoria(nome=nome, tipo=TipoTransacao.DESPESA)
    session.add(cat)
    session.flush()
    return cat


def _transacao(session: Session, **kwargs: object) -> Transacao:
    padrao = {
        "data": date(2026, 8, 1),
        "competencia": date(2026, 8, 1),
        "valor": Decimal("100.00"),
        "tipo": TipoTransacao.DESPESA,
        "descricao": "Compra",
    }
    tx = Transacao(**{**padrao, **kwargs})
    session.add(tx)
    session.flush()
    return tx


class TestDinheiro:
    def test_valor_guarda_duas_casas_exatas(self, session: Session) -> None:
        """`numeric(12,2)` — nada de float comendo centavo."""
        tx = _transacao(session, valor=Decimal("1234.56"))
        session.commit()
        session.refresh(tx)
        assert tx.valor == Decimal("1234.56")

    def test_valor_negativo_e_recusado(self, session: Session) -> None:
        """O sinal vem de `tipo`; o valor é sempre positivo."""
        with pytest.raises(IntegrityError):
            _transacao(session, valor=Decimal("-10.00"))


class TestSoftDelete:
    def test_remocao_marca_deleted_em_e_some_da_view(self, session: Session) -> None:
        tx = _transacao(session)
        session.commit()

        session.execute(
            text("UPDATE transacoes SET deleted_em = now() WHERE id = :id"), {"id": tx.id}
        )
        session.commit()

        # A linha continua na tabela...
        assert session.get(Transacao, tx.id) is not None
        # ...mas some de toda leitura.
        visiveis = session.execute(
            text("SELECT count(*) FROM vw_transacoes_completa WHERE id = :id"), {"id": tx.id}
        ).scalar()
        assert visiveis == 0


class TestDedup:
    def test_transacao_identica_esbarra_no_indice_unico(self, session: Session) -> None:
        """Reimportar o mesmo PDF ou aprovar duas vezes não duplica (D-07)."""
        _transacao(session, descricao_original="MERCADO SAO JOSE 01/08")
        session.commit()

        with pytest.raises(IntegrityError):
            _transacao(session, descricao_original="MERCADO SAO JOSE 01/08")
            session.commit()

    def test_dedup_nao_bloqueia_apos_exclusao(self, session: Session) -> None:
        """O índice é parcial: relançar algo excluído tem que passar."""
        tx = _transacao(session, descricao_original="MERCADO SAO JOSE 01/08")
        session.commit()

        session.execute(
            text("UPDATE transacoes SET deleted_em = now() WHERE id = :id"), {"id": tx.id}
        )
        session.commit()

        _transacao(session, descricao_original="MERCADO SAO JOSE 01/08")
        session.commit()  # não levanta


class TestTransferencia:
    def test_transferencia_exige_origem_e_destino(self, session: Session) -> None:
        with pytest.raises(IntegrityError):
            _transacao(session, tipo=TipoTransacao.TRANSFERENCIA)

    def test_transferencia_nao_aceita_categoria(self, session: Session) -> None:
        origem = Conta(nome="Corrente", tipo=TipoConta.CORRENTE)
        destino = Conta(nome="Cartão", tipo=TipoConta.CARTAO)
        session.add_all([origem, destino])
        session.flush()
        cat = _categoria(session)

        with pytest.raises(IntegrityError):
            _transacao(
                session,
                tipo=TipoTransacao.TRANSFERENCIA,
                conta_origem_id=origem.id,
                conta_destino_id=destino.id,
                categoria_id=cat.id,
            )

    def test_despesa_nao_aceita_conta_origem(self, session: Session) -> None:
        conta = Conta(nome="Corrente", tipo=TipoConta.CORRENTE)
        session.add(conta)
        session.flush()

        with pytest.raises(IntegrityError):
            _transacao(session, conta_origem_id=conta.id)


class TestCompetencia:
    def test_competencia_tem_que_ser_dia_primeiro(self, session: Session) -> None:
        with pytest.raises(IntegrityError):
            _transacao(session, competencia=date(2026, 8, 15))

    def test_competencia_pode_diferir_do_mes_da_data(self, session: Session) -> None:
        """Compra de 28/07 caindo na fatura de agosto (D-02)."""
        tx = _transacao(session, data=date(2026, 7, 28), competencia=date(2026, 8, 1))
        session.commit()
        assert tx.data.month == 7
        assert tx.competencia.month == 8


class TestDescricaoOriginal:
    def test_descricao_original_e_imutavel(self, session: Session) -> None:
        tx = _transacao(session, descricao_original="TEXTO CRU DO EXTRATO")
        session.commit()

        with pytest.raises(DBAPIError, match="imutavel"):
            session.execute(
                text("UPDATE transacoes SET descricao_original = 'editado' WHERE id = :id"),
                {"id": tx.id},
            )
            session.commit()

    def test_descricao_do_usuario_e_editavel(self, session: Session) -> None:
        tx = _transacao(session, descricao_original="TEXTO CRU", descricao="Compra")
        session.commit()

        tx.descricao = "Compras do mês"
        session.commit()
        session.refresh(tx)
        assert tx.descricao == "Compras do mês"
        assert tx.descricao_original == "TEXTO CRU"


class TestCategorias:
    def test_hierarquia_para_em_dois_niveis(self, session: Session) -> None:
        raiz = _categoria(session, "Alimentação")
        filha = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA, categoria_pai_id=raiz.id)
        session.add(filha)
        session.commit()

        neta = Categoria(nome="Hortifruti", tipo=TipoTransacao.DESPESA, categoria_pai_id=filha.id)
        session.add(neta)
        with pytest.raises(DBAPIError, match="2 niveis"):
            session.commit()

    def test_categoria_nao_pode_ser_transferencia(self, session: Session) -> None:
        session.add(Categoria(nome="Errada", tipo=TipoTransacao.TRANSFERENCIA))
        with pytest.raises(IntegrityError):
            session.commit()


class TestAuditoria:
    def test_insert_update_e_delete_viram_linha_de_auditoria(self, session: Session) -> None:
        """Trigger, não código de aplicação — agentes escrevem por outros
        caminhos e todos têm que cair no log (D-06)."""
        tx = _transacao(session)
        session.commit()

        tx.descricao = "Editado"
        session.commit()

        linhas = session.execute(
            text(
                "SELECT acao, autor, dados_antes, dados_depois FROM auditoria "
                "WHERE tabela = 'transacoes' AND registro_id = :id ORDER BY id"
            ),
            {"id": tx.id},
        ).all()

        assert [linha.acao for linha in linhas] == ["INSERT", "UPDATE"]
        assert all(linha.autor == "teste" for linha in linhas)
        # O UPDATE guarda o antes e o depois — é o que permite desfazer.
        assert linhas[1].dados_antes["descricao"] == "Compra"
        assert linhas[1].dados_depois["descricao"] == "Editado"

    def test_atualizado_em_e_preenchido_por_trigger(self, session: Session) -> None:
        tx = _transacao(session)
        session.commit()
        assert tx.atualizado_em is None

        tx.descricao = "Outra coisa"
        session.commit()
        session.refresh(tx)
        assert tx.atualizado_em is not None


class TestSeed:
    def test_seed_e_idempotente(self, session: Session, semeado: None) -> None:
        from app.seed import run

        antes = session.scalar(text("SELECT count(*) FROM categorias"))  # type: ignore[arg-type]
        run()
        depois = session.scalar(text("SELECT count(*) FROM categorias"))  # type: ignore[arg-type]
        assert antes == depois

    def test_seed_cria_as_duas_pessoas(self, session: Session, semeado: None) -> None:
        pessoas = session.query(Pessoa).order_by(Pessoa.id).all()
        assert len(pessoas) == 2
