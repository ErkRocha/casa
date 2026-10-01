"""Cliente da Pluggy (fase 5b, D-16).

Pacote isolado de propósito: não importa banco, models, services nem config.
Fala HTTP e devolve objetos tipados. Quem decide o que fazer com eles — e
grava no staging — é o service de sync, fora daqui.

Fica fora de `app.ingestao` também por causa da guarda da D-08
(`test_pdf_nunca_sai_da_maquina`): o pacote de ingestão não pode ter cliente
HTTP, e a sync é o primeiro código do sistema que fala com a internet — só
saída, só leitura.
"""

from app.pluggy.cliente import URL_PADRAO, PluggyCliente, RespostaBruta
from app.pluggy.erros import (
    PluggyAutenticacaoErro,
    PluggyErro,
    PluggyFormatoErro,
    PluggyLimiteErro,
    PluggyRedeErro,
    PluggyRespostaErro,
)
from app.pluggy.modelos import (
    Conector,
    Conta,
    DadosBancarios,
    DadosCredito,
    Fatura,
    Item,
    MetadadosCartao,
    Transacao,
)

__all__ = [
    "URL_PADRAO",
    "Conector",
    "Conta",
    "DadosBancarios",
    "DadosCredito",
    "Fatura",
    "Item",
    "MetadadosCartao",
    "PluggyAutenticacaoErro",
    "PluggyCliente",
    "PluggyErro",
    "PluggyFormatoErro",
    "PluggyLimiteErro",
    "PluggyRedeErro",
    "PluggyRespostaErro",
    "RespostaBruta",
    "Transacao",
]
