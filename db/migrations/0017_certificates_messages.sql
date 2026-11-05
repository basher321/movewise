-- 0017_certificates_messages: completion letters for completed cases, email attachments for
-- certificates and letters, and staff messages to one client or a group (spec B20).
-- Only adds tables, columns, indexes and triggers. Nothing is dropped or deleted.

-- ---------------------------------------------------------------- completion letters

CREATE TABLE case_letters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  letter_id text NOT NULL UNIQUE CHECK (letter_id ~ '^LTR-[A-HJ-NP-Z2-9]{8}$'),
  application_id uuid NOT NULL UNIQUE REFERENCES applications (id) ON DELETE RESTRICT,
  issued_by uuid NOT NULL REFERENCES admin_users (id) ON DELETE RESTRICT,
  issued_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX case_letters_issued_by_idx ON case_letters (issued_by);

-- A letter is never changed or deleted. Whether it is valid is computed from its case.
CREATE TRIGGER trg_case_letters_block_change BEFORE UPDATE ON case_letters
  FOR EACH ROW EXECUTE FUNCTION block_change();
CREATE TRIGGER trg_case_letters_block_delete BEFORE DELETE ON case_letters
  FOR EACH ROW EXECUTE FUNCTION block_delete();

-- ---------------------------------------------------------------- message batches

CREATE TABLE message_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module text NOT NULL CHECK (module IN ('course', 'study', 'job', 'visa')),
  filters jsonb NOT NULL CHECK (jsonb_typeof(filters) = 'object'),
  channels text[] NOT NULL CHECK (channels <@ ARRAY['email', 'whatsapp']::text[] AND cardinality(channels) > 0),
  subject text NOT NULL CHECK (btrim(subject) <> '' AND length(subject) <= 200),
  body text NOT NULL CHECK (btrim(body) <> '' AND length(body) <= 5000),
  recipients integer NOT NULL CHECK (recipients >= 0),
  sent_by uuid NOT NULL REFERENCES admin_users (id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX message_batches_sent_by_idx ON message_batches (sent_by);

CREATE TRIGGER trg_message_batches_block_change BEFORE UPDATE ON message_batches
  FOR EACH ROW EXECUTE FUNCTION block_change();
CREATE TRIGGER trg_message_batches_block_delete BEFORE DELETE ON message_batches
  FOR EACH ROW EXECUTE FUNCTION block_delete();

-- ---------------------------------------------------------------- notifications

-- The PDF is built when the email is sent, from attachment_kind + attachment_ref (the CERT- or
-- LTR- id); it is never stored.
ALTER TABLE notifications
  ADD COLUMN attachment_kind text CHECK (attachment_kind IN ('certificate', 'letter')),
  ADD COLUMN attachment_ref text,
  ADD COLUMN sent_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  ADD COLUMN batch_id uuid REFERENCES message_batches (id) ON DELETE RESTRICT,
  ADD CONSTRAINT notifications_attachment_pair CHECK ((attachment_kind IS NULL) = (attachment_ref IS NULL));

CREATE INDEX notifications_sent_by_idx ON notifications (sent_by);
CREATE INDEX notifications_batch_id_idx ON notifications (batch_id);
