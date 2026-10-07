"""scripts/local/subir.sh recusa subir quando outro banco pode estar ativo (D-17).

Com docker, netstat e Postgres falsos; nada sobe de verdade."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests_sem_banco._falsos import CONFIG, SUBIR, Ambiente, montar_ambiente, sem_shell

pytestmark = sem_shell


@pytest.fixture
def amb(tmp_path: Path) -> Ambiente:
    return montar_ambiente(tmp_path)


def _checar(amb: Ambiente, **extra: str) -> subprocess.CompletedProcess[str]:
    """Só a verificação, sem subir nada."""
    return amb.rodar("-c", f'source "{CONFIG.as_posix()}" && casa_checar_banco_unico', **extra)


class TestBancoUnico:
    def test_container_do_db_rodando_recusa(self, amb: Ambiente) -> None:
        r = amb.rodar(SUBIR.as_posix(), FAKE_DB_RODANDO="1")
        assert r.returncode == 1
        assert "container do banco (casa_db) está rodando" in r.stderr
        assert "pg_ctl" not in amb.log, "não pode ter tentado subir o Postgres"

    def test_porta_ocupada_por_outro_processo_recusa(self, amb: Ambiente) -> None:
        netstat = "  TCP    127.0.0.1:55432        0.0.0.0:0              LISTENING       999\\n"
        r = amb.rodar(SUBIR.as_posix(), FAKE_NETSTAT=netstat)
        assert r.returncode == 1
        assert "porta 55432 já está ocupada por outro processo (PID 999)" in r.stderr
        assert "pg_ctl" not in amb.log

    def test_porta_ocupada_pelo_proprio_postgres_local_passa(self, amb: Ambiente) -> None:
        (amb.raiz / "dev" / "pgdata" / "postmaster.pid").write_text("999\n", encoding="utf-8")
        netstat = "  TCP    127.0.0.1:55432        0.0.0.0:0              LISTENING       999\\n"
        assert _checar(amb, FAKE_NETSTAT=netstat).returncode == 0

    def test_outra_porta_ocupada_nao_importa(self, amb: Ambiente) -> None:
        netstat = "  TCP    127.0.0.1:5432         0.0.0.0:0              LISTENING       999\\n"
        assert _checar(amb, FAKE_NETSTAT=netstat).returncode == 0

    def test_tudo_livre_passa(self, amb: Ambiente) -> None:
        assert _checar(amb).returncode == 0

    def test_depois_da_migracao_recusa_e_permite_forcar(self, amb: Ambiente) -> None:
        amb.marcador.write_text("migrado para o Docker em 08/10/2026\n", encoding="utf-8")
        r = amb.rodar(SUBIR.as_posix())
        assert r.returncode == 1
        assert "cópia congelada" in r.stderr
        assert _checar(amb, CASA_FORCAR_LOCAL="1").returncode == 0
