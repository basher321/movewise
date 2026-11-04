-- 0016_immigration: the Immigration Processing module (code name "visa"), spec B19.
-- Visa programmes for every country and every visa type; applicants choose a programme, upload
-- documents and follow their stages, exactly like Student Consultancy and Job Processing.
-- Partner agents (B16) and B2B partners (B18) can also work in this module.
--
-- The owner allowed the DROP CONSTRAINT statements below (2026-11-04, "follow the same
-- pattern" as 0011). Each one removes an old CHECK rule and at once adds a wider rule that also
-- allows 'visa'. No table, column, index or row is removed.

-- ---------------------------------------------------------------- visa programmes

CREATE TABLE visa_programs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  title text NOT NULL CHECK (btrim(title) <> '' AND length(title) <= 200),
  country text NOT NULL CHECK (btrim(country) <> '' AND length(country) <= 120),
  visa_type text NOT NULL CHECK (visa_type IN (
    'visit', 'tourist', 'business', 'family', 'spouse', 'work', 'student',
    'permanent_residence', 'citizenship', 'transit', 'medical', 'other'
  )),
  processing_time text NOT NULL DEFAULT '' CHECK (length(processing_time) <= 200),
  validity text NOT NULL DEFAULT '' CHECK (length(validity) <= 200),
  government_fee text NOT NULL DEFAULT '' CHECK (length(government_fee) <= 200),
  description text NOT NULL DEFAULT '' CHECK (length(description) <= 4000),
  eligibility text[] NOT NULL CHECK (cardinality(eligibility) > 0),
  required_documents text[] NOT NULL CHECK (cardinality(required_documents) > 0),
  conditions text NOT NULL DEFAULT '' CHECK (length(conditions) <= 4000),
  official_link text NOT NULL DEFAULT '' CHECK (official_link = '' OR official_link LIKE 'https://%'),
  embassy_email text NOT NULL DEFAULT '' CHECK (length(embassy_email) <= 254),
  fee_override_poisha bigint CHECK (fee_override_poisha IS NULL OR fee_override_poisha > 0),
  published boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX visa_programs_published_idx ON visa_programs (published);
CREATE INDEX visa_programs_country_type_idx ON visa_programs (country, visa_type);

CREATE TRIGGER trg_visa_programs_updated_at BEFORE UPDATE ON visa_programs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------- settings and licence

ALTER TABLE settings
  ADD COLUMN default_fee_visa_poisha bigint NOT NULL DEFAULT 100000 CHECK (default_fee_visa_poisha > 0);

ALTER TABLE licence
  ADD COLUMN module_visa boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------- applications

ALTER TABLE applications
  ADD COLUMN visa_program_id uuid REFERENCES visa_programs (id) ON DELETE RESTRICT;

CREATE INDEX applications_visa_program_id_idx ON applications (visa_program_id);

-- Only one open application per applicant and visa programme (study and job keep
-- applications_one_open_idx, where a visa row counts as NULL and never clashes).
CREATE UNIQUE INDEX applications_one_open_visa_idx
  ON applications (applicant_id, visa_program_id)
  WHERE status IN ('active', 'on_hold') AND visa_program_id IS NOT NULL;

ALTER TABLE applications DROP CONSTRAINT applications_module_check;
ALTER TABLE applications
  ADD CONSTRAINT applications_module_check CHECK (module IN ('study', 'job', 'visa'));

ALTER TABLE applications DROP CONSTRAINT applications_one_item;
ALTER TABLE applications ADD CONSTRAINT applications_one_item CHECK (
  (module = 'study' AND university_id IS NOT NULL AND vacancy_id IS NULL AND visa_program_id IS NULL)
  OR (module = 'job' AND vacancy_id IS NOT NULL AND university_id IS NULL AND visa_program_id IS NULL)
  OR (module = 'visa' AND visa_program_id IS NOT NULL AND university_id IS NULL AND vacancy_id IS NULL)
);

ALTER TABLE applications DROP CONSTRAINT applications_stage_range;
ALTER TABLE applications ADD CONSTRAINT applications_stage_range CHECK (
  (module = 'study' AND stage <= 8) OR (module = 'job' AND stage <= 7) OR (module = 'visa' AND stage <= 7)
);

-- ---------------------------------------------------------------- accounts and sign-in

ALTER TABLE admin_users DROP CONSTRAINT admin_users_sections_check;
ALTER TABLE admin_users
  ADD CONSTRAINT admin_users_sections_check CHECK (sections <@ ARRAY['course', 'study', 'job', 'visa']::text[]);

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_module_check;
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_public_id_check;
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_public_id_check CHECK (public_id ~ '^(CRS|STU|JOB|VIS)-[A-HJ-NP-Z2-9]{6}$');

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_prefix;
ALTER TABLE applicant_accounts ADD CONSTRAINT applicant_accounts_prefix CHECK (
  (module = 'course' AND public_id LIKE 'CRS-%')
  OR (module = 'study' AND public_id LIKE 'STU-%')
  OR (module = 'job' AND public_id LIKE 'JOB-%')
  OR (module = 'visa' AND public_id LIKE 'VIS-%')
);

ALTER TABLE sessions DROP CONSTRAINT sessions_module_check;
ALTER TABLE sessions
  ADD CONSTRAINT sessions_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

ALTER TABLE signin_failures DROP CONSTRAINT signin_failures_kind_check;
ALTER TABLE signin_failures
  ADD CONSTRAINT signin_failures_kind_check CHECK (kind IN ('admin', 'course', 'study', 'job', 'visa'));

ALTER TABLE password_resets DROP CONSTRAINT password_resets_kind_check;
ALTER TABLE password_resets
  ADD CONSTRAINT password_resets_kind_check CHECK (kind IN ('admin', 'course', 'study', 'job', 'visa'));

ALTER TABLE notifications DROP CONSTRAINT notifications_module_check;
ALTER TABLE notifications
  ADD CONSTRAINT notifications_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

-- ---------------------------------------------------------------- money

ALTER TABLE payments DROP CONSTRAINT payments_module_check;
ALTER TABLE payments
  ADD CONSTRAINT payments_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

ALTER TABLE invoices DROP CONSTRAINT invoices_module_check;
ALTER TABLE invoices
  ADD CONSTRAINT invoices_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_category_check;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_category_check CHECK (category IN (
  'course', 'study', 'job', 'visa', 'otherin', 'opening',
  'salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'
));

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_category_direction;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_category_direction CHECK (
  (direction = 'in' AND category IN ('course', 'study', 'job', 'visa', 'otherin', 'opening'))
  OR (direction = 'out' AND category IN ('salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'))
);

-- ---------------------------------------------------------------- enquiries, agents, partners, AI

ALTER TABLE enquiries DROP CONSTRAINT enquiries_interest_check;
ALTER TABLE enquiries
  ADD CONSTRAINT enquiries_interest_check CHECK (interest IN ('course', 'study', 'job', 'visa', 'other'));

ALTER TABLE partner_agents DROP CONSTRAINT partner_agents_sections_check;
ALTER TABLE partner_agents
  ADD CONSTRAINT partner_agents_sections_check CHECK (sections <@ ARRAY['study', 'job', 'visa']::text[]);

ALTER TABLE partners DROP CONSTRAINT partners_module_check;
ALTER TABLE partners
  ADD CONSTRAINT partners_module_check CHECK (module IN ('course', 'study', 'job', 'visa'));

-- Immigration partners: visa application centres and immigration law firms.
ALTER TABLE partners DROP CONSTRAINT partners_partner_type_check;
ALTER TABLE partners ADD CONSTRAINT partners_partner_type_check CHECK (partner_type IN (
  'university', 'college', 'employer', 'recruitment_agency', 'training_body', 'exam_board',
  'visa_centre', 'law_firm', 'other'
));

ALTER TABLE ai_questions DROP CONSTRAINT ai_questions_module_check;
ALTER TABLE ai_questions
  ADD CONSTRAINT ai_questions_module_check CHECK (module IN ('study', 'job', 'visa'));
