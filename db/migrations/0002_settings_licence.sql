-- 0002_settings_licence: company settings, encrypted secrets, branding pictures and the licence.

-- Uploaded logo and home pictures. Rows are only ever added; clearing a picture keeps its row.
CREATE TABLE branding_images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('logo', 'hero')),
  mime text NOT NULL CHECK (mime IN ('image/png', 'image/jpeg', 'image/webp')),
  size_bytes integer NOT NULL CHECK (size_bytes > 0),
  sha256 text NOT NULL,
  bytes bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Company settings: exactly one row.
CREATE TABLE settings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  singleton text NOT NULL DEFAULT 'settings' UNIQUE CHECK (singleton = 'settings'),
  name text NOT NULL CHECK (btrim(name) <> ''),
  tagline text NOT NULL DEFAULT '',
  brand_color text NOT NULL CHECK (brand_color ~ '^#[0-9A-Fa-f]{6}$'),
  hero_title text NOT NULL DEFAULT '',
  hero_text text NOT NULL DEFAULT '',
  stats jsonb NOT NULL CHECK (jsonb_typeof(stats) = 'array' AND jsonb_array_length(stats) = 3),
  about_title text NOT NULL DEFAULT '',
  about_text text NOT NULL DEFAULT '',
  address text NOT NULL DEFAULT '',
  phone text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  hours text NOT NULL DEFAULT '',
  facebook text NOT NULL DEFAULT '',
  website text NOT NULL DEFAULT '',
  invoice_prefix text NOT NULL CHECK (invoice_prefix ~ '^[A-Za-z0-9]{1,10}$'),
  invoice_footer text NOT NULL DEFAULT '',
  vat_bin text NOT NULL DEFAULT '',
  default_fee_study_poisha bigint NOT NULL CHECK (default_fee_study_poisha > 0),
  default_fee_job_poisha bigint NOT NULL CHECK (default_fee_job_poisha > 0),
  sslcommerz_enabled boolean NOT NULL DEFAULT false,
  sslcommerz_sandbox boolean NOT NULL DEFAULT true,
  bkash_enabled boolean NOT NULL DEFAULT false,
  bkash_sandbox boolean NOT NULL DEFAULT true,
  nagad_enabled boolean NOT NULL DEFAULT false,
  nagad_sandbox boolean NOT NULL DEFAULT true,
  manual_enabled boolean NOT NULL DEFAULT true,
  manual_instructions text NOT NULL DEFAULT '',
  mail_sender_name text NOT NULL DEFAULT '',
  mail_sender_email text NOT NULL DEFAULT '',
  whatsapp_number text NOT NULL DEFAULT '',
  logo_image_id uuid REFERENCES branding_images (id) ON DELETE RESTRICT,
  hero_image_id uuid REFERENCES branding_images (id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT settings_payment_method_on
    CHECK (sslcommerz_enabled OR bkash_enabled OR nagad_enabled OR manual_enabled)
);

CREATE INDEX settings_logo_image_id_idx ON settings (logo_image_id);
CREATE INDEX settings_hero_image_id_idx ON settings (hero_image_id);

CREATE TRIGGER trg_settings_updated_at BEFORE UPDATE ON settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Gateway, mail and WhatsApp secrets, encrypted by backend/app/crypto.py.
-- A row exists only once the secret has been saved.
CREATE TABLE settings_secrets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE CHECK (name IN (
    'sslcommerz.store_id', 'sslcommerz.store_password',
    'bkash.app_key', 'bkash.app_secret', 'bkash.username', 'bkash.password',
    'nagad.merchant_id', 'nagad.private_key',
    'mail.api_key', 'whatsapp.token'
  )),
  ciphertext text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_settings_secrets_updated_at BEFORE UPDATE ON settings_secrets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The licence: exactly one row. applied_by gets its foreign key when the users table exists.
CREATE TABLE licence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  singleton text NOT NULL DEFAULT 'licence' UNIQUE CHECK (singleton = 'licence'),
  key text CHECK (key IS NULL OR length(key) <= 4096),
  holder text,
  module_course boolean NOT NULL DEFAULT false,
  module_study boolean NOT NULL DEFAULT false,
  module_job boolean NOT NULL DEFAULT false,
  issued_at date,
  expires_at date,
  applied_at timestamptz,
  applied_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_licence_updated_at BEFORE UPDATE ON licence
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The single rows, with neutral defaults. No company, sample or demo data.
INSERT INTO settings (
  name, brand_color, stats, invoice_prefix,
  default_fee_study_poisha, default_fee_job_poisha, manual_enabled
) VALUES (
  'Company name', '#4F46E5',
  '[{"number": "", "label": ""}, {"number": "", "label": ""}, {"number": "", "label": ""}]',
  'INV', 100000, 100000, true
);

INSERT INTO licence DEFAULT VALUES;
