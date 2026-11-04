-- 0003_accounts: admin and applicant accounts, sessions, email codes, sign-in failures
-- and the notification outbox.

-- Admins. Nobody is ever deleted; deactivating sets active = false.
CREATE TABLE admin_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (btrim(name) <> ''),
  email text NOT NULL CHECK (btrim(email) <> ''),
  password_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('super_admin', 'admin', 'finance')),
  approved boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  sections text[] NOT NULL DEFAULT '{}'
    CHECK (sections <@ ARRAY['course', 'study', 'job']::text[]),
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX admin_users_email_key ON admin_users (lower(email));

CREATE TRIGGER trg_admin_users_updated_at BEFORE UPDATE ON admin_users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Applicants: one account per module and email.
CREATE TABLE applicant_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_id text NOT NULL UNIQUE CHECK (public_id ~ '^(CRS|STU|JOB)-[A-HJ-NP-Z2-9]{6}$'),
  module text NOT NULL CHECK (module IN ('course', 'study', 'job')),
  name text NOT NULL CHECK (btrim(name) <> ''),
  email text NOT NULL CHECK (btrim(email) <> ''),
  phone text NOT NULL DEFAULT '',
  country text NOT NULL DEFAULT '',
  education text NOT NULL DEFAULT '',
  password_hash text NOT NULL,
  email_verified boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT applicant_accounts_prefix CHECK (
    (module = 'course' AND public_id LIKE 'CRS-%')
    OR (module = 'study' AND public_id LIKE 'STU-%')
    OR (module = 'job' AND public_id LIKE 'JOB-%')
  )
);

CREATE UNIQUE INDEX applicant_accounts_module_email_key ON applicant_accounts (module, lower(email));

CREATE TRIGGER trg_applicant_accounts_updated_at BEFORE UPDATE ON applicant_accounts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Sign-in sessions. Only the sha256 of the cookie token is stored, never the token.
-- Rows are deleted on sign-out.
CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash bytea NOT NULL UNIQUE CHECK (length(token_hash) = 32),
  kind text NOT NULL CHECK (kind IN ('admin', 'applicant')),
  admin_id uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  applicant_id uuid REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  module text CHECK (module IN ('course', 'study', 'job')),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  ip text,
  user_agent text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sessions_one_owner CHECK (
    (kind = 'admin' AND admin_id IS NOT NULL AND applicant_id IS NULL AND module IS NULL)
    OR (kind = 'applicant' AND applicant_id IS NOT NULL AND admin_id IS NULL AND module IS NOT NULL)
  )
);

CREATE INDEX sessions_admin_id_idx ON sessions (admin_id);
CREATE INDEX sessions_applicant_id_idx ON sessions (applicant_id);

CREATE TRIGGER trg_sessions_updated_at BEFORE UPDATE ON sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Email verification and password reset codes, stored only as a keyed hash.
-- Codes are marked used, never deleted. At most one unused code per account and purpose.
CREATE TABLE email_codes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  purpose text NOT NULL CHECK (purpose IN ('verify', 'reset')),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  code_hash bytea NOT NULL,
  expires_at timestamptz NOT NULL,
  tries integer NOT NULL DEFAULT 0 CHECK (tries >= 0),
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX email_codes_applicant_id_idx ON email_codes (applicant_id);
CREATE UNIQUE INDEX email_codes_one_live_idx ON email_codes (applicant_id, purpose) WHERE used_at IS NULL;

CREATE TRIGGER trg_email_codes_updated_at BEFORE UPDATE ON email_codes
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Failed sign-ins, for rate limiting. Old rows are ignored, not deleted.
-- kind is 'admin' or the applicant's module.
CREATE TABLE signin_failures (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('admin', 'course', 'study', 'job')),
  ip text,
  at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX signin_failures_email_kind_at_idx ON signin_failures (email, kind, at);
CREATE INDEX signin_failures_ip_at_idx ON signin_failures (ip, at);

-- Notification outbox. Rows wait as 'queued' until sending arrives in a later step.
-- to_address is the "to" field of the API ("to" is a reserved word in SQL).
CREATE TABLE notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  at timestamptz NOT NULL DEFAULT now(),
  channel text NOT NULL CHECK (channel IN ('email', 'whatsapp')),
  to_address text NOT NULL,
  to_name text NOT NULL DEFAULT '',
  module text CHECK (module IN ('course', 'study', 'job')),
  event text NOT NULL,
  subject text NOT NULL DEFAULT '',
  body text NOT NULL,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed')),
  tries integer NOT NULL DEFAULT 0 CHECK (tries >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX notifications_at_idx ON notifications (at);
CREATE INDEX notifications_status_idx ON notifications (status);

CREATE TRIGGER trg_notifications_updated_at BEFORE UPDATE ON notifications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The foreign key 0002 left for when the users table exists.
ALTER TABLE licence
  ADD CONSTRAINT licence_applied_by_fkey FOREIGN KEY (applied_by) REFERENCES admin_users (id) ON DELETE RESTRICT;

CREATE INDEX licence_applied_by_idx ON licence (applied_by);

-- audit_log.by_id stays without a foreign key: it holds either an admin_users id or an
-- applicant_accounts id, and one foreign key cannot point at two tables.
