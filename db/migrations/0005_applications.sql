-- 0005_applications: Student Consultancy and Job Processing applications and their history.

CREATE TABLE applications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ref text NOT NULL UNIQUE CHECK (ref ~ '^APP-[A-HJ-NP-Z2-9]{6}$'),
  module text NOT NULL CHECK (module IN ('study', 'job')),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  university_id uuid REFERENCES universities (id) ON DELETE RESTRICT,
  vacancy_id uuid REFERENCES vacancies (id) ON DELETE RESTRICT,
  stage integer NOT NULL DEFAULT 0 CHECK (stage >= 0),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'on_hold', 'rejected', 'withdrawn', 'completed')),
  assigned_to uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  deadline date,
  interview_at timestamptz,
  interview_result text NOT NULL DEFAULT 'pending' CHECK (interview_result IN ('pending', 'passed', 'failed')),
  offered_salary_usd integer CHECK (offered_salary_usd IS NULL OR offered_salary_usd > 0),
  fee_paid boolean NOT NULL DEFAULT false,
  answers jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(answers) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT applications_one_item CHECK (
    (module = 'study' AND university_id IS NOT NULL AND vacancy_id IS NULL)
    OR (module = 'job' AND vacancy_id IS NOT NULL AND university_id IS NULL)
  ),
  CONSTRAINT applications_stage_range CHECK (
    (module = 'study' AND stage <= 8) OR (module = 'job' AND stage <= 7)
  )
);

CREATE INDEX applications_module_status_idx ON applications (module, status);
CREATE INDEX applications_applicant_id_idx ON applications (applicant_id);
CREATE INDEX applications_assigned_to_idx ON applications (assigned_to);
CREATE INDEX applications_university_id_idx ON applications (university_id);
CREATE INDEX applications_vacancy_id_idx ON applications (vacancy_id);

-- Only one open (active or on hold) application per applicant and item.
CREATE UNIQUE INDEX applications_one_open_idx
  ON applications (applicant_id, (COALESCE(university_id, vacancy_id)))
  WHERE status IN ('active', 'on_hold');

CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON applications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- History of an application. Rows can never be changed or deleted.
-- by_id holds an admin_users or applicant_accounts id (no foreign key: it can point at either).
CREATE TABLE app_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE RESTRICT,
  at timestamptz NOT NULL DEFAULT clock_timestamp(),
  by_kind text NOT NULL CHECK (by_kind IN ('applicant', 'admin', 'system')),
  by_id uuid,
  by_name text NOT NULL,
  text text NOT NULL,
  note text NOT NULL DEFAULT '',
  public boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX app_events_application_id_idx ON app_events (application_id, at);

CREATE FUNCTION app_events_block_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'app_events rows can never be changed or deleted';
END;
$$;

CREATE TRIGGER trg_app_events_block_change
  BEFORE UPDATE OR DELETE ON app_events
  FOR EACH ROW EXECUTE FUNCTION app_events_block_change();

-- Case emails and updates link to their application, so staff see what was sent.
ALTER TABLE notifications
  ADD COLUMN application_id uuid REFERENCES applications (id) ON DELETE RESTRICT;

CREATE INDEX notifications_application_id_idx ON notifications (application_id);
