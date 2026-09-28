-- Role read-only do agente de insights (D-11).
--
-- Garantia estrutural, não instrução de prompt: o agente da fase 6 não
-- consegue escrever porque a role não tem permissão, e não porque alguém
-- lembrou de pedir no prompt.
--
-- Roda em dois momentos, e precisa ser idempotente nos dois:
--   1. primeiro boot do volume do Postgres, pelo entrypoint do Docker —
--      as migrations ainda não passaram, daí o ALTER DEFAULT PRIVILEGES,
--      que alcança as tabelas que o Alembic criar depois;
--   2. a qualquer momento, por `make roles` / `scripts.aplicar_roles`, para
--      cluster que já existia antes desta fase (é o caso de quem subiu o
--      banco à mão, sem Docker: o entrypoint nunca rodou lá).
--
-- Quem executa precisa ser o dono das tabelas — o ALTER DEFAULT PRIVILEGES
-- sem `FOR ROLE` vale para os objetos criados por quem está rodando o script,
-- e é o mesmo papel que o Alembic usa nas migrations.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'casa_insights') THEN
    -- A senha real entra depois com ALTER ROLE; aqui só garantimos a
    -- existência da role, porque o entrypoint não expande variável de shell.
    CREATE ROLE casa_insights LOGIN PASSWORD 'trocar_no_primeiro_uso';
  END IF;
END
$$;

-- `current_database()` em vez do nome literal: o entrypoint do Docker cria o
-- banco a partir de POSTGRES_DB, e o nome do cluster local não é obrigado a
-- ser o mesmo. Nome fixo aqui falharia em silêncio no cluster errado.
--
-- `quote_ident` + concatenação em vez do `format()` com máscara de
-- identificador: este arquivo também é executado pelo driver psycopg, que
-- varre a query inteira atrás de placeholders e recusa qualquer sinal de
-- porcentagem que não seja dele. A varredura não pula comentário — o símbolo
-- não pode aparecer nem aqui, o que é a razão desta frase ser tão perifrástica.
DO $$
BEGIN
  EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database())
       || ' TO casa_insights';
END
$$;

GRANT USAGE ON SCHEMA public TO casa_insights;

-- Nada de INSERT/UPDATE/DELETE, agora e no futuro.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO casa_insights;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO casa_insights;
REVOKE CREATE ON SCHEMA public FROM casa_insights;
