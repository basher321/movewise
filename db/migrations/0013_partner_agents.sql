-- 0013_partner_agents (spec B16): partner agents who refer applicants, the agent of each
-- application, and the commission owed and paid. Agents are switched off, never deleted.

CREATE TABLE partner_agents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
  firm text NOT NULL DEFAULT '' CHECK (length(firm) <= 120),
  phone text NOT NULL DEFAULT '' CHECK (length(phone) <= 40),
  email text NOT NULL DEFAULT '' CHECK (length(email) <= 254),
  country text NOT NULL DEFAULT '' CHECK (length(country) <= 80),
  address text NOT NULL DEFAULT '' CHECK (length(address) <= 300),
  sections text[] NOT NULL DEFAULT '{}' CHECK (sections <@ ARRAY['study', 'job']::text[]),
  commission_type text NOT NULL DEFAULT 'fixed' CHECK (commission_type IN ('fixed', 'percent')),
  commission_poisha bigint NOT NULL DEFAULT 0 CHECK (commission_poisha >= 0),
  -- Basis points: 1250 = 12.50 %.
  commission_percent_bp integer NOT NULL DEFAULT 0 CHECK (commission_percent_bp BETWEEN 0 AND 10000),
  notes text NOT NULL DEFAULT '' CHECK (length(notes) <= 1000),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX partner_agents_email_key ON partner_agents (lower(email)) WHERE email <> '';
CREATE INDEX partner_agents_active_idx ON partner_agents (active, name);

CREATE TRIGGER trg_partner_agents_updated_at BEFORE UPDATE ON partner_agents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_partner_agents_block_delete BEFORE DELETE ON partner_agents
  FOR EACH ROW EXECUTE FUNCTION block_delete();

ALTER TABLE applications
  ADD COLUMN agent_id uuid REFERENCES partner_agents (id) ON DELETE RESTRICT;

CREATE INDEX applications_agent_id_idx ON applications (agent_id);

CREATE TABLE agent_commissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id uuid NOT NULL REFERENCES partner_agents (id) ON DELETE RESTRICT,
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE RESTRICT,
  amount_poisha bigint NOT NULL CHECK (amount_poisha >= 0),
  status text NOT NULL DEFAULT 'due' CHECK (status IN ('due', 'paid', 'cancelled')),
  paid_at timestamptz,
  paid_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  pay_reference text NOT NULL DEFAULT '' CHECK (length(pay_reference) <= 120),
  note text NOT NULL DEFAULT '' CHECK (length(note) <= 300),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);

CREATE INDEX agent_commissions_agent_id_idx ON agent_commissions (agent_id, status);
CREATE INDEX agent_commissions_application_id_idx ON agent_commissions (application_id);
CREATE INDEX agent_commissions_paid_by_idx ON agent_commissions (paid_by);
-- One live commission per case.
CREATE UNIQUE INDEX agent_commissions_one_live_idx ON agent_commissions (application_id)
  WHERE status <> 'cancelled';

-- A paid or cancelled commission is final.
CREATE FUNCTION agent_commissions_final() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('paid', 'cancelled') THEN
    RAISE EXCEPTION 'A % commission can no longer change', OLD.status;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_agent_commissions_final BEFORE UPDATE ON agent_commissions
  FOR EACH ROW EXECUTE FUNCTION agent_commissions_final();
CREATE TRIGGER trg_agent_commissions_updated_at BEFORE UPDATE ON agent_commissions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_agent_commissions_block_delete BEFORE DELETE ON agent_commissions
  FOR EACH ROW EXECUTE FUNCTION block_delete();
