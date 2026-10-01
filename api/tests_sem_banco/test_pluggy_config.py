"""Configuração da Pluggy (fase 5b, passo 2)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings

SEGREDO = "segredo-de-teste-NAO-PODE-VAZAR"


@pytest.fixture(autouse=True)
def _sem_pluggy_no_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola do `.env` e do ambiente de quem roda o teste."""
    for nome in ("PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET"):
        monkeypatch.delenv(nome, raising=False)


def _settings(**valores: str) -> Settings:
    return Settings(_env_file=None, **valores)  # type: ignore[call-arg]


def test_sem_credenciais_a_sync_fica_desligada() -> None:
    cfg = _settings()
    assert cfg.pluggy_client_id is None
    assert cfg.pluggy_client_secret is None
    assert cfg.pluggy_habilitada is False


def test_string_vazia_conta_como_ausente(monkeypatch: pytest.MonkeyPatch) -> None:
    """É o que o compose entrega quando a variável não está no `.env`."""
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "   ")
    cfg = _settings()
    assert cfg.pluggy_client_id is None
    assert cfg.pluggy_client_secret is None
    assert cfg.pluggy_habilitada is False


def test_so_uma_das_duas_nao_liga_a_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "id-qualquer")
    assert _settings().pluggy_habilitada is False


def test_com_as_duas_a_sync_liga(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "id-qualquer")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", SEGREDO)
    cfg = _settings()
    assert cfg.pluggy_habilitada is True
    assert cfg.pluggy_client_secret is not None
    assert cfg.pluggy_client_secret.get_secret_value() == SEGREDO


def test_secret_nao_vaza_em_repr_str_nem_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "id-qualquer")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", SEGREDO)
    cfg = _settings()
    for texto in (repr(cfg), str(cfg), cfg.model_dump_json(), str(cfg.model_dump())):
        assert SEGREDO not in texto


def test_api_sobe_sem_credenciais_da_pluggy() -> None:
    """`import app.main` sem nenhuma variável da Pluggy.

    Em subprocesso para pegar o import de verdade, com ambiente limpo — no
    mesmo processo o módulo já estaria em cache. Importar não conecta no
    banco (o engine é preguiçoso), então isto roda sem Postgres.
    """
    raiz_api = Path(__file__).resolve().parents[1]
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PLUGGY_")}
    resultado = subprocess.run(
        [sys.executable, "-c", "import app.main as m; print(m.settings.pluggy_habilitada)"],
        cwd=raiz_api,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"
