"""Testes que não tocam em banco.

Moram fora de `tests/` de propósito: o `conftest` de lá sobe um Postgres
(testcontainers) na importação, antes de qualquer teste, e isso exige Docker
até para um teste que só fala com um `httpx.MockTransport`. Aqui nada sobe —
`pytest tests_sem_banco` roda em qualquer máquina com Python.

O `make test` continua rodando as duas pastas (`testpaths` no pyproject).
"""
