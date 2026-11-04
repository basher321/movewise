-- B12: privileges of the limited application role movewise_app (created by hand, Step 0).
-- SELECT, INSERT, UPDATE on every table, USAGE on sequences, DELETE only on sessions, and the
-- same defaults for tables and sequences made by later migrations (which run as the owner
-- account). Everything else is revoked. Without the role this only prints a notice, so test
-- databases still migrate. Running it again changes nothing.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'movewise_app') THEN
    RAISE NOTICE 'Role movewise_app does not exist; no privileges were changed.';
    RETURN;
  END IF;

  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM movewise_app;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM movewise_app;
  REVOKE CREATE ON SCHEMA public FROM movewise_app;

  GRANT USAGE ON SCHEMA public TO movewise_app;
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO movewise_app;
  GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO movewise_app;
  GRANT DELETE ON sessions TO movewise_app;

  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO movewise_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO movewise_app;
END
$$;
