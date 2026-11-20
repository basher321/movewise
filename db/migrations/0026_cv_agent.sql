-- 0026_cv_agent: the AI CV Agent (spec B28, phase 1). CV projects of applicants, their uploaded
-- files (encrypted on disk, content removed after cv_file_days), CV versions, cover letters and
-- a count of AI calls (never document text). Two settings for the limits. No data rows.
-- Nothing is dropped or removed.

ALTER TABLE settings
  ADD COLUMN cv_file_days integer NOT NULL DEFAULT 30 CHECK (cv_file_days BETWEEN 1 AND 365),
  ADD COLUMN cv_ai_per_day integer NOT NULL DEFAULT 40 CHECK (cv_ai_per_day BETWEEN 1 AND 1000);

CREATE TABLE cv_projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  module text NOT NULL CHECK (module IN ('course', 'study', 'job', 'visa', 'remote')),
  title text NOT NULL DEFAULT '' CHECK (char_length(title) <= 120),
  cv_type text CHECK (cv_type IS NULL OR cv_type IN (
    'new', 'update', 'overseas', 'immigration', 'student', 'graduate', 'professional', 'academic', 'europass'
  )),
  cover_letter boolean NOT NULL DEFAULT false,
  country text CHECK (country IS NULL OR char_length(country) BETWEEN 2 AND 60),
  category text CHECK (category IS NULL OR category IN (
    'skilled_worker', 'it', 'healthcare', 'engineering', 'construction', 'hospitality', 'agriculture',
    'manufacturing', 'driving', 'administration', 'business', 'finance', 'education', 'research',
    'student_admission', 'general'
  )),
  job_advert_text text NOT NULL DEFAULT '' CHECK (char_length(job_advert_text) <= 20000),
  doc_kinds text[] NOT NULL DEFAULT '{}',
  consent_at timestamptz,
  template text CHECK (template IS NULL OR template IN (
    'modern', 'corporate', 'minimalist', 'technical', 'academic', 'europass', 'international'
  )),
  page_length smallint NOT NULL DEFAULT 2 CHECK (page_length IN (1, 2)),
  step smallint NOT NULL DEFAULT 1 CHECK (step BETWEEN 1 AND 8),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'deleted')),
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX cv_projects_applicant_id_idx ON cv_projects (applicant_id, updated_at DESC);

CREATE TRIGGER trg_cv_projects_updated_at BEFORE UPDATE ON cv_projects
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE cv_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES cv_projects (id) ON DELETE RESTRICT,
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  file_name text NOT NULL CHECK (btrim(file_name) <> '' AND char_length(file_name) <= 200),
  doc_kind text NOT NULL DEFAULT 'other' CHECK (doc_kind IN (
    'cv', 'academic', 'experience', 'training', 'licence', 'language', 'passport', 'other'
  )),
  mime text NOT NULL CHECK (mime IN (
    'application/pdf', 'image/jpeg', 'image/png', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  )),
  size_bytes integer NOT NULL CHECK (size_bytes > 0),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  -- NULL once the content is removed (by the person or after cv_file_days).
  storage_path text,
  extraction_status text NOT NULL DEFAULT 'waiting' CHECK (extraction_status IN (
    'waiting', 'reading', 'done', 'failed', 'unsupported'
  )),
  delete_after timestamptz NOT NULL,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cv_files_removed CHECK ((deleted_at IS NULL) = (storage_path IS NOT NULL))
);

CREATE INDEX cv_files_project_id_idx ON cv_files (project_id, created_at);
CREATE INDEX cv_files_applicant_id_idx ON cv_files (applicant_id, created_at);
CREATE INDEX cv_files_delete_after_idx ON cv_files (delete_after) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_cv_files_updated_at BEFORE UPDATE ON cv_files
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE cv_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES cv_projects (id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version >= 1),
  data jsonb NOT NULL,
  reason text NOT NULL CHECK (reason IN (
    'answers', 'extracted', 'edited', 'generated', 'regenerated', 'shorter', 'stronger', 'removed', 'restored'
  )),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, version)
);

CREATE TABLE cover_letters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES cv_projects (id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version >= 1),
  body text NOT NULL CHECK (char_length(body) <= 20000),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, version)
);

CREATE TABLE cv_ai_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES cv_projects (id) ON DELETE RESTRICT,
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  service text NOT NULL CHECK (service IN (
    'extractor', 'merger', 'gap_checker', 'writer', 'reviewer', 'cover_letter'
  )),
  provider text CHECK (provider IS NULL OR provider IN ('claude', 'openai', 'gemini', 'groq')),
  status text NOT NULL CHECK (status IN ('ok', 'failed', 'invalid_json')),
  input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX cv_ai_calls_project_id_idx ON cv_ai_calls (project_id);
CREATE INDEX cv_ai_calls_applicant_id_idx ON cv_ai_calls (applicant_id, created_at);

-- Versions, cover letters and the AI call count are history: never changed or deleted.
CREATE TRIGGER trg_cv_versions_block_change BEFORE UPDATE OR DELETE ON cv_versions
  FOR EACH ROW EXECUTE FUNCTION block_change();
CREATE TRIGGER trg_cover_letters_block_change BEFORE UPDATE OR DELETE ON cover_letters
  FOR EACH ROW EXECUTE FUNCTION block_change();
CREATE TRIGGER trg_cv_ai_calls_block_change BEFORE UPDATE OR DELETE ON cv_ai_calls
  FOR EACH ROW EXECUTE FUNCTION block_change();

-- CV projects and files are never deleted: "Delete CV" sets status 'deleted' and removes the
-- files' content from disk (spec B28 Decisions 2).
CREATE TRIGGER trg_cv_projects_block_delete BEFORE DELETE ON cv_projects
  FOR EACH ROW EXECUTE FUNCTION block_delete();
CREATE TRIGGER trg_cv_files_block_delete BEFORE DELETE ON cv_files
  FOR EACH ROW EXECUTE FUNCTION block_delete();
