-- 0001_foundation: objects every later migration builds on.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Applied migrations, written by backend/app/db/migrate.py.
CREATE TABLE schema_migrations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  filename text NOT NULL UNIQUE,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Keeps updated_at current. Pattern for every table that changes:
--   CREATE TRIGGER trg_<table>_updated_at BEFORE UPDATE ON <table>
--     FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- Append-only record of every data change.
-- by_id gets its foreign key when the users table exists.
CREATE TABLE audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  at timestamptz NOT NULL DEFAULT now(),
  by_id uuid,
  by_name text NOT NULL,
  by_role text CHECK (by_role IN ('super_admin', 'admin', 'finance', 'applicant')),
  action text NOT NULL,
  detail text NOT NULL,
  ip text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION audit_log_block_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_log rows can never be changed or deleted';
END;
$$;

CREATE TRIGGER trg_audit_log_block_change
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_block_change();
