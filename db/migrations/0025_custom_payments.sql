-- 0025_custom_payments: custom payments of any amount on a case or course enrolment, spec B27.
-- A payment request is either asked for by staff ('requested') or started by the applicant
-- with an amount of their own ('own'). Its payment is a normal payment with ref_type 'request'.
--
-- The owner allowed the DROP CONSTRAINT statement below (2026-11-20, spec B27 Decisions 1).
-- It removes the old ref_type CHECK rule and at once adds a wider rule that also allows
-- 'request'. No table, column, index or row is removed.

CREATE TABLE payment_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ref text NOT NULL UNIQUE CHECK (ref ~ '^PR-[A-Z0-9]{6}$'),
  module text NOT NULL CHECK (module IN ('course', 'study', 'job', 'visa', 'remote')),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  application_id uuid REFERENCES applications (id) ON DELETE RESTRICT,
  enrolment_id uuid REFERENCES enrolments (id) ON DELETE RESTRICT,
  kind text NOT NULL CHECK (kind IN ('requested', 'own')),
  description text NOT NULL CHECK (btrim(description) <> '' AND char_length(description) <= 200),
  amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'paid', 'cancelled')),
  created_by_kind text NOT NULL CHECK (created_by_kind IN ('staff', 'applicant')),
  created_by_admin uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  cancelled_at timestamptz,
  paid_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payment_requests_one_case CHECK (
    (module = 'course' AND enrolment_id IS NOT NULL AND application_id IS NULL)
    OR (module <> 'course' AND application_id IS NOT NULL AND enrolment_id IS NULL)
  ),
  CONSTRAINT payment_requests_staff_by CHECK (created_by_kind = 'staff' OR created_by_admin IS NULL)
);

CREATE INDEX payment_requests_applicant_id_idx ON payment_requests (applicant_id, created_at);
CREATE INDEX payment_requests_application_id_idx ON payment_requests (application_id);
CREATE INDEX payment_requests_enrolment_id_idx ON payment_requests (enrolment_id);
CREATE INDEX payment_requests_created_by_admin_idx ON payment_requests (created_by_admin);

CREATE TRIGGER trg_payment_requests_updated_at BEFORE UPDATE ON payment_requests
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE payments DROP CONSTRAINT payments_ref_type_check;
ALTER TABLE payments
  ADD CONSTRAINT payments_ref_type_check CHECK (ref_type IN ('application', 'enrolment', 'request'));
