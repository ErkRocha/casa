---
name: nova-decisao
description: Registra uma decisão de arquitetura em docs/decisoes.md (próximo D-xx) e propaga para CLAUDE.md, docs/ecossistema.md ou docs/llm.md. Use quando o usuário decidir uma regra nova, ou quando uma tarefa exigir exceção a uma regra inviolável; gatilhos: "decidi que", "nova decisão", "exceção à regra".
---

1. Leia só o `## Índice` e as 2 últimas decisões de docs/decisoes.md para pegar o formato. Não leia o arquivo todo (`grep -n "## D-" docs/decisoes.md` ajuda).
2. Próximo ID = último D-xx + 1, com dois dígitos.
3. Acrescente a seção no fim do arquivo, no formato das últimas: `## D-xx — título`, linha `Decisão do usuário, DD/MM/AAAA.` e o texto com o porquê (não só o quê), consequências e o que fica de fora.
4. Acrescente a linha no `## Índice`, no formato `- D-xx — título`.
5. Propague, conforme o caso:
   - muda ou abre exceção a uma regra do CLAUDE.md: atualize CLAUDE.md (e o intervalo `D-01..D-xx` no topo);
   - muda container, porta, rota ou integração: atualize docs/ecossistema.md;
   - muda regra de LLM (ingestão, insights): atualize docs/llm.md.
6. Se a decisão pede mudança de schema, siga também a skill migracao-banco; se pede serviço novo, a skill novo-servico-compose.
7. Faça o commit `docs: D-xx <título curto>`.
