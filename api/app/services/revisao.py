"""O que está esperando decisão na revisão, por motivo (D-21, D-22).

Desde a D-21 a sync promove sozinha o item limpo; o que fica no staging tem
um motivo. Aqui ele é deduzido do próprio item, no banco, na mesma ordem de
`promocao_pluggy.MOTIVOS` — o primeiro que se aplica é o do item. A leitura
crua da Pluggy (a confiança da conversão) não fica no staging, então o
motivo "confiança" não tem como ser reconhecido aqui: item pendente sem
nenhum dos outros motivos aparece como "outros" (PDF, por exemplo).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_PAGAMENTO_NO_CARTAO
from app.schemas.revisar import MotivoRevisao, RevisarResumo
from app.services.promocao_pluggy import MARCA_DUPLICATA, MOTIVOS

#: Os motivos que a revisão reconhece, na ordem de leitura e de checagem.
MOTIVOS_REVISAO: dict[str, str] = {
    "possivel_duplicata": MOTIVOS["possivel_duplicata"],
    "encargos": MOTIVOS["encargos"],
    "pagamento_fatura_cartao": MOTIVOS["pagamento_fatura_cartao"],
    "transferencia": MOTIVOS["transferencia"],
    "observacao": MOTIVOS["observacao"],
    "sem_categoria": MOTIVOS["sem_categoria"],
    "outros": "outros",
}

#: Classificação de um item de `importacao_itens` (alias `i`). Fragmento
#: reaproveitado pela listagem da revisão.
MOTIVO_SQL = """
    CASE
      WHEN strpos(coalesce(i.observacao, ''), :marca_duplicata) > 0 THEN 'possivel_duplicata'
      WHEN i.id_externo LIKE 'bill:%' THEN 'encargos'
      WHEN i.tipo_sugerido = 'transferencia'
        AND strpos(coalesce(i.observacao, ''), :marca_cartao) > 0 THEN 'pagamento_fatura_cartao'
      WHEN i.tipo_sugerido = 'transferencia' THEN 'transferencia'
      WHEN coalesce(i.observacao, '') <> '' THEN 'observacao'
      WHEN i.categoria_sugerida_id IS NULL THEN 'sem_categoria'
      ELSE 'outros'
    END
"""

#: Pendente, vivo e de importação viva.
PENDENTES_SQL = """
    FROM importacao_itens i
    JOIN importacoes imp ON imp.id = i.importacao_id AND imp.deleted_em IS NULL
    WHERE i.status = 'pendente' AND i.deleted_em IS NULL
"""

_RESUMO = f"""
    SELECT {MOTIVO_SQL} AS motivo, count(*) AS quantidade
    {PENDENTES_SQL}
    GROUP BY 1
"""


def parametros_motivo() -> dict[str, str]:
    return {"marca_duplicata": MARCA_DUPLICATA, "marca_cartao": OBS_PAGAMENTO_NO_CARTAO}


class RevisaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resumo(self) -> RevisarResumo:
        contagem = {
            linha.motivo: int(linha.quantidade)
            for linha in self.session.execute(text(_RESUMO), parametros_motivo())
        }
        motivos = [
            MotivoRevisao(motivo=chave, rotulo=rotulo, quantidade=contagem[chave])
            for chave, rotulo in MOTIVOS_REVISAO.items()
            if contagem.get(chave)
        ]
        return RevisarResumo(total=sum(m.quantidade for m in motivos), motivos=motivos)
