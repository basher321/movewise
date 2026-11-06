-- 0021_remote_jobs_module: Remote Jobs, a fifth module built like Job Processing but with no visa,
-- medical or flight steps: search, match, payment, processing, then the offer / completion letter.
-- Remote roles are rows of vacancies with remote = true (column from 0020); remote applications
-- use vacancy_id with module 'remote'. Only constraints are replaced (to add 'remote' to the lists)
-- and columns added. No data is dropped or deleted.

-- ---------------------------------------------------------------- settings and licence

ALTER TABLE settings
  ADD COLUMN default_fee_remote_poisha bigint NOT NULL DEFAULT 100000 CHECK (default_fee_remote_poisha > 0);

ALTER TABLE licence
  ADD COLUMN module_remote boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------- applications

ALTER TABLE applications DROP CONSTRAINT applications_module_check;
ALTER TABLE applications
  ADD CONSTRAINT applications_module_check CHECK (module IN ('study', 'job', 'visa', 'remote'));

ALTER TABLE applications DROP CONSTRAINT applications_one_item;
ALTER TABLE applications ADD CONSTRAINT applications_one_item CHECK (
  (module = 'study' AND university_id IS NOT NULL AND vacancy_id IS NULL AND visa_program_id IS NULL)
  OR (module IN ('job', 'remote') AND vacancy_id IS NOT NULL AND university_id IS NULL AND visa_program_id IS NULL)
  OR (module = 'visa' AND visa_program_id IS NOT NULL AND university_id IS NULL AND vacancy_id IS NULL)
);

ALTER TABLE applications DROP CONSTRAINT applications_stage_range;
ALTER TABLE applications ADD CONSTRAINT applications_stage_range CHECK (
  (module = 'study' AND stage <= 8) OR (module = 'job' AND stage <= 7) OR (module = 'visa' AND stage <= 7)
  OR (module = 'remote' AND stage <= 5)
);

-- ---------------------------------------------------------------- accounts and sign-in

ALTER TABLE admin_users DROP CONSTRAINT admin_users_sections_check;
ALTER TABLE admin_users
  ADD CONSTRAINT admin_users_sections_check CHECK (sections <@ ARRAY['course', 'study', 'job', 'visa', 'remote']::text[]);

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_module_check;
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_public_id_check;
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_public_id_check CHECK (public_id ~ '^(CRS|STU|JOB|VIS|RMT)-[A-HJ-NP-Z2-9]{6}$');

ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_prefix;
ALTER TABLE applicant_accounts ADD CONSTRAINT applicant_accounts_prefix CHECK (
  (module = 'course' AND public_id LIKE 'CRS-%')
  OR (module = 'study' AND public_id LIKE 'STU-%')
  OR (module = 'job' AND public_id LIKE 'JOB-%')
  OR (module = 'visa' AND public_id LIKE 'VIS-%')
  OR (module = 'remote' AND public_id LIKE 'RMT-%')
);

ALTER TABLE sessions DROP CONSTRAINT sessions_module_check;
ALTER TABLE sessions
  ADD CONSTRAINT sessions_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE signin_failures DROP CONSTRAINT signin_failures_kind_check;
ALTER TABLE signin_failures
  ADD CONSTRAINT signin_failures_kind_check CHECK (kind IN ('admin', 'course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE password_resets DROP CONSTRAINT password_resets_kind_check;
ALTER TABLE password_resets
  ADD CONSTRAINT password_resets_kind_check CHECK (kind IN ('admin', 'course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE notifications DROP CONSTRAINT notifications_module_check;
ALTER TABLE notifications
  ADD CONSTRAINT notifications_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

-- ---------------------------------------------------------------- money

ALTER TABLE payments DROP CONSTRAINT payments_module_check;
ALTER TABLE payments
  ADD CONSTRAINT payments_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE invoices DROP CONSTRAINT invoices_module_check;
ALTER TABLE invoices
  ADD CONSTRAINT invoices_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_entries_category_check;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_category_check CHECK (category IN (
  'course', 'study', 'job', 'visa', 'remote', 'otherin', 'opening',
  'salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'
));

ALTER TABLE ledger_entries DROP CONSTRAINT ledger_category_direction;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_category_direction CHECK (
  (direction = 'in' AND category IN ('course', 'study', 'job', 'visa', 'remote', 'otherin', 'opening'))
  OR (direction = 'out' AND category IN ('salary', 'rent', 'mkt', 'partner', 'tools', 'refund', 'otherout'))
);

-- ---------------------------------------------------------------- enquiries, agents, partners, AI, messages

ALTER TABLE enquiries DROP CONSTRAINT enquiries_interest_check;
ALTER TABLE enquiries
  ADD CONSTRAINT enquiries_interest_check CHECK (interest IN ('course', 'study', 'job', 'visa', 'remote', 'other'));

ALTER TABLE partner_agents DROP CONSTRAINT partner_agents_sections_check;
ALTER TABLE partner_agents
  ADD CONSTRAINT partner_agents_sections_check CHECK (sections <@ ARRAY['study', 'job', 'visa', 'remote']::text[]);

ALTER TABLE partners DROP CONSTRAINT partners_module_check;
ALTER TABLE partners
  ADD CONSTRAINT partners_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));

ALTER TABLE ai_questions DROP CONSTRAINT ai_questions_module_check;
ALTER TABLE ai_questions
  ADD CONSTRAINT ai_questions_module_check CHECK (module IN ('study', 'job', 'visa', 'remote'));

ALTER TABLE message_batches DROP CONSTRAINT message_batches_module_check;
ALTER TABLE message_batches
  ADD CONSTRAINT message_batches_module_check CHECK (module IN ('course', 'study', 'job', 'visa', 'remote'));
