-- 0009_enrolments_enquiries: course enrolments and certificates, enquiries and their notes,
-- and the public rate-limit log.

CREATE TABLE enrolments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_no text NOT NULL UNIQUE CHECK (order_no ~ '^ORD-[A-HJ-NP-Z2-9]{6}$'),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  course_id uuid NOT NULL REFERENCES courses (id) ON DELETE RESTRICT,
  price_poisha bigint NOT NULL CHECK (price_poisha > 0),
  status text NOT NULL DEFAULT 'awaiting_payment'
    CHECK (status IN ('awaiting_payment', 'active', 'completed', 'cancelled')),
  certificate_id text UNIQUE CHECK (certificate_id ~ '^CERT-[A-HJ-NP-Z2-9]{8}$'),
  certificate_approved boolean NOT NULL DEFAULT false,
  certificate_approved_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  certificate_approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX enrolments_applicant_id_idx ON enrolments (applicant_id);
CREATE INDEX enrolments_course_id_idx ON enrolments (course_id);
CREATE INDEX enrolments_status_idx ON enrolments (status);
CREATE INDEX enrolments_certificate_approved_by_idx ON enrolments (certificate_approved_by);
CREATE UNIQUE INDEX enrolments_one_per_course_idx ON enrolments (applicant_id, course_id)
  WHERE status <> 'cancelled';

CREATE TRIGGER trg_enrolments_updated_at BEFORE UPDATE ON enrolments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_enrolments_block_delete BEFORE DELETE ON enrolments
  FOR EACH ROW EXECUTE FUNCTION block_delete();

CREATE TABLE enquiries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
  contact text NOT NULL CHECK (btrim(contact) <> ''),
  interest text NOT NULL CHECK (interest IN ('course', 'study', 'job', 'other')),
  preferred_date date,
  message text NOT NULL DEFAULT '' CHECK (length(message) <= 2000),
  status text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'converted', 'closed')),
  assigned_to uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  ip text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX enquiries_status_idx ON enquiries (status, created_at);
CREATE INDEX enquiries_assigned_to_idx ON enquiries (assigned_to);
CREATE INDEX enquiries_ip_created_at_idx ON enquiries (ip, created_at);

CREATE TRIGGER trg_enquiries_updated_at BEFORE UPDATE ON enquiries
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_enquiries_block_delete BEFORE DELETE ON enquiries
  FOR EACH ROW EXECUTE FUNCTION block_delete();

-- by_id is the admin who wrote the note (admin_users).
CREATE TABLE enquiry_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  enquiry_id uuid NOT NULL REFERENCES enquiries (id) ON DELETE RESTRICT,
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  by_id uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  by_name text NOT NULL,
  text text NOT NULL CHECK (btrim(text) <> ''),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX enquiry_notes_enquiry_id_idx ON enquiry_notes (enquiry_id, at);
CREATE INDEX enquiry_notes_by_id_idx ON enquiry_notes (by_id);

CREATE TRIGGER trg_enquiry_notes_block_change BEFORE UPDATE OR DELETE ON enquiry_notes
  FOR EACH ROW EXECUTE FUNCTION block_change();

-- Public requests counted for rate limits (certificate checks). Old rows are ignored, not deleted.
CREATE TABLE rate_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('certificate_check')),
  ip text NOT NULL,
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX rate_events_kind_ip_at_idx ON rate_events (kind, ip, at);
