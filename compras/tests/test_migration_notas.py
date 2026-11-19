"""A migration 0006 migra os dados e reverte (D-33).

Volta o banco para a 0005, cria dados no formato antigo (associação só com
produto, apelido de GTIN, item já comprado), sobe de novo e confere o que a
migration fez. Devolve o banco ao `head` no fim, de qualquer jeito: os outros
testes dependem dele.
"""

from __future__ import annotations

import os
from typing import Any

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from compras.config import url_para_alembic
from compras.db import SessionLocal, engine

GTIN = "7891234567895"
CNPJ_1 = "11222333000181"
CNPJ_2 = "44555666000172"


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["COMPRAS_DATABASE_URL"]))
    return config


def _um(sessao: Session, sql: str, **params: Any) -> Any:
    return sessao.execute(text(sql), params).scalar_one()


def _dados_antigos() -> None:
    with SessionLocal() as s:
        secao = _um(s, "INSERT INTO compras.secoes (nome, ordem) VALUES ('Mig', 1) RETURNING id")

        def produto(nome: str) -> int:
            return int(
                _um(
                    s,
                    "INSERT INTO compras.produtos (nome, nome_normalizado, secao_id) "
                    "VALUES (:n, upper(:n), :s) RETURNING id",
                    n=nome,
                    s=secao,
                )
            )

        def mercado(cnpj: str) -> int:
            return int(
                _um(
                    s,
                    "INSERT INTO compras.mercados (nome, cnpj) VALUES (:c, :c) RETURNING id",
                    c=cnpj,
                )
            )

        def nota(numero: int, mercado_id: int) -> int:
            return int(
                _um(
                    s,
                    "INSERT INTO compras.notas_fiscais (chave_acesso, mercado_id, url_consulta, "
                    "status, lida_por, valor_total) "
                    "VALUES (:ch, :m, 'x', 'lida', 'teste', 50) RETURNING id",
                    ch=str(numero).zfill(44),
                    m=mercado_id,
                )
            )

        def item(
            nota_id: int, linha: int, descricao: str, codigo: str | None, unidade: str,
            produto_id: int | None, gtin: str | None = None,
        ) -> None:  # fmt: skip
            s.execute(
                text(
                    "INSERT INTO compras.nota_itens (nota_fiscal_id, linha_num, codigo, gtin, "
                    "descricao_original, quantidade, unidade, valor_total, produto_id, "
                    "origem_associacao) VALUES (:n, :l, :c, :g, :d, 1, :u, 5, :p, "
                    "CASE WHEN CAST(:p AS bigint) IS NULL THEN NULL "
                    "ELSE CAST('usuario' AS compras.origem_associacao) END)"
                ),
                {"n": nota_id, "l": linha, "c": codigo, "g": gtin, "d": descricao, "u": unidade,
                 "p": produto_id},
            )  # fmt: skip

        leite, banana = produto("leite"), produto("banana")
        m1, m2 = mercado(CNPJ_1), mercado(CNPJ_2)
        n1, n2 = nota(1, m1), nota(2, m2)
        item(n1, 1, "LEITE ITALAC 1L", "0001077397", "UN", leite, GTIN)
        item(n1, 2, "BANANA KG", "000555", "KG", banana)
        item(n1, 3, "SEM PRODUTO", "999", "UN", None)
        item(n2, 1, "BANANA KG", "000555", "KG", banana)
        item(n2, 2, "BANANA  Kg", "0", "KG", banana)  # mesma descrição normalizada, sem código

        def apelido(
            produto_id: int, texto: str | None, gtin: str | None, mercado_id: int | None
        ) -> None:
            s.execute(
                text(
                    "INSERT INTO compras.apelidos (produto_id, texto_normalizado, gtin, "
                    "mercado_id, criado_por) VALUES (:p, :t, :g, :m, 'usuario')"
                ),
                {"p": produto_id, "t": texto, "g": gtin, "m": mercado_id},
            )

        apelido(leite, None, GTIN, None)
        apelido(banana, "BANANA KG", None, m1)
        apelido(banana, "BANANA GRANDE", None, None)  # sem item que o explique

        origem = {"o": "manual"}
        s.execute(
            text(
                "INSERT INTO compras.itens_lista (produto_id, situacao, origem, adicionado_por, "
                "comprado_por, comprado_em) VALUES (:p, 'comprado', :o, 'Laura', 'Erik', now())"
            ),
            {"p": leite, **origem},
        )
        s.execute(
            text(
                "INSERT INTO compras.itens_lista (produto_id, situacao, origem, adicionado_por) "
                "VALUES (:p, 'pendente', :o, 'Laura')"
            ),
            {"p": banana, **origem},
        )
        s.commit()


def _colunas(tabela: str) -> set[str]:
    with engine.connect() as c:
        return set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'compras' AND table_name = :t"
                ),
                {"t": tabela},
            ).scalars()
        )


