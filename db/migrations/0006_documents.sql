-- 0006_documents: application documents. Files live in STORAGE_DIR; rows are never deleted.

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE RESTRICT,
  applicant_id uuid NOT NULL REFERENCES applicant_accounts (id) ON DELETE RESTRICT,
  type text NOT NULL CHECK (btrim(type) <> ''),
  original_name text NOT NULL,
  stored_name text NOT NULL UNIQUE CHECK (stored_name ~ '^\d{4}/\d{2}/[0-9a-f]{32}$'),
  mime text NOT NULL CHECK (mime IN ('application/pdf', 'image/jpeg', 'image/png')),
  size_bytes integer NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 2097152),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected', 'replaced')),
  expiry date,
  note text NOT NULL DEFAULT '',
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  reviewed_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_application_id_idx ON documents (application_id);
CREATE INDEX documents_applicant_id_idx ON documents (applicant_id);
CREATE INDEX documents_status_idx ON documents (status);
CREATE INDEX documents_expiry_idx ON documents (expiry);
CREATE INDEX documents_reviewed_by_idx ON documents (reviewed_by);
CREATE INDEX documents_uploaded_at_idx ON documents (applicant_id, uploaded_at);

CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE FUNCTION documents_block_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'documents rows can never be deleted';
END;
$$;

CREATE TRIGGER trg_documents_block_delete
  BEFORE DELETE ON documents
  FOR EACH ROW EXECUTE FUNCTION documents_block_delete();
