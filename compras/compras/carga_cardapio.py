"""Carga inicial do cardápio: pessoas, produtos com medidas e 15 receitas (D-30).

    docker compose run --rm compras python -m compras.carga_cardapio
    make compras-carga-cardapio

Idempotente: o que já existe (pelo nome, sem caixa nem acento) não é tocado,
e rodar de novo não muda nada. Usa os services, com o autor `carga_cardapio`.

* Pessoas: Erik (1,5) e Laura (1,0), ligadas à identidade do Tailscale cujo
  `nome` bata (sem acento nem caixa); sem identidade, ficam sem login.
* Produtos: acha pelo nome ou cria (na seção do seed, ou em "Sem seção").
  `medida_base` e `medida_por_unidade` só entram onde estão nulos, e só se a
  `unidade_padrao` do produto for a que a medida pressupõe: edição do casal
  não é sobrescrita.
* Receitas: 1 porção cada, com quantidades **estimadas**: nascem com
  `quantidades_revisadas = false`, até alguém apertar "Conferi, está certa".
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from compras.db import SessionLocal, definir_autor
from compras.enums import MedidaBase, TipoRefeicao, UnidadeMedida
from compras.normalizar import normalizar
from compras.schemas_cardapio import IngredienteEntrada, ReceitaCriar
from compras.services.identidades import IdentidadeService
from compras.services.pessoas import PessoaService
from compras.services.produtos import ProdutoService
from compras.services.receitas import ReceitaService
from compras.services.secoes import SecaoService

AUTOR = "carga_cardapio"

D = Decimal
G, ML, UN = MedidaBase.G, MedidaBase.ML, MedidaBase.UN
U = UnidadeMedida

#: (nome, porção padrão)
PESSOAS: tuple[tuple[str, Decimal], ...] = (("Erik", D("1.5")), ("Laura", D("1.0")))


@dataclass(frozen=True)
class ProdutoCarga:
    nome: str
    secao: str
    unidade_padrao: str
    medida_base: MedidaBase | None = None
    medida_por_unidade: Decimal | None = None


PRODUTOS: tuple[ProdutoCarga, ...] = (
    ProdutoCarga("Aveia em flocos 500g", "Mercearia", "un", G, D(500)),
    ProdutoCarga("Iogurte natural", "Frios e laticínios", "un", G, D(170)),
    ProdutoCarga("Banana", "Hortifrúti", "kg", G, D(120)),
    ProdutoCarga("Leite integral 1L", "Frios e laticínios", "un", ML, D(1000)),
    ProdutoCarga("Ovos 12 un", "Frios e laticínios", "un", UN, D(12)),
    ProdutoCarga("Pão integral fatiado", "Padaria", "un", UN, D(20)),
    ProdutoCarga("Manteiga 200g", "Frios e laticínios", "un", G, D(200)),
    # Sal: sem medida, só "a gosto".
    ProdutoCarga("Sal", "Mercearia", "un"),
    ProdutoCarga("Peito de frango", "Carnes", "kg", G),
    ProdutoCarga("Sobrecoxa de frango", "Carnes", "kg", G),
    ProdutoCarga("Carne moída", "Carnes", "kg", G),
    ProdutoCarga("Queijo mussarela", "Frios e laticínios", "kg", G),
    ProdutoCarga("Tomate", "Hortifrúti", "kg", G, D(120)),
    ProdutoCarga("Cebola", "Hortifrúti", "kg", G, D(150)),
    ProdutoCarga("Alho", "Hortifrúti", "un", UN, D(10)),  # a cabeça tem ~10 dentes
    ProdutoCarga("Cenoura", "Hortifrúti", "kg", G, D(120)),
    ProdutoCarga("Batata", "Hortifrúti", "kg", G, D(150)),
    ProdutoCarga("Batata-doce", "Hortifrúti", "kg", G, D(300)),
    ProdutoCarga("Brócolis", "Hortifrúti", "un", G, D(300)),  # um maço
    ProdutoCarga("Azeite 500ml", "Mercearia", "un", ML, D(500)),
    ProdutoCarga("Arroz 5kg", "Mercearia", "un", G, D(5000)),
    ProdutoCarga("Feijão preto 1kg", "Mercearia", "un", G, D(1000)),
    ProdutoCarga("Macarrão 500g", "Mercearia", "un", G, D(500)),
    ProdutoCarga("Molho de tomate 340g", "Mercearia", "un", G, D(340)),
    ProdutoCarga("Tortilha wrap integral 8 un", "Padaria", "un", UN, D(8)),
)

#: (produto, quantidade, unidade); quantidade nula só com a_gosto.
Linha = tuple[str, Decimal | None, UnidadeMedida]


@dataclass(frozen=True)
class ReceitaCarga:
    nome: str
    tipo: TipoRefeicao
    tempo_preparo_min: int
    modo_preparo: str
    pode_antecipar: bool
    dura_dias: int | None
    pode_congelar: bool
    ingredientes: tuple[Linha, ...]


SAL: Linha = ("Sal", None, U.A_GOSTO)

RECEITAS: tuple[ReceitaCarga, ...] = (
    ReceitaCarga(
        "Aveia de geladeira com iogurte e fruta",
        TipoRefeicao.CAFE_DA_MANHA,
        5,
        "Misture a aveia, o iogurte e o leite num pote, tampe e deixe na geladeira de um dia "
        "para o outro. Sirva com a banana fatiada.",
        True,
        3,
        False,
        (
            ("Aveia em flocos 500g", D(40), U.G),
            ("Iogurte natural", D(1), U.UN),
            ("Leite integral 1L", D(100), U.ML),
            ("Banana", D(1), U.UN),
        ),
    ),
    ReceitaCarga(
        "Ovos mexidos com pão integral",
        TipoRefeicao.CAFE_DA_MANHA,
        10,
        "Bata os ovos com uma pitada de sal. Derreta a manteiga na frigideira, mexa os ovos em "
        "fogo baixo até firmar. Sirva com o pão torrado.",
        False,
        None,
        False,
        (
            ("Ovos 12 un", D(2), U.UN),
            ("Pão integral fatiado", D(2), U.UN),
            ("Manteiga 200g", D(5), U.G),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Sanduíche de frango desfiado",
        TipoRefeicao.LANCHE,
        10,
        "Monte o pão com o frango desfiado, o queijo e o tomate em rodelas. Leve à sanduicheira "
        "ou à frigideira até dourar.",
        False,
        None,
        False,
        (
            ("Pão integral fatiado", D(2), U.UN),
            ("Peito de frango", D(100), U.G),
            ("Queijo mussarela", D(30), U.G),
            ("Tomate", D(40), U.G),
        ),
    ),
    ReceitaCarga(
        "Frango desfiado (base)",
        TipoRefeicao.ALMOCO,
        30,
        "Cozinhe o peito de frango com cebola, alho, azeite e sal até ficar macio. Desfie com "
        "dois garfos e guarde com um pouco do caldo.",
        True,
        4,
        True,
        (
            ("Peito de frango", D(200), U.G),
            ("Cebola", D("0.5"), U.UN),
            ("Alho", D(1), U.UN),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Frango grelhado",
        TipoRefeicao.ALMOCO,
        20,
        "Tempere o frango com alho e sal. Grelhe com um fio de azeite, sem mexer, até dourar dos "
        "dois lados e cozinhar por dentro.",
        True,
        3,
        True,
        (
            ("Peito de frango", D(150), U.G),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            ("Alho", D(1), U.UN),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Arroz",
        TipoRefeicao.ALMOCO,
        25,
        "Refogue a cebola e o alho no azeite, junte o arroz e o sal, cubra com água quente e "
        "cozinhe tampado até secar.",
        True,
        4,
        True,
        (
            ("Arroz 5kg", D(70), U.G),
            ("Alho", D(1), U.UN),
            ("Cebola", D("0.25"), U.UN),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Feijão",
        TipoRefeicao.ALMOCO,
        40,
        "Cozinhe o feijão na panela de pressão até ficar macio. Refogue o alho e a cebola no "
        "azeite, junte o feijão com o caldo e o sal e deixe apurar.",
        True,
        4,
        True,
        (
            ("Feijão preto 1kg", D(80), U.G),
            ("Alho", D(1), U.UN),
            ("Cebola", D("0.25"), U.UN),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Carne moída com legumes",
        TipoRefeicao.ALMOCO,
        30,
        "Refogue a cebola e o alho no azeite, doure a carne moída, junte a cenoura ralada e o "
        "tomate picado, tempere com sal e cozinhe até secar.",
        True,
        3,
        True,
        (
            ("Carne moída", D(150), U.G),
            ("Cenoura", D(60), U.G),
            ("Tomate", D(50), U.G),
            ("Cebola", D("0.5"), U.UN),
            ("Alho", D(1), U.UN),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Batata-doce cozida",
        TipoRefeicao.ALMOCO,
        25,
        "Lave a batata-doce, corte em pedaços e cozinhe em água com sal até ficar macia.",
        True,
        4,
        True,
        (("Batata-doce", D(200), U.G), SAL),
    ),
    ReceitaCarga(
        "Brócolis e cenoura no vapor",
        TipoRefeicao.ALMOCO,
        15,
        "Corte o brócolis em buquês e a cenoura em rodelas. Cozinhe no vapor por uns 8 minutos. "
        "Tempere com azeite e sal.",
        False,
        None,
        False,
        (
            ("Brócolis", D(100), U.G),
            ("Cenoura", D(60), U.G),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Omelete com legumes e queijo",
        TipoRefeicao.JANTA,
        10,
        "Bata os ovos com sal. Refogue a cebola e o tomate picados, junte os ovos, cubra com o "
        "queijo e dobre quando firmar.",
        False,
        None,
        False,
        (
            ("Ovos 12 un", D(3), U.UN),
            ("Queijo mussarela", D(30), U.G),
            ("Tomate", D(40), U.G),
            ("Cebola", D("0.25"), U.UN),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Wrap de frango",
        TipoRefeicao.JANTA,
        15,
        "Aqueça a tortilha, recheie com o frango desfiado, o queijo e o tomate e enrole. Doure "
        "dos dois lados na frigideira.",
        False,
        None,
        False,
        (
            ("Tortilha wrap integral 8 un", D(1), U.UN),
            ("Peito de frango", D(100), U.G),
            ("Queijo mussarela", D(20), U.G),
            ("Tomate", D(40), U.G),
        ),
    ),
    ReceitaCarga(
        "Sopa de legumes com frango",
        TipoRefeicao.JANTA,
        40,
        "Refogue a cebola e o alho no azeite, junte o frango em cubos, a batata e a cenoura, "
        "cubra com água e cozinhe até tudo ficar macio. Acerte o sal.",
        True,
        4,
        True,
        (
            ("Peito de frango", D(100), U.G),
            ("Batata", D(150), U.G),
            ("Cenoura", D(60), U.G),
            ("Cebola", D("0.5"), U.UN),
            ("Alho", D(1), U.UN),
            ("Azeite 500ml", D(1), U.COLHER_CHA),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Macarrão com carne moída",
        TipoRefeicao.ALMOCO,
        30,
        "Cozinhe o macarrão. Refogue a cebola e o alho, doure a carne moída, junte o molho de "
        "tomate e deixe apurar. Misture ao macarrão.",
        True,
        3,
        True,
        (
            ("Macarrão 500g", D(80), U.G),
            ("Carne moída", D(120), U.G),
            ("Molho de tomate 340g", D(100), U.G),
            ("Cebola", D("0.25"), U.UN),
            ("Alho", D(1), U.UN),
            SAL,
        ),
    ),
    ReceitaCarga(
        "Sobrecoxa assada com batata-doce",
        TipoRefeicao.JANTA,
        60,
        "Tempere a sobrecoxa com alho e sal. Disponha numa assadeira com a batata-doce em "
        "pedaços, regue com azeite e asse a 200 graus até dourar.",
        True,
        3,
        True,
        (
            ("Sobrecoxa de frango", D(250), U.G),
            ("Batata-doce", D(200), U.G),
            ("Azeite 500ml", D(1), U.COLHER_SOPA),
            ("Alho", D(1), U.UN),
            SAL,
        ),
    ),
)


@dataclass
class Resumo:
    pessoas_criadas: int = 0
    identidades_ligadas: int = 0
    produtos_criados: int = 0
    produtos_com_medida: int = 0
    receitas_criadas: int = 0

    def mudou(self) -> bool:
        return any(vars(self).values())


def carregar(session: Session, quem: str = AUTOR) -> Resumo:
    """Grava o que faltar, pelos services. Não commita."""
    resumo = Resumo()
    _pessoas(session, quem, resumo)
    produtos = _produtos(session, quem, resumo)
    _receitas(session, quem, resumo, produtos)
    return resumo


def _pessoas(session: Session, quem: str, resumo: Resumo) -> None:
    pessoas = PessoaService(session, quem)
    identidades = IdentidadeService(session)
    for nome, porcao in PESSOAS:
        if pessoas.por_nome(nome) is not None:
            continue  # não sobrescreve pessoa existente
        ocupadas = {p.identidade_id for p in pessoas.listar() if p.identidade_id is not None}
        identidade = next(
            (
                i
                for i in identidades.listar()
                if normalizar(i.nome) == normalizar(nome) and i.id not in ocupadas
            ),
            None,
        )
        pessoas.criar(nome, porcao, identidade.id if identidade is not None else None)
        resumo.pessoas_criadas += 1
        if identidade is not None:
            resumo.identidades_ligadas += 1


def _produtos(session: Session, quem: str, resumo: Resumo) -> dict[str, int]:
    """O id de cada produto da carga, criando e completando as medidas."""
    produtos = ProdutoService(session)
    secoes = SecaoService(session)
    por_nome_da_secao = {s.nome.lower(): s.id for s in secoes.listar()}
    ids: dict[str, int] = {}
    for item in PRODUTOS:
        produto = produtos.por_nome(item.nome)
        if produto is None:
            secao_id = por_nome_da_secao.get(item.secao.lower()) or secoes.sem_secao().id
            produto, _ = produtos.criar(
                item.nome, uuid.uuid4(), secao_id=secao_id, unidade_padrao=item.unidade_padrao
            )
            resumo.produtos_criados += 1
        ids[item.nome] = produto.id

        if item.medida_base is None:
            continue
        mesma_unidade = (produto.unidade_padrao or item.unidade_padrao).lower() == (
            item.unidade_padrao.lower()
        )
        if produto.medida_base is None and produto.medida_por_unidade is None and mesma_unidade:
            campos: dict[str, object] = {
                "medida_base": item.medida_base,
                "medida_por_unidade": item.medida_por_unidade,
            }
            if produto.unidade_padrao is None:
                campos["unidade_padrao"] = item.unidade_padrao
            produtos.atualizar(produto.id, campos)
            resumo.produtos_com_medida += 1
    return ids


def _receitas(session: Session, quem: str, resumo: Resumo, produtos: dict[str, int]) -> None:
    receitas = ReceitaService(session, quem)
    for item in RECEITAS:
        if receitas.por_nome(item.nome) is not None:
            continue  # não sobrescreve
        receitas.criar(
            ReceitaCriar(
                id_cliente=uuid.uuid4(),
                nome=item.nome,
                tipo=item.tipo,
                rendimento_porcoes=D(1),
                tempo_preparo_min=item.tempo_preparo_min,
                modo_preparo=item.modo_preparo,
                pode_antecipar=item.pode_antecipar,
                dura_dias=item.dura_dias,
                pode_congelar=item.pode_congelar,
                ingredientes=[
                    IngredienteEntrada(
                        produto_id=produtos[produto], quantidade=quantidade, unidade=unidade
                    )
                    for produto, quantidade, unidade in item.ingredientes
                ],
            ),
            revisada=False,
        )
        resumo.receitas_criadas += 1


def run() -> Resumo:
    with SessionLocal() as session:
        definir_autor(session, AUTOR)
        resumo = carregar(session)
        session.commit()
    return resumo


if __name__ == "__main__":
    r = run()
    print(
        f"carga do cardápio: {r.pessoas_criadas} pessoa(s) ({r.identidades_ligadas} ligada(s) à "
        f"identidade), {r.produtos_criados} produto(s) novos, {r.produtos_com_medida} com medida "
        f"preenchida, {r.receitas_criadas} receita(s) nova(s)."
    )
