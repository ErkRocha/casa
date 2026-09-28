"""O código determinístico em volta do modelo (D-12).

O modelo é uma peça no meio de código comum e testável, não o centro do
sistema. Este módulo cuida das quatro garantias da D-12:

* saída validada com Pydantic — resposta inválida volta com o erro anexo,
  até `insights_tentativas_max` tentativas (regra 8);
* prompt em arquivo versionado, com a versão gravada junto do resultado
  (regra 9);
* telemetria estruturada por execução: backend, modelo, tentativas, duração;
* fronteira explícita — o que sai daqui já é um objeto validado, nunca texto
  solto para alguém parsear depois.

Dois backends. `claude_code` chama o CLI local e usa a assinatura, sem chave
de API; `api` usa o SDK da Anthropic. A escolha é de configuração, e o resto
do sistema não sabe qual está em uso.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import get_settings

PROMPTS = Path(__file__).resolve().parent / "prompts"

#: O modelo às vezes devolve o JSON dentro de uma cerca de markdown, mesmo
#: sendo instruído a não fazer isso — e a instrução não é garantia, então a
#: cerca é removida aqui em vez de virar tentativa desperdiçada. Observado com
#: o CLI rodando dentro de um projeto: o contexto do diretório empurra o
#: modelo para o hábito de formatar código.
_CERCA = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

#: O CLI espera dado em stdin e demora 3s desistindo quando não vem. Fechar a
#: entrada explicitamente economiza esse tempo em toda execução.
_SEM_ENTRADA = subprocess.DEVNULL


class FalhaDoModelo(RuntimeError):
    """O modelo não devolveu saída válida dentro do limite de tentativas."""


class BackendIndisponivel(RuntimeError):
    """O backend configurado não está utilizável nesta máquina."""


@dataclass
class Execucao:
    """Telemetria de uma geração. Vai para `relatorios.execucao` (D-12)."""

    backend: str
    modelo: str
    prompt_versao: str
    tentativas: int = 0
    duracao_ms: int = 0
    #: Custo equivalente em USD que o CLI reporta. Sob assinatura não é
    #: cobrança — é a régua para decidir se vale migrar para a API.
    custo_equivalente_usd: float | None = None
    erros: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "modelo": self.modelo,
            "prompt_versao": self.prompt_versao,
            "tentativas": self.tentativas,
            "duracao_ms": self.duracao_ms,
            "custo_equivalente_usd": self.custo_equivalente_usd,
            "erros": self.erros,
        }


def carregar_prompt(versao: str, substituicoes: dict[str, str]) -> str:
    """Lê `prompts/<versao>.md` e troca os marcadores.

    `str.replace` e não `str.format`: o prompt contém blocos JSON, e chaves
    literais fariam o `format` estourar ou, pior, consumir parte do conteúdo.
    """
    caminho = PROMPTS / f"{versao}.md"
    if not caminho.exists():
        raise FileNotFoundError(f"prompt não encontrado: {caminho}")

    texto = caminho.read_text(encoding="utf-8")
    for marcador, valor in substituicoes.items():
        texto = texto.replace("{{" + marcador + "}}", valor)
    return texto


def _limpar(bruto: str) -> str:
    encontrado = _CERCA.match(bruto)
    return encontrado.group(1) if encontrado else bruto.strip()


def _chamar_claude_code(prompt: str, modelo: str, timeout: int) -> tuple[str, float | None]:
    """Roda o CLI local do Claude Code em modo headless.

    `--system-prompt` substitui o system prompt do Claude Code inteiro. Sem
    isso o modelo entra no papel de agente de codificação — com ferramentas de
    arquivo, hábito de explorar o diretório e um preâmbulo de milhares de
    tokens que não tem nada a ver com fechar o mês da casa.

    O `cwd` é o diretório dos prompts, e não o repositório: rodando na raiz o
    CLI carrega o `CLAUDE.md` do projeto, que fala de migrations e de ruff.
    """
    sistema = (
        "Você redige o fechamento mensal de finanças domésticas a partir de "
        "números já calculados. Você não calcula nada e não usa ferramentas. "
        "Sua resposta é um único objeto JSON, sem cerca de markdown."
    )
    comando = [
        "claude",
        "-p",
        prompt,
        "--system-prompt",
        sistema,
        "--model",
        modelo,
        "--output-format",
        "json",
    ]

    try:
        # Lista de argumentos, sem `shell=True`: o prompt vai como argv e
        # nada nele é interpretado pelo shell.
        concluido = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            stdin=_SEM_ENTRADA,
            cwd=PROMPTS,
        )
    except FileNotFoundError as erro:
        raise BackendIndisponivel(
            "`claude` não está no PATH. Instale o Claude Code ou rode com "
            "`--sem-ia` para gerar o relatório apenas com os números."
        ) from erro
    except subprocess.TimeoutExpired as erro:
        raise FalhaDoModelo(f"o CLI não respondeu em {timeout}s") from erro

    if concluido.returncode != 0:
        raise FalhaDoModelo(f"CLI saiu com código {concluido.returncode}: {concluido.stderr[:500]}")

    try:
        envelope = json.loads(concluido.stdout)
    except json.JSONDecodeError as erro:
        raise FalhaDoModelo(f"o CLI não devolveu JSON: {concluido.stdout[:300]}") from erro

    if envelope.get("is_error"):
        raise FalhaDoModelo(f"o CLI reportou erro: {envelope.get('result', '')[:300]}")

    return str(envelope.get("result", "")), envelope.get("total_cost_usd")


def _chamar_api(prompt: str, modelo: str, timeout: int) -> tuple[str, float | None]:
    """Chama a API da Anthropic. Só entra em uso com `INSIGHTS_BACKEND=api`.

    Import adiado de propósito: o pacote `anthropic` é dependência opcional, e
    quem roda pelo CLI não deve ser obrigado a instalá-lo.
    """
    try:
        import anthropic
    except ImportError as erro:
        raise BackendIndisponivel(
            "backend `api` exige o pacote `anthropic` (pip install anthropic) "
            "e a variável ANTHROPIC_API_KEY."
        ) from erro

    cliente = anthropic.Anthropic(timeout=timeout)
    resposta = cliente.messages.create(
        model=modelo,
        max_tokens=4096,
        system=(
            "Você redige o fechamento mensal de finanças domésticas a partir de "
            "números já calculados. Você não calcula nada. Sua resposta é um "
            "único objeto JSON, sem cerca de markdown."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    # `stop_reason` antes de `content`: numa recusa o content vem vazio, e
    # indexar `content[0]` estouraria com IndexError em vez de dizer o motivo.
    if resposta.stop_reason == "refusal":
        raise FalhaDoModelo("a API recusou a requisição (stop_reason=refusal)")

    texto = next((bloco.text for bloco in resposta.content if bloco.type == "text"), "")
    return texto, None


def gerar_validado[T: BaseModel](
    prompt: str,
    esquema: type[T],
    execucao: Execucao,
    timeout: int = 180,
) -> T:
    """Chama o modelo até a saída validar contra `esquema`, ou desiste.

    A tentativa seguinte leva o erro de validação anexado. É o que transforma
    "o modelo errou o formato" de falha em correção: na prática ele acerta na
    segunda quando a primeira falhou por um campo faltando.
    """
    cfg = get_settings()
    chamar = _chamar_claude_code if execucao.backend == "claude_code" else _chamar_api

    inicio = time.monotonic()
    pedido = prompt
    ultimo_erro = ""

    try:
        for tentativa in range(1, cfg.insights_tentativas_max + 1):
            execucao.tentativas = tentativa
            bruto, custo = chamar(pedido, execucao.modelo, timeout)
            if custo is not None:
                execucao.custo_equivalente_usd = round(
                    (execucao.custo_equivalente_usd or 0.0) + custo, 6
                )

            try:
                return esquema.model_validate_json(_limpar(bruto))
            except (ValidationError, ValueError) as erro:
                ultimo_erro = str(erro)[:600]
                execucao.erros.append(f"tentativa {tentativa}: {ultimo_erro}")
                pedido = (
                    f"{prompt}\n\n---\n\n"
                    "Sua resposta anterior não validou contra o esquema pedido. "
                    f"Erro:\n\n{ultimo_erro}\n\n"
                    "Responda de novo, apenas com o JSON corrigido."
                )
    finally:
        execucao.duracao_ms = int((time.monotonic() - inicio) * 1000)

    raise FalhaDoModelo(
        f"saída inválida em {cfg.insights_tentativas_max} tentativas. Último erro: {ultimo_erro}"
    )
