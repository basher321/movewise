-- 0012_password_resets (B15): one-time "Forgot password?" links sent by email.
-- Only the sha256 of the link token is stored, never the token. A link works once, for 30
-- minutes. Rows are never deleted; used and expired rows are simply ignored.

CREATE TABLE password_resets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('admin', 'course', 'study', 'job')),
  admin_id uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  applicant_id uuid REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  token_hash bytea NOT NULL UNIQUE CHECK (length(token_hash) = 32),
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  ip text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((admin_id IS NULL) <> (applicant_id IS NULL)),
  CHECK ((kind = 'admin') = (admin_id IS NOT NULL))
);

CREATE INDEX password_resets_admin_id_idx ON password_resets (admin_id);
CREATE INDEX password_resets_applicant_id_idx ON password_resets (applicant_id);
CREATE INDEX password_resets_created_at_idx ON password_resets (created_at);

CREATE TRIGGER trg_password_resets_updated_at BEFORE UPDATE ON password_resets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
