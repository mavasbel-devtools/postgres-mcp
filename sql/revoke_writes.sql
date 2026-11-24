-- revoke_writes.sql — close the write exercise on one table.
--
-- Usage: see grant_writes.sql. Takes the same two psql variables (role,
-- table) with the same bare-or-qualified table form.
--
-- Revokes exactly what the grant gave — INSERT, UPDATE, DELETE on that
-- one table — and restores default_transaction_read_only = on, so the
-- role is read-only again. Idempotent: re-running a revoke over an
-- already revoked table is only a WARNING, exit stays 0.
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
    'REVOKE INSERT, UPDATE, DELETE ON TABLE %s FROM %I',
    current_setting('myvars.target'),
    current_setting('myvars.role')
  );
END
$$;

RESET myvars.target;

ALTER ROLE :"role" SET default_transaction_read_only = on;

RESET myvars.role;
