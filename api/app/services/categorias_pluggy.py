"""Mapeamento de categorias da Pluggy (D-21).

Liga a categoria que a Pluggy dá a cada transação (`categoryId` e nome) a uma
`categoria` daqui. O enriquecimento usa o mapeamento depois das regras do
usuário e antes do local conhecido (`_ContextoEnriquecimento`).

Duas guardas, as duas da D-21:

* **transferência da Pluggy não vira despesa.** As famílias `Transfers`,
  `Same person transfer` e `Third-party transfers` dizem como o dinheiro
  saiu, não em quê foi gasto: um Pix para pessoa pode ser gasto ou repasse.
  Mapear uma delas para categoria de despesa é recusado;
* **o tipo tem que bater** — isso é checado no uso, não aqui: o mesmo
  mapeamento pode apontar para receita, e então não vale para despesa.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.models import Categoria, CategoriaPluggy
from app.services.base import CrudService, RegraViolada

#: Prefixo de dois dígitos do `categoryId` das famílias de transferência:
#: 04 Same person transfer, 05 Transfers, 06 Third-party transfers.
PREFIXOS_TRANSFERENCIA = ("04", "05", "06")

#: Os mesmos, pelo nome — a árvore publicada pela Pluggy dá os ids só do
#: primeiro nível, e a comparação por nome cobre os outros dois.
NOMES_TRANSFERENCIA = frozenset(
    {
        "Same person transfer",
        "Transfers",
        "Third-party transfers",
        "Credit card payment",
        "Bank slip",
        "Debt card",
        "DOC",
        "PIX",
        "TED",
    }
)
_PREFIXOS_NOME_TRANSFERENCIA = ("Transfer - ", "Same person transfer - ")


def e_transferencia_pluggy(pluggy_categoria_id: str | None, nome: str | None) -> bool:
    """A categoria da Pluggy é de uma das famílias de transferência?"""
    if pluggy_categoria_id and pluggy_categoria_id[:2] in PREFIXOS_TRANSFERENCIA:
        return True
    nome = (nome or "").strip()
    return nome in NOMES_TRANSFERENCIA or nome.startswith(_PREFIXOS_NOME_TRANSFERENCIA)


class CategoriaPluggyService(CrudService[CategoriaPluggy]):
    model = CategoriaPluggy
    nome_recurso = "mapeamento de categoria Pluggy"

    def criar(self, dados: dict[str, Any]) -> CategoriaPluggy:
        self._checa(dados["pluggy_categoria_id"], dados["pluggy_categoria_nome"], dados)
        return super().criar(dados)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> CategoriaPluggy:
        if "categoria_id" in dados and dados["categoria_id"] is None:
            raise RegraViolada("'categoria_id' é obrigatório no mapeamento.")
        obj = self.get(id_)
        if "categoria_id" in dados:
            nome = dados.get("pluggy_categoria_nome") or obj.pluggy_categoria_nome
            self._checa(obj.pluggy_categoria_id, nome, dados)
        return super().atualizar(id_, dados)

    def remover(self, id_: int) -> None:
        """Desativa: `ativo` falso e soft delete, como o mapeamento de contas.

        `deleted_em` libera o id da Pluggy para um mapeamento novo.
        """
        self.get(id_).ativo = False
        super().remover(id_)

    def _checa(self, pluggy_id: str, nome: str, dados: dict[str, Any]) -> None:
        categoria = self.session.get(Categoria, dados["categoria_id"])
        if categoria is None or categoria.deleted_em is not None:
            raise RegraViolada(f"Categoria {dados['categoria_id']} não existe.")
        if not categoria.ativo:
            raise RegraViolada(f"A categoria '{categoria.nome}' está inativa.")
        if categoria.tipo is TipoTransacao.DESPESA and e_transferencia_pluggy(pluggy_id, nome):
            raise RegraViolada(
                f"'{nome}' é uma categoria de transferência da Pluggy e não pode apontar para "
                f"categoria de despesa ('{categoria.nome}'): um Pix ou TED pode ser gasto ou "
                "repasse, e quem decide é a revisão (D-21)."
            )


def carregar_mapa(session: Session) -> dict[str, tuple[int, TipoTransacao]]:
    """Mapeamentos ativos, por id da Pluggy: `(categoria_id, tipo da categoria)`.

    Ordem por id: com dois mapeamentos vivos para o mesmo id (o banco não
    deixa, mas o código não conta com isso), vence o mais antigo, sempre.
    """
    linhas = session.execute(
        select(CategoriaPluggy.pluggy_categoria_id, Categoria.id, Categoria.tipo)
        .join(Categoria, Categoria.id == CategoriaPluggy.categoria_id)
        .where(
            CategoriaPluggy.deleted_em.is_(None),
            CategoriaPluggy.ativo.is_(True),
            Categoria.deleted_em.is_(None),
            Categoria.ativo.is_(True),
        )
        .order_by(CategoriaPluggy.id)
    ).all()
    mapa: dict[str, tuple[int, TipoTransacao]] = {}
    for pluggy_id, categoria_id, tipo in linhas:
        mapa.setdefault(pluggy_id, (categoria_id, tipo))
    return mapa


# --------------------------------------------------------------------------
# Proposta inicial (D-21)
# --------------------------------------------------------------------------
#
# Pelo nome que a Pluggy publica para os três níveis da árvore (a
# documentação só dá o id do primeiro; o script de proposta pega os ids dos
# dados reais). O alvo é um caminho da árvore daqui, "Raiz" ou "Raiz › Sub";
# havendo mais de um, vale o primeiro que existir no banco. Nada aqui é
# gravado sozinho: `scripts/pluggy_categorias.py` mostra a proposta e só
# grava com `--aplicar`.

PROPOSTA_INICIAL: dict[str, tuple[str, ...]] = {
    # Receita
    "Income": ("Receita",),
    "Salary": ("Receita › Salário",),
    "Entrepreneurial activities": ("Receita › Freelance",),
    "Retirement": ("Receita › Outros",),
    "Government aid": ("Receita › Outros",),
    "Non-recurring income": ("Receita › Outros",),
    "Proceeds interests and dividends": ("Receita › Outros",),
    # Alimentação
    "Groceries": ("Alimentação › Mercado",),
    "Food and drinks": ("Alimentação",),
    "Eating out": ("Alimentação › Restaurante",),
    "Food delivery": ("Alimentação › Delivery",),
    # Casa
    "Housing": ("Casa",),
    "Rent": ("Casa › Aluguel",),
    "Houseware": ("Casa",),
    "Utilities": ("Casa › Contas",),
    "Water": ("Casa › Contas",),
    "Electricity": ("Casa › Contas",),
    "Gas": ("Casa › Contas",),
    "Telecommunications": ("Casa › Contas",),
    "Internet": ("Casa › Contas",),
    "Mobile": ("Casa › Contas",),
    "TV": ("Casa › Contas",),
    # Transporte
    "Transportation": ("Transporte",),
    "Taxi and ride-hailing": ("Transporte › App/Corrida",),
    "Public transportation": ("Transporte › Transporte público",),
    "Bicycle": ("Transporte",),
    "Automotive": ("Transporte",),
    "Gas stations": ("Transporte › Combustível",),
    "Parking": ("Transporte",),
    "Tolls and in-vehicle payment": ("Transporte",),
    "Vehicle maintenance": ("Transporte",),
    # Assinaturas
    "Video streaming": ("Assinaturas › Streaming",),
    "Music streaming": ("Assinaturas › Streaming",),
    "Gyms and fitness centers": ("Assinaturas › Academia",),
    # Saúde
    "Healthcare": ("Saúde",),
    "Pharmacy": ("Saúde › Farmácia",),
    "Dentist": ("Saúde › Consultas",),
    "Hospital clinics and labs": ("Saúde › Consultas",),
    "Optometry": ("Saúde",),
    "Health insurance": ("Saúde › Plano de saúde",),
    # Lazer
    "Leisure": ("Lazer",),
    "Tickets": ("Lazer",),
    "Stadiums and arenas": ("Lazer",),
    "Landmarks and museums": ("Lazer",),
    "Cinema, theater and concerts": ("Lazer › Cinema/Shows",),
    "Gaming": ("Lazer › Hobbies",),
    "Travel": ("Lazer › Viagem",),
    "Airport and airlines": ("Lazer › Viagem",),
    "Accommodation": ("Lazer › Viagem",),
    "Bus tickets": ("Lazer › Viagem",),
    # Educação
    "Education": ("Educação",),
    "Online Courses": ("Educação › Cursos",),
    "University": ("Educação",),
    "School": ("Educação",),
    "Kindergarten": ("Educação",),
    "Bookstore": ("Educação › Livros",),
    # Pessoal
    "Clothing": ("Pessoal › Vestuário",),
    "Wellness": ("Pessoal › Cuidados pessoais",),
    # Pets é categoria (D-04), mas não está no seed: só vale se existir.
    "Pet supplies and vet": ("Pets",),
    # Juros e encargos: criada como dado em 06/10/2026 (encargos de fatura).
    "Interests charged": ("Juros e encargos",),
    "Late payment and overdraft costs": ("Juros e encargos",),
    "Tax on financial operations": ("Juros e encargos",),
    "Bank fees": ("Juros e encargos",),
    "Account fees": ("Juros e encargos",),
    "Wire transfer fees and ATM fees": ("Juros e encargos",),
    "Credit card fees": ("Juros e encargos",),
}

#: Ficam sem mapeamento de propósito, com o motivo: o item vai para a revisão
#: sem categoria. Transferência não está aqui porque tem regra própria
#: (`e_transferencia_pluggy`).
AMBIGUAS: dict[str, str] = {
    "Shopping": "genérica: compra de qualquer coisa",
    "Online shopping": "loja online vende de tudo; a categoria depende do que foi comprado",
    "Electronics": "sem categoria equivalente na árvore",
    "Sports goods": "sem categoria equivalente na árvore",
    "Office Supplies": "sem categoria equivalente na árvore",
    "Kids and toys": "sem categoria equivalente na árvore",
    "Cashback": "crédito de cashback: receita ou estorno, a decidir",
    "Donations": "doação não é presente, e a árvore só tem Presentes",
    "Gambling": "sem categoria equivalente na árvore",
    "Lottery": "sem categoria equivalente na árvore",
    "Online bet": "sem categoria equivalente na árvore",
    "Insurance": "sem categoria de seguros",
    "Life insurance": "sem categoria de seguros",
    "Home Insurance": "sem categoria de seguros",
    "Vehicle insurance": "sem categoria de seguros",
    "Taxes": "imposto não tem categoria",
    "Income taxes": "imposto não tem categoria",
    "Taxes on investments": "imposto não tem categoria",
    "Vehicle ownership taxes and fees": "IPVA e taxas: Transporte ou imposto, a decidir",
    "Traffic tickets": "multa: Transporte ou outra coisa, a decidir",
    "Urban land and building tax": "IPTU: Casa › Contas ou imposto, a decidir",
    "Loans and financing": (
        "parcela de empréstimo ou financiamento; nos dados reais também cobre "
        "pagamento de fatura por débito automático (D-05)"
    ),
    "Loans": "parcela de empréstimo: dívida, não gasto do mês",
    "Financing": "parcela de financiamento: dívida, não gasto do mês",
    "Real estate financing": "parcela de financiamento: dívida, não gasto do mês",
    "Vehicle Financing": "parcela de financiamento: dívida, não gasto do mês",
    "Student loan": "parcela de financiamento: dívida, não gasto do mês",
    "Investments": "aplicação é dinheiro mudando de lugar, não gasto",
    "Automatic investment": "aplicação é dinheiro mudando de lugar, não gasto",
    "Fixed income": "aplicação é dinheiro mudando de lugar, não gasto",
    "Mutual funds": "aplicação é dinheiro mudando de lugar, não gasto",
    "Variable income": "aplicação é dinheiro mudando de lugar, não gasto",
    "Margin": "aplicação é dinheiro mudando de lugar, não gasto",
    "Pension": "previdência: aplicação ou despesa, a decidir",
    "Legal obligations": "sem categoria equivalente na árvore",
    "Blocked balances": "sem categoria equivalente na árvore",
    "Alimony": "sem categoria equivalente na árvore",
    "Services": "genérica demais",
    "Digital services": "genérica: streaming, jogo ou software",
    "Wellness and fitness": "genérica: academia, esporte ou bem-estar",
    "Sports practice": "Academia ou Hobbies, a decidir",
    "Mileage programs": "sem categoria equivalente na árvore",
    "Car rental": "Viagem ou Transporte, a decidir",
}


def proposta_para(nome: str) -> tuple[str, tuple[str, ...] | str]:
    """O que a proposta diz sobre uma categoria da Pluggy, pelo nome.

    Devolve `("mapear", caminhos)`, `("ambigua", motivo)`,
    `("transferencia", motivo)` ou `("sem_proposta", "")`.
    """
    if e_transferencia_pluggy(None, nome):
        return "transferencia", "transferência: não recebe categoria de despesa (D-21)"
    if nome in PROPOSTA_INICIAL:
        return "mapear", PROPOSTA_INICIAL[nome]
    if nome in AMBIGUAS:
        return "ambigua", AMBIGUAS[nome]
    return "sem_proposta", ""


def categorias_por_caminho(session: Session) -> dict[str, Categoria]:
    """Categorias vivas e ativas por caminho normalizado ("ALIMENTACAO › MERCADO")."""
    from app.services.cadastros import normalizar_nome

    todas = list(
        session.scalars(
            select(Categoria)
            .where(Categoria.deleted_em.is_(None), Categoria.ativo.is_(True))
            .order_by(Categoria.id)
        )
    )
    por_id = {c.id: c for c in todas}
    caminhos: dict[str, Categoria] = {}
    for categoria in todas:
        pai = por_id.get(categoria.categoria_pai_id) if categoria.categoria_pai_id else None
        if categoria.categoria_pai_id is not None and pai is None:
            continue  # filha de categoria apagada ou inativa
        caminho = f"{pai.nome} › {categoria.nome}" if pai else categoria.nome
        caminhos.setdefault(normalizar_nome(caminho), categoria)
    return caminhos


def resolver_alvo(caminhos: dict[str, Categoria], alvos: tuple[str, ...]) -> Categoria | None:
    """O primeiro caminho da proposta que existe no banco."""
    from app.services.cadastros import normalizar_nome

    for alvo in alvos:
        categoria = caminhos.get(normalizar_nome(alvo))
        if categoria is not None:
            return categoria
    return None
