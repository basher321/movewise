-- 0007_payments: payments, payment events, invoices, the ledger and refunds.
-- Money records are append-only: nothing here can be deleted, and ledger entries and payment
-- events can never be changed.

CREATE FUNCTION block_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% rows can never be deleted', TG_TABLE_NAME;
END;
$$;

CREATE FUNCTION block_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% rows can never be changed or deleted', TG_TABLE_NAME;
END;
$$;

CREATE TABLE payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  module text NOT NULL CHECK (module IN ('course', 'study', 'job')),
  ref_type text NOT NULL CHECK (ref_type IN ('application', 'enrolment')),
  ref_id uuid NOT NULL,
  purpose text NOT NULL CHECK (btrim(purpose) <> ''),
  amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
  currency text NOT NULL DEFAULT 'BDT' CHECK (currency = 'BDT'),
  method text NOT NULL CHECK (method IN ('sslcommerz', 'bkash', 'manual')),
  status text NOT NULL CHECK (status IN (
    'initiated', 'pending_verify', 'paid', 'failed', 'cancelled',
    'abandoned', 'rejected', 'refunded', 'duplicate'
  )),
  tran_id text NOT NULL UNIQUE CHECK (tran_id ~ '^[A-Za-z0-9-]{8,30}$'),
  -- bKash paymentID or SSLCommerz session key, to find the payment from a callback.
  gateway_session text,
  gateway_ref text,
  manual_ref text,
  payer_phone text NOT NULL DEFAULT '',
  verified_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  decision_note text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  paid_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX payments_applicant_id_idx ON payments (applicant_id);
CREATE INDEX payments_ref_idx ON payments (ref_type, ref_id);
CREATE INDEX payments_status_idx ON payments (status);
CREATE INDEX payments_verified_by_idx ON payments (verified_by);
CREATE UNIQUE INDEX payments_gateway_session_key ON payments (method, gateway_session)
  WHERE gateway_session IS NOT NULL;

-- Never charge twice: only one live payment per application or enrolment.
CREATE UNIQUE INDEX payments_one_live_idx ON payments (ref_type, ref_id)
  WHERE status IN ('initiated', 'pending_verify', 'paid');

CREATE TRIGGER trg_payments_updated_at BEFORE UPDATE ON payments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_payments_block_delete BEFORE DELETE ON payments
  FOR EACH ROW EXECUTE FUNCTION block_delete();

-- What happened to a payment, with gateway answers (secrets removed before saving).
CREATE TABLE payment_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_id uuid NOT NULL REFERENCES payments (id) ON DELETE RESTRICT,
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  kind text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX payment_events_payment_id_idx ON payment_events (payment_id, at);

CREATE TRIGGER trg_payment_events_block_change BEFORE UPDATE OR DELETE ON payment_events
  FOR EACH ROW EXECUTE FUNCTION block_change();

-- Gap-free invoice numbers per year.
CREATE TABLE invoice_counters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  year integer NOT NULL UNIQUE CHECK (year BETWEEN 2000 AND 9999),
  last_no integer NOT NULL CHECK (last_no >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_invoice_counters_updated_at BEFORE UPDATE ON invoice_counters
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Invoices keep a snapshot of the company details at issue time.
CREATE TABLE invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  no text NOT NULL UNIQUE,
  payment_id uuid NOT NULL UNIQUE REFERENCES payments (id) ON DELETE RESTRICT,
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  module text NOT NULL CHECK (module IN ('course', 'study', 'job')),
  name text NOT NULL,
  email text NOT NULL,
  description text NOT NULL,
  method text NOT NULL,
  amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
  issued_at timestamptz NOT NULL DEFAULT now(),
  company_name text NOT NULL,
  company_address text NOT NULL DEFAULT '',
  company_email text NOT NULL DEFAULT '',
  vat_bin text NOT NULL DEFAULT '',
  footer text NOT NULL DEFAULT '',
  refunded boolean NOT NULL DEFAULT false,
  refunded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX invoices_applicant_id_idx ON invoices (applicant_id);
CREATE INDEX invoices_module_idx ON invoices (module);

CREATE FUNCTION invoices_only_refund_changes() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (to_jsonb(NEW) - 'refunded' - 'refunded_at' - 'updated_at')
     IS DISTINCT FROM (to_jsonb(OLD) - 'refunded' - 'refunded_at' - 'updated_at') THEN
    RAISE EXCEPTION 'invoices can only be marked refunded';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invoices_only_refund BEFORE UPDATE ON invoices
  FOR EACH ROW EXECUTE FUNCTION invoices_only_refund_changes();
CREATE TRIGGER trg_invoices_updated_at BEFORE UPDATE ON invoices
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_invoices_block_delete BEFORE DELETE ON invoices
  FOR EACH ROW EXECUTE FUNCTION block_delete();

-- The ledger: append-only. A mistake is fixed by a reversing entry (reverses_id).
CREATE TABLE ledger_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ref text NOT NULL UNIQUE,
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  entry_date date NOT NULL,
  direction text NOT NULL CHECK (direction IN ('in', 'out')),
  category text NOT NULL CHECK (category IN (
    'course', 'study', 'job', 'otherin', 'opening',
    'salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'
  )),
  party text NOT NULL CHECK (btrim(party) <> ''),
  email text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  method text NOT NULL DEFAULT '',
  amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
  auto boolean NOT NULL,
  payment_id uuid REFERENCES payments (id) ON DELETE RESTRICT,
  reverses_id uuid UNIQUE REFERENCES ledger_entries (id) ON DELETE RESTRICT,
  created_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ledger_category_direction CHECK (
    (direction = 'in' AND category IN ('course', 'study', 'job', 'otherin', 'opening'))
    OR (direction = 'out' AND category IN ('salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'))
  )
);

CREATE INDEX ledger_entries_entry_date_idx ON ledger_entries (entry_date, at);
CREATE INDEX ledger_entries_payment_id_idx ON ledger_entries (payment_id);
CREATE INDEX ledger_entries_created_by_idx ON ledger_entries (created_by);

CREATE TRIGGER trg_ledger_entries_block_change BEFORE UPDATE OR DELETE ON ledger_entries
  FOR EACH ROW EXECUTE FUNCTION block_change();

CREATE TABLE refunds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- One refund per invoice. A duplicate payment has no invoice: its refund names the payment.
  invoice_no text UNIQUE REFERENCES invoices (no) ON DELETE RESTRICT,
  payment_id uuid NOT NULL UNIQUE REFERENCES payments (id) ON DELETE RESTRICT,
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
  reason text NOT NULL CHECK (btrim(reason) <> ''),
  status text NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'approved', 'declined')),
  decided_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  decision_note text NOT NULL DEFAULT '',
  refund_method text NOT NULL DEFAULT '',
  refund_ref text NOT NULL DEFAULT '',
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX refunds_applicant_id_idx ON refunds (applicant_id);
CREATE INDEX refunds_decided_by_idx ON refunds (decided_by);
CREATE INDEX refunds_status_idx ON refunds (status);

CREATE TRIGGER trg_refunds_updated_at BEFORE UPDATE ON refunds
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_refunds_block_delete BEFORE DELETE ON refunds
  FOR EACH ROW EXECUTE FUNCTION block_delete();
