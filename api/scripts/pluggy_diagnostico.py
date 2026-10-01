"""Diagnóstico da Pluggy — somente leitura (fase 5b).

    python api/scripts/pluggy_diagnostico.py                 # da raiz do repo
    cd api && python -m scripts.pluggy_diagnostico --item ID
    make pluggy-diagnostico item=ID

Autentica, lê items, contas, transações dos últimos 60 dias e faturas de
cartão, e grava o JSON **bruto** de cada resposta em
`pluggy_amostras/<data_hora>/`, com um `indice.json` dizendo o que é cada
arquivo. As amostras viram fixture dos passos 3 e 5 da Fase 5b.

No terminal, só contagens, tipos e ids. O resto — nomes, descrições, valores,
documento do titular — fica nos arquivos, e `pluggy_amostras/` está no
`.gitignore`: é dado financeiro pessoal.

Responde as duas perguntas em aberto da Fase 5b:

* as transações de cartão `POSTED` trazem `creditCardMetadata.billId`?
* o `id` de uma transação se mantém quando ela passa de `PENDING` para
  `POSTED`? Para isso, compara automaticamente com a execução anterior
  encontrada na pasta. Rode de novo depois do fechamento da fatura.

Nada aqui escreve na Pluggy nem no banco. O id do item vem de `--item`, de
`PLUGGY_ITEM_IDS` no `.env` ou, se a Pluggy liberou o recurso (opt-in),
de `GET /v2/items`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    # Execução direta (`python api/scripts/pluggy_diagnostico.py`): sem isto,
    # `app` não está no caminho de import.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import Settings
from app.pluggy import (
    PluggyAutenticacaoErro,
    PluggyCliente,
    PluggyErro,
    PluggyRespostaErro,
    RespostaBruta,
    Transacao,
)

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = RAIZ / ".env"
PASTA_AMOSTRAS = RAIZ / "pluggy_amostras"
DIAS_PADRAO = 60


class _Ambiente(BaseSettings):
    """O que só o diagnóstico lê do `.env`."""

    model_config = SettingsConfigDict(env_file=ARQUIVO_ENV, extra="ignore")

    pluggy_item_ids: str = ""


# --- gravação das amostras -----------------------------------------------------


class Gravador:
    """Recebe cada resposta bruta do cliente e grava em disco, como veio."""

    def __init__(self, pasta: Path) -> None:
        self.pasta = pasta
        self.indice: list[dict[str, Any]] = []
        self._paginas: Counter[tuple[str, str]] = Counter()

    def __call__(self, resposta: RespostaBruta) -> None:
        # Criada só na primeira resposta: execução que falha antes de ler
        # qualquer coisa não deixa pasta vazia para trás.
        self.pasta.mkdir(parents=True, exist_ok=True)
        nome = f"{len(self.indice) + 1:03d}_{self._rotulo(resposta)}.json"
        (self.pasta / nome).write_bytes(resposta.conteudo)
        self.indice.append(
            {
                "arquivo": nome,
                "metodo": resposta.metodo,
                "caminho": resposta.caminho,
                "params": resposta.params,
                "status": resposta.status,
            }
        )
        # Reescrito a cada resposta: se a execução cair no meio, o que já foi
        # gravado continua legível pela comparação da próxima.
        (self.pasta / "indice.json").write_text(
            json.dumps(self.indice, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _rotulo(self, r: RespostaBruta) -> str:
        if r.caminho == "/accounts":
            return f"accounts_{r.params.get('itemId', '')}"
        if r.caminho == "/v2/transactions":
            return self._paginado("transactions", r.params.get("accountId", ""))
        if r.caminho == "/bills":
            return f"bills_{r.params.get('accountId', '')}_p{r.params.get('page', '1')}"
        if r.caminho == "/v2/items":
            return self._paginado("items", "todos")
        return r.caminho.strip("/").replace("/", "_")

    def _paginado(self, tipo: str, chave: str) -> str:
        self._paginas[(tipo, chave)] += 1
        return f"{tipo}_{chave}_p{self._paginas[(tipo, chave)]}"


# --- resumo de transação e comparação entre execuções ---------------------------


@dataclass(frozen=True, slots=True)
class Resumo:
    """O mínimo de uma transação para comparar duas execuções."""

    id: str
    conta: str
    status: str
    valor: Decimal
    data: date


def resumir(t: Transacao) -> Resumo:
    return Resumo(t.id, t.account_id, t.status or "?", t.amount, t.date.date())


def ler_execucao(pasta: Path) -> dict[str, Resumo]:
    """Transações de uma execução anterior, lidas das amostras brutas."""
    indice_arquivo = pasta / "indice.json"
    if not indice_arquivo.exists():
        return {}
    resumos: dict[str, Resumo] = {}
    for entrada in json.loads(indice_arquivo.read_text(encoding="utf-8")):
        if entrada.get("caminho") != "/v2/transactions":
            continue
        caminho = pasta / entrada["arquivo"]
        if not caminho.exists():
            continue
        dados = json.loads(caminho.read_bytes(), parse_float=Decimal)
        for bruto in dados.get("results", []):
            t = Transacao.model_validate(bruto)
            resumos[t.id] = resumir(t)
    return resumos


def execucao_anterior(base: Path, atual: Path) -> Path | None:
    """A execução mais recente antes da atual que tenha transações gravadas."""
    if not base.exists():
        return None
    candidatas = sorted(
        (p for p in base.iterdir() if p.is_dir() and p.name < atual.name), reverse=True
    )
    for pasta in candidatas:
        if ler_execucao(pasta):
            return pasta
    return None


@dataclass
class Comparacao:
    pendentes_antes: int = 0
    mesmo_id_postada: list[str] = field(default_factory=list)
    ainda_pendente: list[str] = field(default_factory=list)
    fora_da_janela: list[str] = field(default_factory=list)
    sumiram: list[str] = field(default_factory=list)
    #: (id pendente antigo, id postado novo) com mesma conta e mesmo valor.
    possiveis_trocas: list[tuple[str, str]] = field(default_factory=list)


def comparar(
    anteriores: dict[str, Resumo], atuais: dict[str, Resumo], inicio_janela: date
) -> Comparacao:
    """O que aconteceu com cada transação que estava PENDING antes.

    "Sumiu" é o caso que interessa: ou o id mudou na consolidação, ou a
    transação foi cancelada. Para separar os dois, procura uma POSTED nova
    (id que a execução anterior não tinha) na mesma conta e com o mesmo
    valor — é indício de troca de id, não prova.
    """
    comp = Comparacao()
    novas_postadas = [r for r in atuais.values() if r.id not in anteriores and r.status == "POSTED"]
    for antes in anteriores.values():
        if antes.status != "PENDING":
            continue
        comp.pendentes_antes += 1
        agora = atuais.get(antes.id)
        if agora is not None:
            if agora.status == "POSTED":
                comp.mesmo_id_postada.append(antes.id)
            else:
                comp.ainda_pendente.append(antes.id)
        elif antes.data < inicio_janela:
            comp.fora_da_janela.append(antes.id)
        else:
            comp.sumiram.append(antes.id)
            for nova in novas_postadas:
                if nova.conta == antes.conta and nova.valor == antes.valor:
                    comp.possiveis_trocas.append((antes.id, nova.id))
    return comp


# --- execução -------------------------------------------------------------------


@dataclass
class Relatorio:
    pasta: Path
    dias: int = DIAS_PADRAO
    items: list[tuple[str, str]] = field(default_factory=list)
    contas: list[tuple[str, str, str]] = field(default_factory=list)
    transacoes: dict[str, Resumo] = field(default_factory=dict)
    cartao_postadas: int = 0
    cartao_postadas_com_bill: int = 0
    bills_citados: set[str] = field(default_factory=set)
    bills_listados: set[str] = field(default_factory=set)
    anterior: Path | None = None
    comparacao: Comparacao | None = None


def executar(
    cliente: PluggyCliente,
    item_ids: list[str],
    pasta: Path,
    hoje: date,
    dias: int = DIAS_PADRAO,
) -> Relatorio:
    """Lê tudo e monta o relatório. O cliente já vem com o gravador ligado."""
    relatorio = Relatorio(pasta=pasta, dias=dias)
    desde = hoje - timedelta(days=dias)

    for item_id in item_ids:
        item = cliente.obter_item(item_id)
        conector = item.connector
        descricao = (
            f"conector {conector.id} ({conector.name}), isOpenFinance={conector.is_open_finance}"
            if conector
            else "conector ?"
        )
        relatorio.items.append((item.id, f"{descricao}, status={item.status}"))

        for conta in cliente.listar_contas(item_id):
            relatorio.contas.append((conta.id, conta.type, conta.subtype or "?"))

            for t in cliente.iterar_transacoes(conta.id, desde, hoje):
                relatorio.transacoes[t.id] = resumir(t)
                if conta.e_cartao and t.status == "POSTED":
                    relatorio.cartao_postadas += 1
                    bill = t.credit_card_metadata.bill_id if t.credit_card_metadata else None
                    if bill:
                        relatorio.cartao_postadas_com_bill += 1
                        relatorio.bills_citados.add(bill)

            if conta.e_cartao:
                relatorio.bills_listados.update(f.id for f in cliente.listar_faturas(conta.id))

    relatorio.anterior = execucao_anterior(pasta.parent, pasta)
    if relatorio.anterior is not None:
        relatorio.comparacao = comparar(
            ler_execucao(relatorio.anterior), relatorio.transacoes, desde
        )
    return relatorio


def imprimir(r: Relatorio) -> None:
    pendentes = sorted(
        (t for t in r.transacoes.values() if t.status == "PENDING"), key=lambda t: t.id
    )
    status = Counter(t.status for t in r.transacoes.values())

    print(f"\namostras brutas: {r.pasta}")
    print(f"\nitems: {len(r.items)}")
    for item_id, descricao in r.items:
        print(f"  {item_id}  {descricao}")

    print(f"\na. contas: {len(r.contas)}")
    for (tipo, subtipo), n in sorted(Counter((c[1], c[2]) for c in r.contas).items()):
        print(f"   {tipo}/{subtipo}: {n}")
    for conta_id, tipo, subtipo in r.contas:
        n = sum(1 for t in r.transacoes.values() if t.conta == conta_id)
        print(f"   {conta_id}  {tipo}/{subtipo}  {n} transações")
    print(f"   transações por status: {dict(sorted(status.items()))}")

    print("\nb. billId nas transações de cartão POSTED:")
    if r.cartao_postadas == 0:
        print("   nenhuma transação de cartão POSTED na janela — inconclusivo.")
    else:
        print(f"   {r.cartao_postadas_com_bill} de {r.cartao_postadas} trazem billId")
        print(
            f"   {len(r.bills_citados)} faturas citadas; "
            f"{len(r.bills_citados & r.bills_listados)} delas aparecem em GET /bills "
            f"({len(r.bills_listados)} faturas listadas)"
        )
        if r.cartao_postadas_com_bill == r.cartao_postadas:
            print("   -> competência pelo billId é viável (passo 5).")
        elif r.cartao_postadas_com_bill == 0:
            print("   -> billId não vem: o fallback por dia de fechamento vira o caminho.")
        else:
            print("   -> billId vem só em parte: billId quando houver, fallback no resto.")

    print(f"\nc. transações PENDING: {len(pendentes)}")
    for t in pendentes:
        print(f"   {t.id}  conta {t.conta}")

    print("\nd. PENDING -> POSTED, comparando com a execução anterior:")
    if r.anterior is None or r.comparacao is None:
        print("   primeira execução nesta pasta. Rode de novo depois do fechamento da")
        print("   fatura para ver se as pendentes acima viram POSTED com o mesmo id.")
        return
    c = r.comparacao
    print(f"   anterior: {r.anterior.name}; pendentes naquela execução: {c.pendentes_antes}")
    print(f"   viraram POSTED com o mesmo id: {len(c.mesmo_id_postada)}")
    for i in c.mesmo_id_postada:
        print(f"     {i}")
    print(f"   continuam PENDING: {len(c.ainda_pendente)}")
    print(f"   saíram da janela de {r.dias} dias: {len(c.fora_da_janela)}")
    print(f"   sumiram (id mudou ou foram canceladas): {len(c.sumiram)}")
    for i in c.sumiram:
        print(f"     {i}")
    for antigo, novo in c.possiveis_trocas:
        print(f"     possível troca de id: {antigo} -> {novo} (mesma conta e valor)")

    observadas = len(c.mesmo_id_postada) + len(c.sumiram)
    if observadas == 0:
        print("   -> nenhuma consolidação observada ainda; rode depois do fechamento.")
    elif not c.sumiram:
        print(f"   -> id preservado em {observadas} de {observadas} consolidações.")
    else:
        print(
            f"   -> id preservado em {len(c.mesmo_id_postada)} de {observadas}; "
            "confira os casos que sumiram antes de decidir sobre pendentes."
        )


def _item_ids(argumento: list[str] | None, cliente: PluggyCliente) -> list[str]:
    if argumento:
        return argumento
    do_env = [i.strip() for i in _Ambiente().pluggy_item_ids.split(",") if i.strip()]
    if do_env:
        return do_env
    return [item.id for item in cliente.listar_items()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--item", action="append", help="id do item; pode repetir")
    parser.add_argument("--dias", type=int, default=DIAS_PADRAO, help="janela de transações")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    cfg = Settings(_env_file=ARQUIVO_ENV)
    if cfg.pluggy_client_id is None or cfg.pluggy_client_secret is None:
        print(
            f"PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET não estão definidos em {ARQUIVO_ENV} "
            "nem no ambiente.",
            file=sys.stderr,
        )
        return 2

    pasta = PASTA_AMOSTRAS / datetime.now().strftime("%Y%m%d_%H%M%S")
    gravador = Gravador(pasta)
    cliente = PluggyCliente(cfg.pluggy_client_id, cfg.pluggy_client_secret, ao_responder=gravador)
    try:
        with cliente:
            try:
                item_ids = _item_ids(args.item, cliente)
            except PluggyRespostaErro as exc:
                if exc.codigo != "LIST_ITEMS_FEATURE_NOT_ENABLED":
                    raise
                print(
                    "Nenhum id de item informado, e listar items (GET /v2/items) não está "
                    "liberado para esta aplicação na Pluggy.\nPasse --item <id> ou defina "
                    "PLUGGY_ITEM_IDS no .env com o id que a conexão MeuPluggy gerou.",
                    file=sys.stderr,
                )
                return 2
            if not item_ids:
                print("Nenhum item encontrado para esta aplicação.", file=sys.stderr)
                return 2
            relatorio = executar(cliente, item_ids, pasta, date.today(), args.dias)
    except PluggyAutenticacaoErro as exc:
        print(f"Credencial recusada pela Pluggy: {exc}", file=sys.stderr)
        return 1
    except PluggyErro as exc:
        print(f"Falha ao falar com a Pluggy: {exc}", file=sys.stderr)
        print(f"O que chegou a ser lido está em {pasta}", file=sys.stderr)
        return 1

    imprimir(relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
