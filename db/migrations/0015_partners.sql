-- 0015_partners (spec B18): B2B partner organisations with their logo, each shown only on the
-- page of its own module. Partners are switched off, never deleted; logo rows are only added.

CREATE TABLE partner_logos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mime text NOT NULL CHECK (mime IN ('image/png', 'image/jpeg', 'image/webp')),
  size_bytes integer NOT NULL CHECK (size_bytes > 0),
  sha256 text NOT NULL,
  bytes bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_partner_logos_block_change BEFORE UPDATE OR DELETE ON partner_logos
  FOR EACH ROW EXECUTE FUNCTION block_change();

CREATE TABLE partners (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  module text NOT NULL CHECK (module IN ('course', 'study', 'job')),
  partner_type text NOT NULL CHECK (partner_type IN (
    'university', 'college', 'employer', 'recruitment_agency', 'training_body', 'exam_board', 'other'
  )),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
  country text NOT NULL DEFAULT '' CHECK (length(country) <= 80),
  website text NOT NULL DEFAULT '' CHECK (website = '' OR website LIKE 'https://%'),
  description text NOT NULL DEFAULT '' CHECK (length(description) <= 300),
  contact_name text NOT NULL DEFAULT '' CHECK (length(contact_name) <= 120),
  contact_email text NOT NULL DEFAULT '' CHECK (length(contact_email) <= 254),
  contact_phone text NOT NULL DEFAULT '' CHECK (length(contact_phone) <= 40),
  agreement_ref text NOT NULL DEFAULT '' CHECK (length(agreement_ref) <= 120),
  agreement_until date,
  logo_id uuid REFERENCES partner_logos (id) ON DELETE RESTRICT,
  show_on_site boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX partners_public_idx ON partners (module, active, show_on_site, sort_order);
CREATE INDEX partners_logo_id_idx ON partners (logo_id);

CREATE TRIGGER trg_partners_updated_at BEFORE UPDATE ON partners
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_partners_block_delete BEFORE DELETE ON partners
  FOR EACH ROW EXECUTE FUNCTION block_delete();
