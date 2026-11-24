-- create_readonly_role.sql — create (or refresh) a revoked read-only role.
--
-- Usage:
--   psql -v role=curso_mcp -v password='<secret>' -v schema=public \
--     -f sql/create_readonly_role.sql
--
-- Idempotent: safe to re-run. A re-run resets the password, the flags,
-- the grants and the settings below. Takes three psql variables:
--   role      the role to create    (:"role" — identifier)
--   password  its LOGIN password    (:'password' — quoted literal)
--   schema    the data schema       (:"schema" — identifier, usually public)
--
-- The role gets: LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE; CONNECT on the
-- current database; USAGE on the schema; SELECT on all its tables, present
-- and future (ALTER DEFAULT PRIVILEGES); and no CREATE on the schema.
--
-- The role keeps: default_transaction_read_only = on and
-- statement_timeout = 15s. The 15s matches the executor constant
-- TIMEOUT_MS = 15000; the role setting is the backstop for direct psql
-- sessions, which bypass the executor.
--
-- The role never gets: membership in pg_read_server_files,
-- pg_write_server_files, pg_execute_server_program or pg_signal_backend
-- (plain REVOKEs — a missing membership is only a WARNING, exit stays 0),
-- and no EXECUTE on the dangerous functions the step-1.4 spike proved
-- callable from inside a read-only session (set_config,
-- pg_terminate_backend, pg_cancel_backend, pg_sleep, the
-- pg_read_*/pg_ls_dir/pg_stat_file file readers and the lo_* large-object
-- writers). The loop only touches functions that exist, so it survives
-- version drift. Functions granted to PUBLIC cannot be fenced by a
-- per-role REVOKE — those stay fenced by the classifier denylist
-- (defence in depth); the REVOKEs below remove any direct grant,
-- whatever the server defaults are.
--
-- Plumbing note: psql does not expand :'vars' inside $$ dollar-quoted
-- bodies, so the values cross into the DO blocks through session
-- settings (reset at the end). Plain statements use :"role"/:"schema"
-- directly.

SET myvars.role TO :'role';
SET myvars.password TO :'password';

DO
$$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = current_setting('myvars.role')
  ) THEN
    EXECUTE format(
      'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
      current_setting('myvars.role'),
      current_setting('myvars.password')
    );
  ELSE
    EXECUTE format(
      'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
      current_setting('myvars.role'),
      current_setting('myvars.password')
    );
  END IF;
END
$$;

RESET myvars.password;

DO
$$
BEGIN
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    current_setting('myvars.role')
  );
END
$$;

GRANT USAGE ON SCHEMA :"schema" TO :"role";
GRANT SELECT ON ALL TABLES IN SCHEMA :"schema" TO :"role";
ALTER DEFAULT PRIVILEGES IN SCHEMA :"schema" GRANT SELECT ON TABLES TO :"role";
REVOKE CREATE ON SCHEMA :"schema" FROM :"role";

ALTER ROLE :"role" SET default_transaction_read_only = on;
ALTER ROLE :"role" SET statement_timeout = '15s';

REVOKE pg_read_server_files FROM :"role";
REVOKE pg_write_server_files FROM :"role";
REVOKE pg_execute_server_program FROM :"role";
REVOKE pg_signal_backend FROM :"role";

DO
$$
DECLARE
  func text;
BEGIN
  FOR func IN
    SELECT p.oid::regprocedure::text
    FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'pg_catalog'
      AND p.proname IN (
        'pg_read_file', 'pg_read_binary_file', 'pg_ls_dir', 'pg_stat_file',
        'set_config', 'pg_terminate_backend', 'pg_cancel_backend',
        'pg_reload_conf', 'pg_rotate_logfile', 'pg_sleep',
        'lo_creat', 'lo_create', 'lo_import', 'lo_export', 'lo_unlink'
      )
  LOOP
    EXECUTE format(
      'REVOKE EXECUTE ON FUNCTION %s FROM %I',
      func,
      current_setting('myvars.role')
    );
  END LOOP;
END
$$;

RESET myvars.role;
