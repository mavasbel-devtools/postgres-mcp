-- grant_writes.sql — open one write exercise on one table.
--
-- Usage:
--   psql -v role=curso_mcp -v table=public.cuenta_p07 \
--     -f sql/grant_writes.sql
--   ... exercise ...
--   psql -v role=curso_mcp -v table=public.cuenta_p07 \
--     -f sql/revoke_writes.sql
--
-- Takes two psql variables: role (:"role" — identifier) and table
-- (:'table' — quoted literal spliced as a table reference, so both bare
-- names like pgmcp_live_scratch and qualified names like
-- public.cuenta_p07 work).
--
-- Scoped to INSERT, UPDATE, DELETE on that one table: SELECT grants are
-- untouched, so the paired revoke never blinds reads. Toggling: this
-- script sets default_transaction_read_only = off so the exercise can
-- run; revoke_writes.sql restores it to on.
--
-- Plumbing note: psql does not expand :'vars' inside $$ dollar-quoted
-- bodies, so the values cross into the DO block through session settings
-- (reset at the end).

SET myvars.role TO :'role';
SET myvars.target TO :'table';

DO
$$
BEGIN
  EXECUTE format(
    'GRANT INSERT, UPDATE, DELETE ON TABLE %s TO %I',
    current_setting('myvars.target'),
    current_setting('myvars.role')
  );
END
$$;

RESET myvars.target;

ALTER ROLE :"role" SET default_transaction_read_only = off;

RESET myvars.role;
