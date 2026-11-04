# Regras para código que usa LLM

Valem para os agentes de ingestão e de insights. Violar qualquer uma é bug.

1. **LLM não calcula.** Toda soma, média e comparação sai de SQL agregado. O
   modelo apenas interpreta números que já vieram prontos.
2. **Saída de LLM é structured output validado com Pydantic.** Nada de parse
   de texto livre ou regex em resposta de modelo.
3. **Prompts moram em arquivos versionados** (`prompts/nome_vN.md`), nunca
   hardcoded. A versão usada é gravada na tabela `importacoes`.

Relacionadas: D-08 (parser antes do LLM), D-10 (tools, não text-to-SQL),
D-11 (role read-only de insights), D-12 (harness determinístico), D-13 (evals
com PDFs reais) — em docs/decisoes.md.
