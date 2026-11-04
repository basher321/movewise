-- 0008_notifications_sending: real sending of the outbox (email by SMTP, WhatsApp Cloud API).
--
-- The project rules forbid DROP in migrations, so the fixed CHECK lists of 0002 and 0003 are
-- not replaced:
-- - "sending" is not a new status value. A row being sent keeps status 'queued' and has
--   sending_since set; the API shows it as "sending".
-- - New secret names (the SMTP password, and later ones) live in app_secrets, whose names are
--   checked by format. settings_secrets keeps its rows; 'mail.api_key' is no longer used.

ALTER TABLE notifications
  ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN sending_since timestamptz,
  ADD COLUMN sent_at timestamptz,
  ADD COLUMN last_error text NOT NULL DEFAULT '' CHECK (length(last_error) <= 300),
  ADD COLUMN provider_message_id text;

CREATE INDEX notifications_status_next_attempt_idx ON notifications (status, next_attempt_at);

ALTER TABLE settings
  ADD COLUMN smtp_host text NOT NULL DEFAULT '',
  ADD COLUMN smtp_port integer NOT NULL DEFAULT 587 CHECK (smtp_port BETWEEN 1 AND 65535),
  ADD COLUMN smtp_security text NOT NULL DEFAULT 'starttls' CHECK (smtp_security IN ('starttls', 'ssl', 'none')),
  ADD COLUMN smtp_username text NOT NULL DEFAULT '',
  ADD COLUMN whatsapp_phone_number_id text NOT NULL DEFAULT '',
  ADD COLUMN whatsapp_template_name text NOT NULL DEFAULT '',
  ADD COLUMN whatsapp_template_language text NOT NULL DEFAULT 'en',
  ADD COLUMN whatsapp_api_version text NOT NULL DEFAULT 'v21.0' CHECK (whatsapp_api_version ~ '^v[0-9]{1,3}\.[0-9]{1,2}$');

-- Encrypted secrets added after 0002 (by backend/app/crypto.py). A row exists only once saved.
CREATE TABLE app_secrets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE CHECK (name ~ '^[a-z0-9_]+\.[a-z0-9_]+$'),
  ciphertext text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_app_secrets_updated_at BEFORE UPDATE ON app_secrets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