def test_migration_0006_migra_os_dados_e_reverte() -> None:
    config = _config()
    command.downgrade(config, "0005")
    try:
        assert "variante_id" not in _colunas("nota_itens")
        _dados_antigos()
        command.upgrade(config, "head")

        with SessionLocal() as s:
            variantes = list(
                s.execute(
                    text(
                        "SELECT v.id, v.nome, p.nome AS produto_nome, v.gtin, v.pesada, "
                        "v.medida_base::text AS medida_base, v.criado_por, v.deleted_em "
                        "FROM compras.variantes v JOIN compras.produtos p ON p.id = v.produto_id"
                    )
                )
            )
            # O apelido de GTIN virou a variante do leite, com o GTIN e o nome da nota.
            (leite,) = [v for v in variantes if v.nome == "LEITE ITALAC 1L"]
            assert leite.produto_nome == "leite"
            assert (leite.gtin, leite.pesada, leite.criado_por) == (GTIN, False, "migracao")
            # A banana, em KG: uma variante por mercado, pesada, sem medida inventada.
            bananas = [v for v in variantes if v.nome == "BANANA KG"]
            assert len(bananas) == 2
            assert all(b.pesada and b.medida_base == "g" for b in bananas)
            # O apelido sem item que o explique ganhou variante própria.
            assert [v.produto_nome for v in variantes if v.nome == "BANANA GRANDE"] == ["banana"]
            assert len(variantes) == 4

            itens = {
                (r.nota, r.linha): r
                for r in s.execute(
                    text(
                        "SELECT n.chave_acesso::bigint AS nota, i.linha_num AS linha, "
                        "i.variante_id, i.produto_id FROM compras.nota_itens i "
                        "JOIN compras.notas_fiscais n ON n.id = i.nota_fiscal_id"
                    )
                )
            }
            assert itens[(1, 1)].variante_id == leite.id
            assert itens[(1, 3)].variante_id is None and itens[(1, 3)].produto_id is None
            assert all(
                itens[(n, ln)].variante_id is not None for n, ln in [(1, 1), (1, 2), (2, 1), (2, 2)]
            )
            # As duas linhas da mesma descrição normalizada, no mesmo mercado, são uma variante.
            assert itens[(2, 1)].variante_id == itens[(2, 2)].variante_id
            assert itens[(1, 2)].variante_id != itens[(2, 1)].variante_id

            codigos = {
                (r.cnpj, r.codigo): r.variante_id
                for r in s.execute(
                    text(
                        "SELECT m.cnpj, c.codigo, c.variante_id FROM compras.variante_codigos c "
                        "JOIN compras.mercados m ON m.id = c.mercado_id"
                    )
                )
            }
            # Sem zeros à esquerda; o código "0" (só zeros) não vira nada.
            assert codigos == {
                (CNPJ_1, "1077397"): leite.id,
                (CNPJ_1, "555"): itens[(1, 2)].variante_id,
                (CNPJ_2, "555"): itens[(2, 1)].variante_id,
            }

            apelidos = s.execute(
                text(
                    "SELECT texto_normalizado, gtin, variante_id, produto_id, "
                    "deleted_em IS NOT NULL AS apagado FROM compras.apelidos ORDER BY id"
                )
            ).all()
            assert all(a.variante_id is not None for a in apelidos)
            do_gtin = next(a for a in apelidos if a.gtin == GTIN)
            assert do_gtin.apagado and do_gtin.variante_id == leite.id
            do_texto = next(a for a in apelidos if a.texto_normalizado == "BANANA KG")
            assert not do_texto.apagado and do_texto.variante_id == itens[(1, 2)].variante_id

            fechamentos = s.execute(
                text(
                    "SELECT situacao::text, fechamento::text, fechado_por FROM compras.itens_lista "
                    "ORDER BY id"
                )
            ).all()
            assert [tuple(f) for f in fechamentos] == [
                ("comprado", "sem_nota", "migracao"),
                ("pendente", None, None),
            ]
            assert "categoria_id_financas" in _colunas("secoes")

        # Volta de novo: o apelido de GTIN reaparece, as colunas somem.
        command.downgrade(config, "0005")
        assert not {"variante_id", "item_lista_id"} & _colunas("nota_itens")
        assert "fechamento" not in _colunas("itens_lista")
        with SessionLocal() as s:
            assert _um(s, "SELECT deleted_em IS NULL FROM compras.apelidos WHERE gtin = :g", g=GTIN)
            assert (
                _um(s, "SELECT count(*) FROM compras.nota_itens WHERE produto_id IS NOT NULL") == 4
            )
    finally:
        command.upgrade(config, "head")

    assert {"variante_id", "item_lista_id"} <= _colunas("nota_itens")
