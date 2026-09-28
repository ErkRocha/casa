"""Fecha o mês: gera o relatório e grava em `relatorios`.

    python -m scripts.relatorio                    # mês anterior fechado
    python -m scripts.relatorio --competencia 2026-07
    python -m scripts.relatorio --sem-ia           # só os números, sem modelo
    python -m scripts.relatorio --dossie           # imprime os números e sai
    python -m scripts.relatorio --mostrar          # relê o que já foi gravado

Sem `--sem-ia`, chama o Claude Code local (a assinatura, não a API) para
escrever o texto em cima dos números. Com `--sem-ia`, o mesmo relatório sai
apenas do SQL — mais seco e sempre disponível.

Os números **nunca** vêm do modelo: ele recebe o dossiê pronto e escreve
sobre ele (regra 7). Para conferir qualquer afirmação do texto, rode
`--dossie` na mesma competência e compare.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from sqlalchemy import text

from app.db import SessionLocal
from app.insights.harness import BackendIndisponivel, FalhaDoModelo
from app.insights.tools import somar_meses
from app.services.base import RegraViolada
from app.services.insights import RelatorioService, dossie_bruto


def _competencia(texto: str | None, hoje: date) -> date:
    """`AAAA-MM`, ou o último mês fechado quando nada for passado."""
    if texto is None:
        return somar_meses(hoje.replace(day=1), -1)
    try:
        ano, mes = texto.split("-")[:2]
        return date(int(ano), int(mes), 1)
    except (ValueError, IndexError):
        raise SystemExit(f"competência inválida: {texto!r} — use AAAA-MM") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competencia", help="Mês no formato AAAA-MM. Padrão: mês anterior.")
    parser.add_argument(
        "--sem-ia", action="store_true", help="Gera só com os números, sem chamar modelo."
    )
    parser.add_argument("--dossie", action="store_true", help="Imprime os números em JSON e sai.")
    parser.add_argument(
        "--mostrar", action="store_true", help="Imprime o relatório já gravado e sai."
    )
    parser.add_argument("--hoje", help="Data de referência (AAAA-MM-DD). Padrão: hoje.")
    args = parser.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()
    competencia = _competencia(args.competencia, hoje)

    if args.dossie:
        print(json.dumps(dossie_bruto(competencia), ensure_ascii=False, indent=2))
        return 0

    with SessionLocal() as sessao:
        sessao.execute(text("SELECT set_config('app.autor', 'insights', false)"))
        servico = RelatorioService(sessao, hoje=hoje)

        if args.mostrar:
            existente = servico.vigente(competencia)
            if existente is None:
                print(f"Nenhum relatório gravado para {competencia:%m/%Y}.", file=sys.stderr)
                return 1
            print(existente.conteudo)
            return 0

        if not args.sem_ia:
            print(f"Fechando {competencia:%m/%Y}... (pode levar alguns segundos)", file=sys.stderr)

        try:
            relatorio = servico.gerar_mensal(competencia, sem_ia=args.sem_ia)
        except RegraViolada as erro:
            print(f"ERRO: {erro}", file=sys.stderr)
            return 1
        except BackendIndisponivel as erro:
            print(f"ERRO: {erro}", file=sys.stderr)
            return 2
        except FalhaDoModelo as erro:
            # Sem fallback silencioso para `--sem-ia`: um relatório mais pobre
            # que o pedido, gravado sem avisar, é indistinguível de um bom.
            print(f"ERRO: o modelo não devolveu saída válida — {erro}", file=sys.stderr)
            print("Tente de novo, ou use --sem-ia para gerar só com os números.", file=sys.stderr)
            return 3

        sessao.commit()

        print(relatorio.conteudo)
        print(file=sys.stderr)
        print(
            f"gravado: relatorio #{relatorio.id} · prompt {relatorio.prompt_versao} · "
            f"{relatorio.execucao.get('tentativas', 0)} tentativa(s) · "
            f"{relatorio.execucao.get('duracao_ms', 0)}ms",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
