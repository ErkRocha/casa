"""scripts/migrar_para_docker.sh para no portão certo (D-17).

Com docker, make e Postgres falsos: cada teste faz um portão falhar e confere
que o script parou ali, sem seguir adiante nem apagar nada."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests_sem_banco._falsos import MIGRAR, Ambiente, montar_ambiente, sem_shell

pytestmark = sem_shell


@pytest.fixture
def amb(tmp_path: Path) -> Ambiente:
    return montar_ambiente(tmp_path)


def _etapas(saida: str) -> dict[str, str]:
    """As linhas do resumo: etapa -> OK / FALHOU / não executada."""
    resumo = saida.split("== migrar: resumo ==")[-1]
    resultado = {}
    for linha in resumo.splitlines():
        partes = linha.split(maxsplit=1)
        if len(partes) == 2 and partes[0] in {
            "docker",
            "backup",
            "versao",
            "parar",
            "restore",
            "contagens",
            "validar",
            "sync",
        }:
            resultado[partes[0]] = partes[1].strip()
    return resultado


def _migrar(amb: Ambiente, **extra: str) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    r = amb.rodar(MIGRAR.as_posix(), **extra)
    return r, _etapas(r.stdout)


class TestMigracao:
    def test_sucesso_passa_todas_as_etapas(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb)
        assert r.returncode == 0, r.stdout + r.stderr
        assert set(etapas.values()) == {"OK"} and len(etapas) == 8
        log = amb.log
        # A ordem importa: dump antes de parar o local, restore antes do roles.
        for antes, depois in [
            ("pg_dump", "stop -m fast"),
            ("compose up -d --wait db", "pg_restore"),
            ("pg_restore", "make --no-print-directory roles"),
            ("make --no-print-directory roles", "compose up -d --build"),
            ("make --no-print-directory validar", "make --no-print-directory sync simular=1"),
        ]:
            assert antes in log and depois in log, (antes, depois)
            assert log.index(antes) < log.index(depois), (antes, depois)
        backups = list((amb.raiz / "backups").iterdir())
        assert any(b.suffix == ".dump" for b in backups)
        contagens = next(b for b in backups if b.name.endswith(".txt"))
        assert "transacoes=10" in contagens.read_text("utf-8")
        assert amb.marcador.exists()
        assert "local 16, compose 16" in r.stdout

    def test_docker_fora_do_ar_para_no_primeiro_portao(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, FAKE_DOCKER_INFO="1")
        assert r.returncode == 1
        assert etapas["docker"] == "FALHOU" and etapas["backup"] == "não executada"
        assert "pg_dump" not in amb.log

    def test_sem_make_para_no_primeiro_portao(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, MAKE="make_que_nao_existe")
        assert etapas["docker"] == "FALHOU"
        assert "winget install" in r.stderr

    def test_pg_dump_falha(self, amb: Ambiente) -> None:
        _, etapas = _migrar(amb, FAKE_PG_DUMP_FALHA="1")
        assert etapas["backup"] == "FALHOU" and etapas["versao"] == "não executada"
        assert "compose up" not in amb.log

    def test_postgres_local_mais_novo_para_sem_parar_o_local(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, FAKE_PG_VERSAO="170002")
        assert etapas["versao"] == "FALHOU" and etapas["parar"] == "não executada"
        assert "mais novo" in r.stderr
        assert "stop" not in amb.log, "o ambiente local não pode ter sido parado"
        assert "compose up" not in amb.log

    def test_container_com_dados_nao_e_sobrescrito(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, FAKE_TABELAS_CONTAINER="12")
        assert etapas["restore"] == "FALHOU"
        assert "já tem 12 tabela(s)" in r.stderr
        assert "pg_restore" not in amb.log

    def test_pg_restore_falha(self, amb: Ambiente) -> None:
        _, etapas = _migrar(amb, FAKE_RESTORE="1")
        assert etapas["restore"] == "FALHOU" and etapas["contagens"] == "não executada"
        assert "roles" not in amb.log

    def test_make_roles_falha(self, amb: Ambiente) -> None:
        _, etapas = _migrar(amb, FAKE_MAKE_FALHA="roles")
        assert etapas["restore"] == "FALHOU"

    def test_contagem_diferente_para_no_portao_sem_marcar(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, FAKE_DIF_TABELA="transacoes")
        assert r.returncode == 1
        assert etapas["contagens"] == "FALHOU" and etapas["validar"] == "não executada"
        assert "transacoes=10" in r.stdout and "transacoes=11" in r.stdout
        assert "Nada foi apagado" in r.stderr
        assert not amb.marcador.exists(), "o local não pode virar cópia congelada"
        assert "compose up -d --build" not in amb.log

    def test_validar_falha(self, amb: Ambiente) -> None:
        _, etapas = _migrar(amb, FAKE_MAKE_FALHA="validar")
        assert etapas["validar"] == "FALHOU" and etapas["sync"] == "não executada"
        # O portão das contagens já passou: o Docker é o banco ativo.
        assert amb.marcador.exists()

    def test_sync_simulada_falha(self, amb: Ambiente) -> None:
        r, etapas = _migrar(amb, FAKE_MAKE_FALHA="sync")
        assert r.returncode == 1 and etapas["sync"] == "FALHOU"

    def test_nao_roda_duas_vezes(self, amb: Ambiente) -> None:
        amb.marcador.write_text("migrado para o Docker em 08/10/2026\n", encoding="utf-8")
        r, _ = _migrar(amb)
        assert r.returncode == 1 and "já foi feita" in r.stderr
        assert amb.log == ""
