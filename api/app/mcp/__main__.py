"""`python -m app.mcp`: o servidor MCP por stdio (D-20).

No stdio, a stdout é o canal do protocolo: qualquer `print` ou log ali
corrompe a conversa com o Claude Desktop. Todo log vai para a stderr, e isto
é configurado antes de importar o resto.
"""

import logging
import sys

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from app.mcp.servidor import criar_servidor  # noqa: E402


def main() -> None:
    criar_servidor().run("stdio")


if __name__ == "__main__":
    main()
