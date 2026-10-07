"""Comandos falsos para testar os scripts de shell da D-17.

Nada aqui fala com Docker ou banco de verdade: cada teste monta uma pasta de
comandos falsos na frente do PATH, roda o script com `bash` e confere o que
ele chamou e onde parou. Os falsos registram cada chamada em `chamadas.log`.

- `scripts/local/subir.sh` recusa subir com o container do db no ar, com a
  porta ocupada por outro processo ou depois da migração.
- `scripts/migrar_para_docker.sh` para no portão certo, sem seguir adiante.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SUBIR = RAIZ / "scripts" / "local" / "subir.sh"
CONFIG = RAIZ / "scripts" / "local" / "_config.sh"
MIGRAR = RAIZ / "scripts" / "migrar_para_docker.sh"


def _bash() -> str | None:
    """O bash do Git (ou do Linux). O `bash` do System32 é o do WSL: não serve."""
    candidatos = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"]
    for c in candidatos:
        if c and Path(c).exists() and "system32" not in c.lower():
            return c
    return None


BASH = _bash()
#: Os scripts ficam fora do container (só `api/` é montado) e pedem bash.
sem_shell = pytest.mark.skipif(
    BASH is None or not SUBIR.exists(), reason="precisa de bash e dos scripts (roda no host)"
)

FALSOS = {
    "docker": r"""
echo "docker $*" >>"$FAKE_LOG"
case "$1" in
  info) exit "${FAKE_DOCKER_INFO:-0}" ;;
  ps) [[ -n "${FAKE_DB_RODANDO:-}" ]] && echo casa_db; exit 0 ;;
  compose)
    shift
    case "$1" in
      up)
        [[ "$*" == *"--wait db"* ]] && exit "${FAKE_UP_DB:-0}"
        exit "${FAKE_UP_TUDO:-0}" ;;
      exec)
        cmd="${@: -1}"
        if [[ "$cmd" == *pg_tables* ]]; then echo "${FAKE_TABELAS_CONTAINER:-0}"; exit 0; fi
        if [[ "$cmd" == *pg_restore* ]]; then cat >/dev/null; exit "${FAKE_RESTORE:-0}"; fi
        if [[ "$cmd" =~ count\(\*\)\ FROM\ ([a-z_]+) ]]; then
          t="${BASH_REMATCH[1]}"; n=${#t}
          [[ "$t" == "${FAKE_DIF_TABELA:-}" ]] && n=$((n + 1))
          echo "$n"; exit 0
        fi
        exit 0 ;;
    esac ;;
esac
exit 0
""",
    "make": r"""
echo "make $*" >>"$FAKE_LOG"
for a in "$@"; do
  [[ -n "${FAKE_MAKE_FALHA:-}" && "$a" == "$FAKE_MAKE_FALHA" ]] && exit 1
done
exit 0
""",
    "netstat": r"""printf '%b' "${FAKE_NETSTAT:-}" """,
    "taskkill": r"""echo "taskkill $*" >>"$FAKE_LOG" """,
}

# Ferramentas do Postgres local, no LOCAL_PG_BIN falso.
FALSOS_PG = {
    "pg_isready.exe": r"""[[ -f "$CASA_DEV_DIR/pg_rodando" ]]""",
    "pg_ctl.exe": r"""
echo "pg_ctl $*" >>"$FAKE_LOG"
[[ "$*" == *start* ]] && touch "$CASA_DEV_DIR/pg_rodando"
[[ "$*" == *stop* ]] && rm -f "$CASA_DEV_DIR/pg_rodando"
exit 0
""",
    "pg_dump.exe": r"""
echo "pg_dump $*" >>"$FAKE_LOG"
[[ -n "${FAKE_PG_DUMP_FALHA:-}" ]] && exit 1
while [[ $# -gt 0 ]]; do [[ "$1" == -f ]] && echo DUMP >"$2"; shift; done
exit 0
""",
    "psql.exe": r"""
q="${@: -1}"
if [[ "$q" == *server_version_num* ]]; then echo "${FAKE_PG_VERSAO:-160010}"; exit 0; fi
if [[ "$q" =~ count\(\*\)\ FROM\ ([a-z_]+) ]]; then t="${BASH_REMATCH[1]}"; echo "${#t}"; exit 0; fi
exit 0
""",
}


@dataclass
class Ambiente:
    raiz: Path
    env: dict[str, str]

    @property
    def log(self) -> str:
        arquivo = self.raiz / "chamadas.log"
        return arquivo.read_text("utf-8") if arquivo.exists() else ""

    @property
    def marcador(self) -> Path:
        return self.raiz / "dev" / "MIGRADO_PARA_DOCKER"

    def rodar(self, *comando: str, **extra: str) -> subprocess.CompletedProcess[str]:
        assert BASH is not None
        return subprocess.run(
            [BASH, *comando],
            cwd=RAIZ,
            env=self.env | extra,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )


def _escrever(pasta: Path, nome: str, corpo: str) -> None:
    arquivo = pasta / nome
    arquivo.write_text("#!/usr/bin/env bash\n" + corpo.lstrip("\n"), encoding="utf-8", newline="\n")
    arquivo.chmod(0o755)


def montar_ambiente(tmp_path: Path) -> Ambiente:
    falsos, pg_bin, dev = tmp_path / "bin", tmp_path / "pgbin", tmp_path / "dev"
    for pasta in (falsos, pg_bin, dev / "pgdata"):
        pasta.mkdir(parents=True)
    for nome, corpo in FALSOS.items():
        _escrever(falsos, nome, corpo)
    for nome, corpo in FALSOS_PG.items():
        _escrever(pg_bin, nome, corpo)

    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{falsos.as_posix()}{os.pathsep}{env.get('PATH', '')}",
            "FAKE_LOG": (tmp_path / "chamadas.log").as_posix(),
            "CASA_DEV_DIR": dev.as_posix(),
            "LOCAL_PG_BIN": pg_bin.as_posix(),
            "LOCAL_PG_PORT": "55432",
            "LOCAL_POSTGRES_PASSWORD": "senha_local",
            "LOCAL_INSIGHTS_PASSWORD": "senha_ro",
            "MIGRAR_BACKUPS": (tmp_path / "backups").as_posix(),
            "COMPOSE": "docker compose",
            "MAKE": "make",
        }
    )
    # Nada do ambiente de quem roda os testes vaza para os falsos.
    for chave in [k for k in env if k.startswith("FAKE_") and k != "FAKE_LOG"]:
        del env[chave]
    env.pop("DATABASE_URL", None)
    return Ambiente(tmp_path, env)
