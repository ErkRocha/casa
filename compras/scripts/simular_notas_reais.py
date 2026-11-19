"""Simula, sem gravar nada, o fluxo da D-33 com as duas notas reais anonimizadas.

    python -m scripts.simular_notas_reais        (ou `make notas-simular`)

Lê as duas páginas de `tests/amostras/` (Zaffari, 17/10 e 15/11/2026) pelo
`NotaService`, com uma consulta que devolve os bytes do arquivo (nada de
SEFAZ), contra os dados REAIS do `compras`: associa itens, olha os preços,
as sugestões de despesa e a prévia da conferência. Tudo numa transação que
termina em `rollback()`; a sessão recusa `commit`.

Finanças só é consultada pelos endpoints de leitura (`SomenteLeitura` recusa
`criar_despesa`): nunca lança despesa, nunca consolida, nunca liga a nota.
Depois do rollback, uma sessão nova confere que as contagens não mudaram.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from compras.config import get_settings
from compras.db import SessionLocal, definir_autor
from compras.enums import SituacaoItem
from compras.financas import (
    Financas,
    FinancasHttp,
    FinancasIndisponivel,
    NovaDespesa,
)
from compras.models import (
    Apelido,
    ItemLista,
    NotaFiscal,
    NotaItem,
    Produto,
    Variante,
    VarianteCodigo,
)
from compras.nfce.consulta import Resposta
from compras.nfce.leitor_rs import LeitorSefazRs
from compras.nfce.medida import sugerir_medida
from compras.normalizar import normalizar
from compras.services.base import Conflito, NaoEncontrado
from compras.services.conferencia import FOLGA_DA_MARCACAO, ConferenciaService
from compras.services.ligacao_notas import LigacaoNotaService
from compras.services.notas import NotaService
from compras.services.precos import PrecoService
from compras.services.produtos import ProdutoService
from compras.services.variantes import VarianteService

AUTOR = "simulacao"
AMOSTRAS = Path(__file__).resolve().parent.parent / "tests" / "amostras"
OUTUBRO = AMOSTRAS / "nfce_rs_anonimizada_out.html"
NOVEMBRO = AMOSTRAS / "nfce_rs_anonimizada.html"
SUCO = "SUCO NATURALE LARANJA INT 3L"
PAO = "PAO CACETINHO"

Saida = Callable[[str], None]


class SomenteLeitura:
    """Finanças só pelos GET: tudo é repassado, menos a escrita, que levanta."""

    def __init__(self, interno: Financas) -> None:
        self._interno = interno

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._interno, nome)

    def criar_despesa(self, despesa: NovaDespesa) -> int:
        raise RuntimeError("Simulação: lançar despesa em finanças não é permitido.")


class ConsultaDoArquivo:
    """A "SEFAZ" da simulação: devolve os bytes da página, seja qual for a URL."""

    def __init__(self, conteudo: bytes) -> None:
        self.conteudo = conteudo

    def buscar(self, url: str) -> Resposta:
        return Resposta(self.conteudo, "text/html", url)


def _chave_da_pagina(conteudo: bytes) -> str:
    achada = re.search(rb"chaveNFe=(\d{44})", conteudo)
    if achada is None:
        raise RuntimeError("A página não traz a chave de acesso.")
    return achada.group(1).decode("ascii")


def _contagens(session: Session) -> dict[str, int]:
    modelos: dict[str, Any] = {
        "notas_fiscais": NotaFiscal,
        "variantes": Variante,
        "variante_codigos": VarianteCodigo,
        "apelidos": Apelido,
        "produtos": Produto,
    }
    return {
        nome: int(session.scalar(select(func.count()).select_from(modelo)) or 0)
        for nome, modelo in modelos.items()
    }


def _titulo(saida: Saida, texto: str) -> None:
    saida("")
    saida("=" * 78)
    saida(texto)
    saida("=" * 78)


def _cortar(texto: str | None, n: int) -> str:
    texto = texto or ""
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "-"
    return f"{valor.quantize(Decimal('0.01'))}".replace(".", ",")


# --- associação ---------------------------------------------------------------------


def _casa(session: Session, descricao: str) -> tuple[Produto | None, list[str]]:
    """O produto cujo nome está contido na descrição (ou o contrário), por
    palavras inteiras. Só vale se for único; devolve também os candidatos."""
    d = f" {normalizar(descricao)} "
    achados = [
        p
        for p in session.scalars(select(Produto).where(Produto.deleted_em.is_(None)))
        if f" {p.nome_normalizado} " in d or d in f" {p.nome_normalizado} "
    ]
    nomes = [p.nome for p in achados]
    return (achados[0] if len(achados) == 1 else None), nomes


def _produto_com(session: Session, trecho: str, nome_temporario: str, saida: Saida) -> Produto:
    """O único produto vivo cujo nome contém `trecho`; senão um temporário
    (dentro da transação, que será desfeita)."""
    vivos = [
        p
        for p in session.scalars(select(Produto).where(Produto.deleted_em.is_(None)))
        if trecho in p.nome_normalizado
    ]
    if len(vivos) == 1:
        saida(f"    produto real encontrado: {vivos[0].nome!r}")
        return vivos[0]
    motivo = "nenhum produto real" if not vivos else f"{len(vivos)} produtos reais (ambíguo)"
    produto = ProdutoService(session).obter_ou_criar(nome_temporario)
    saida(f"    {motivo} com {trecho!r}: produto temporário {produto.nome!r} (id {produto.id})")
    return produto


def _nova(item: NotaItem) -> dict[str, Any]:
    """A medida sugerida pela descrição, confirmada; item em KG fica `pesada`."""
    if (item.unidade or "").strip().upper() == "KG":
        return {}
    achada = sugerir_medida(item.descricao_original)
    if achada is None:
        return {}
    return {"medida_base": achada.medida_base, "conteudo": achada.conteudo}


def _associar(servico: NotaService, nota: NotaFiscal, item: NotaItem, produto: Produto) -> NotaItem:
    return servico.associar_variante(
        nota.id, item.id, AUTOR, produto_id=produto.id, nova=_nova(item)
    )


def _mostrar_itens(saida: Saida, servico: NotaService, nota: NotaFiscal) -> list[NotaItem]:
    itens = servico.itens(nota.id)
    saida(
        f"  nota {nota.id}: {len(itens)} itens, total R$ {_brl(nota.valor_total)}, "
        f"forma {nota.forma_pagamento_nota!r}, emitida em {nota.emitida_em:%d/%m/%Y}"
    )
    for i in itens:
        if i.variante is None:
            assoc = "sem variante"
        else:
            origem = i.origem_associacao.value if i.origem_associacao else "?"
            assoc = (
                f"{i.produto.nome if i.produto else '?'} / {i.variante.nome} "
                f"[{origem}, variante {i.variante_id}]"
            )
        saida(
            f"  {i.linha_num:>2} {_cortar(i.descricao_original, 32):<32} "
            f"{i.quantidade.normalize():>6} {i.unidade or '':<3} {_brl(i.valor_total):>8}  {assoc}"
        )
    automaticos = sum(1 for i in itens if i.variante_id is not None)
    saida(f"  associados automaticamente: {automaticos} de {len(itens)}")
    return itens


def _ler(session: Session, caminho: Path) -> NotaFiscal:
    conteudo = caminho.read_bytes()
    servico = NotaService(session, ConsultaDoArquivo(conteudo), LeitorSefazRs())
    nota, nova = servico.ler(_chave_da_pagina(conteudo), AUTOR)
    if not nova:
        raise RuntimeError(
            f"A chave {nota.chave_acesso} já existe nas notas reais (nota {nota.id}): "
            "a simulação não relê nota que já foi lida."
        )
    if nota.status.value != "lida":
        raise RuntimeError(f"A nota não foi lida: {nota.erro_mensagem}")
    return nota


# --- relatório por etapa --------------------------------------------------------------


def _precos(saida: Saida, servico: NotaService, itens: list[NotaItem]) -> None:
    precos = servico.precos_da_nota(itens[0].nota_fiscal_id)
    saida("  desconto / estimado por item associado (as duas notas têm desconto 0):")
    com_desconto = estimados = 0
    for i in itens:
        p = precos.get(i.id)
        if p is None:
            continue
        if (p["desconto_rateado"] or 0) != 0 or i.desconto != 0:
            com_desconto += 1
        if p["preco_pago_estimado"]:
            estimados += 1
    saida(f"    itens com desconto: {com_desconto}; com preço pago estimado: {estimados}")


def _historico(saida: Saida, session: Session, variante_id: int, rotulo: str) -> None:
    variante = VarianteService(session).get(variante_id)
    h = PrecoService(session).historico_da_variante(variante, 20, 0)
    saida(
        f"  histórico de {rotulo} (variante {variante_id}, {variante.nome!r}): "
        f"{h['total']} compra(s), {h['sem_comparavel']} sem comparável"
    )
    for c in h["itens"]:
        comp = c["comparavel"]
        comparavel = f"{_brl(Decimal(comp['valor']))} R$/{comp['por']}" if comp else "-"
        saida(
            f"    {str(c['data'])[:10]}  qtd {Decimal(c['quantidade']).normalize()}  "
            f"cheio {_brl(c['preco_cheio'])}  desconto {_brl(c['desconto'])}  "
            f"pago {_brl(c['preco_pago'])}  estimado={c['preco_pago_estimado']}  "
            f"comparável {comparavel}"
        )


def _despesa(saida: Saida, session: Session, nota: NotaFiscal, financas: Financas) -> None:
    ligacao = LigacaoNotaService(session)
    try:
        sugestoes = ligacao.sugestoes(nota.id, financas)
    except FinancasIndisponivel as exc:
        saida(f"  finanças indisponível: {exc} (sugestões e prévia puladas)")
        return
    saida(
        f"  sugestões de despesa (valor exato R$ {_brl(nota.valor_total)}, ±1 dia, "
        f"forma da nota {nota.forma_pagamento_nota!r}): {len(sugestoes)}"
    )
    for s in sugestoes:
        saida(
            f"    {s.data:%d/%m/%Y}  R$ {_brl(s.valor):>9}  forma {s.cartao or '-'} "
            f"({s.forma_tipo or '-'}, combina={s.forma_combina})  {s.tipo}  "
            f"{_cortar(s.descricao, 30)!r}"
        )
    previa = ligacao.previa(nota.id, financas)
    forma = next(
        (f for f in previa.formas_pagamento if f.id == previa.forma_pagamento_id_sugerida), None
    )
    saida(
        "  prévia do lançamento (GET, nada é lançado): "
        f"valor R$ {_brl(previa.valor)}, data {previa.data:%d/%m/%Y}, "
        f"descrição {previa.descricao!r}, forma da nota {previa.forma_pagamento_nota!r}, "
        f"forma sugerida {forma.apelido if forma else None!r}, "
        f"categoria sugerida {previa.categoria_id_sugerida} (origem {previa.categoria_origem})"
    )
    saida("  (POST lancar-despesa e PUT transacao: NÃO executados.)")


def _lista(nomes: list[str]) -> str:
    return ", ".join(nomes) if nomes else "-"


def _conferencia(saida: Saida, session: Session, nota: NotaFiscal) -> None:
    r = ConferenciaService(session).previa(nota.id)
    saida(f"  conferência (prévia): {r.conferencia}")
    saida(f"    confirmados ({len(r.confirmados)}): {_lista([c.produto for c in r.confirmados])}")
    saida(f"    marcados ({len(r.marcados)}): {_lista([c.produto for c in r.marcados])}")
    saida(f"    extras ({len(r.extras)}): {_lista([c.produto for c in r.extras])}")
    saida(
        f"    continuam pendentes ({len(r.continuam_pendentes)}): "
        f"{_lista([c.produto for c in r.continuam_pendentes])}"
    )
    saida(
        f"    aguardando nota ({len(r.aguardando_nota)}): "
        f"{_lista([c.produto for c in r.aguardando_nota])}"
    )
    saida(
        f"    diferenças ({len(r.diferencas)}): "
        f"{_lista([f'{d.produto} (pedido {d.pedido}, veio {d.veio})' for d in r.diferencas])}"
    )
    saida(
        f"    despensa ({len(r.despensa)}): "
        f"{_lista([f'{d.produto} {d.antes}->{d.depois}' for d in r.despensa])}"
    )
    saida(
        f"    não reconhecidos ({len(r.nao_reconhecidos)}): "
        f"{_lista([_cortar(n.descricao_original, 28) for n in r.nao_reconhecidos])}"
    )
    # Comprado aguardando nota de produto da nota, mas marcado depois dela: não casa.
    produtos = {
        i.produto_id
        for i in NotaService(session).itens(nota.id)
        if i.produto_id is not None and nota.emitida_em is not None
    }
    antigas = [
        item.produto.nome
        for item in session.scalars(
            select(ItemLista).where(
                ItemLista.deleted_em.is_(None),
                ItemLista.situacao == SituacaoItem.COMPRADO,
                ItemLista.fechamento.is_(None),
                ItemLista.produto_id.in_(produtos or {0}),
            )
        )
        if item.comprado_em is not None
        and nota.emitida_em is not None
        and nota.emitida_em <= item.comprado_em - FOLGA_DA_MARCACAO
    ]
    if antigas:
        saida(f"    nota mais antiga que a marcação (não casa): {_lista(antigas)}")
    else:
        saida("    nota mais antiga que a marcação: nenhum caso")


# --- o fluxo ------------------------------------------------------------------------------


def _simular(session: Session, financas: Financas, saida: Saida) -> None:
    servico = NotaService(session, None, None)

    _titulo(saida, "1. Outubro (17/10/2026, 7 itens): leitura e associação automática")
    outubro = _ler(session, OUTUBRO)
    itens_out = _mostrar_itens(saida, servico, outubro)

    _titulo(saida, "2. Outubro: associar aos produtos reais que casam pelo nome")
    suco = next((i for i in itens_out if i.descricao_original == SUCO), None)
    for item in itens_out:
        if item.variante_id is not None:
            continue
        if item is suco:
            saida(f"  {item.linha_num:>2} {item.descricao_original}: sempre associado a um suco")
            produto = _produto_com(session, "suco", "suco de laranja", saida)
        else:
            achado, candidatos = _casa(session, item.descricao_original)
            if achado is None:
                motivo = f"ambíguo: {_lista(candidatos)}" if candidatos else "nenhum produto casa"
                descricao = _cortar(item.descricao_original, 32)
                saida(f"  {item.linha_num:>2} {descricao}: {motivo}; sem variante")
                continue
            produto = achado
        feito = _associar(servico, outubro, item, produto)
        nome_variante = feito.variante.nome if feito.variante else ""
        saida(
            f"  {item.linha_num:>2} {_cortar(item.descricao_original, 32)} -> produto "
            f"{produto.nome!r}, variante {feito.variante_id} {nome_variante!r}, "
            f"medida {_nova(item) or 'sem medida confirmada'}"
        )
    if suco is None or suco.variante_id is None:
        raise RuntimeError("O suco de outubro não ficou associado.")
    variante_suco = suco.variante_id
    ficha = VarianteService(session).get(variante_suco)
    codigos = VarianteService(session).codigos([variante_suco])[variante_suco]
    medida = ficha.medida_base.value if ficha.medida_base else None
    saida(
        f"  variante do suco: {ficha.id}, medida {medida} "
        f"{ficha.conteudo}, códigos {[(c.codigo, c.mercado_id) for c in codigos]}"
    )

    _titulo(saida, "3. Novembro (15/11/2026, 24 itens): leitura e associação automática")
    novembro = _ler(session, NOVEMBRO)
    itens_nov = _mostrar_itens(saida, servico, novembro)
    suco_nov = next((i for i in itens_nov if i.descricao_original == SUCO), None)
    if suco_nov is None:
        saida("  suco de novembro: NÃO ENCONTRADO na nota")
    else:
        mesma = suco_nov.variante_id == variante_suco
        saida(
            f"  suco de novembro: variante {suco_nov.variante_id}, origem "
            f"{suco_nov.origem_associacao.value if suco_nov.origem_associacao else None}; "
            f"mesma variante de outubro (mercado + código): {'SIM' if mesma else 'NÃO'}"
        )
    pao = next((i for i in itens_nov if i.descricao_original == PAO), None)
    if pao is None:
        saida("  pão cacetinho: NÃO ENCONTRADO na nota")
    elif pao.variante_id is None:
        unico = _casa(session, PAO)[0]
        if unico is None:
            produto = ProdutoService(session).obter_ou_criar("pão")
            saida(f"  pão: nenhum produto único casa; produto temporário {produto.nome!r}")
        else:
            produto = unico
        feito = _associar(servico, novembro, pao, produto)
        saida(f"  pão cacetinho (KG) -> produto {produto.nome!r}, variante {feito.variante_id}")
    else:
        saida("  pão cacetinho já veio associado")

    _titulo(saida, "4. Preços")
    _historico(saida, session, variante_suco, "suco")
    if pao is not None and pao.variante_id is not None:
        _historico(saida, session, pao.variante_id, "pão cacetinho")
    session.expire_all()
    for nota in (outubro, novembro):
        saida(f"  nota {nota.id}:")
        _precos(saida, servico, servico.itens(nota.id))
    produto_suco = session.get(Produto, ficha.produto_id)
    nome_suco = produto_suco.nome if produto_suco else ""
    try:
        onde = PrecoService(session).onde_mais_barato(None, nome_suco, 90)
        saida(f"  onde-mais-barato de {nome_suco!r} (90 dias):")
        for linha in onde["ranking"]:
            saida(f"    {linha}")
        if not onde["ranking"]:
            saida("    (ranking vazio)")
    except (Conflito, NaoEncontrado) as exc:
        saida(f"  onde-mais-barato de {nome_suco!r}: {exc}")

    for titulo, nota in (("5", outubro), ("5", novembro)):
        _titulo(saida, f"{titulo}. Despesa da nota de {nota.emitida_em:%d/%m/%Y} (só leitura)")
        _despesa(saida, session, nota, financas)

    for nota in (outubro, novembro):
        _titulo(
            saida, f"6. Conferência da nota de {nota.emitida_em:%d/%m/%Y} (prévia, sem confirmar)"
        )
        _conferencia(saida, session, nota)


def main(
    fabrica: Callable[[], Session] = SessionLocal,
    financas: Financas | None = None,
    saida: Saida = print,
) -> int:
    """Roda a simulação e desfaz tudo. 0 se nada ficou gravado, 1 se algo mudou."""
    if financas is None:
        financas = FinancasHttp(get_settings().financas_url)
    leitura = cast(Financas, SomenteLeitura(financas))

    with fabrica() as sessao:
        antes = _contagens(sessao)
        sessao.rollback()
    saida(f"Antes:  {antes}")

    with fabrica() as sessao:
        definir_autor(sessao, AUTOR)

        def _recusar(_: Any) -> None:
            raise RuntimeError("Simulação: commit não é permitido.")

        # No Connection, não na Session: o savepoint (`begin_nested`) também
        # "comita" na Session, e só o COMMIT de verdade interessa aqui.
        motor = sessao.get_bind()
        event.listen(motor, "commit", _recusar)
        try:
            _simular(sessao, leitura, saida)
            _titulo(saida, "7. Rollback")
            dentro = _contagens(sessao)
            saida(f"  Dentro da transação: {dentro}")
        finally:
            sessao.rollback()
            event.remove(motor, "commit", _recusar)

    with fabrica() as nova:
        depois = _contagens(nova)
        nova.rollback()
    saida(f"Depois: {depois}")
    if depois != antes:
        saida("ATENÇÃO: as contagens mudaram!")
        return 1
    saida("Nada foi gravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
