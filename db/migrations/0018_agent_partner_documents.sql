-- 0018_agent_partner_documents (spec B21): agreements and other documents of partner agents and
-- partners. Files live in STORAGE_DIR like applicant documents. Rows are never deleted: an old
-- document is archived, and an archived document is final. The file and its details never change.
-- Only adds a table, indexes, a function and triggers. Nothing is dropped or deleted.

CREATE TABLE party_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_kind text NOT NULL CHECK (owner_kind IN ('agent', 'partner')),
  agent_id uuid REFERENCES partner_agents (id) ON DELETE RESTRICT,
  partner_id uuid REFERENCES partners (id) ON DELETE RESTRICT,
  doc_type text NOT NULL CHECK (doc_type IN (
    'agreement', 'trade_licence', 'id_document', 'bank_details', 'other'
  )),
  title text NOT NULL DEFAULT '' CHECK (length(title) <= 120),
  original_name text NOT NULL CHECK (btrim(original_name) <> '' AND length(original_name) <= 200),
  stored_name text NOT NULL UNIQUE CHECK (stored_name ~ '^\d{4}/\d{2}/[0-9a-f]{32}$'),
  mime text NOT NULL CHECK (mime IN ('application/pdf', 'image/jpeg', 'image/png')),
  size_bytes integer NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  valid_until date,
  note text NOT NULL DEFAULT '' CHECK (length(note) <= 500),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  uploaded_by uuid NOT NULL REFERENCES admin_users (id) ON DELETE RESTRICT,
  archived_by uuid REFERENCES admin_users (id) ON DELETE RESTRICT,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT party_documents_one_owner CHECK (
    (owner_kind = 'agent' AND agent_id IS NOT NULL AND partner_id IS NULL)
    OR (owner_kind = 'partner' AND partner_id IS NOT NULL AND agent_id IS NULL)
  ),
  CONSTRAINT party_documents_archived_pair CHECK (
    (status = 'archived') = (archived_at IS NOT NULL)
    AND (archived_at IS NULL) = (archived_by IS NULL)
  )
);

CREATE INDEX party_documents_agent_id_idx ON party_documents (agent_id, status);
CREATE INDEX party_documents_partner_id_idx ON party_documents (partner_id, status);
CREATE INDEX party_documents_uploaded_by_idx ON party_documents (uploaded_by);
CREATE INDEX party_documents_archived_by_idx ON party_documents (archived_by);
CREATE INDEX party_documents_valid_until_idx ON party_documents (valid_until);

-- The only change allowed is active -> archived (with who and when). Everything else is fixed.
CREATE FUNCTION party_documents_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'archived' THEN
    RAISE EXCEPTION 'An archived document can no longer change';
  END IF;
  IF (NEW.owner_kind, NEW.agent_id, NEW.partner_id, NEW.doc_type, NEW.title, NEW.original_name,
      NEW.stored_name, NEW.mime, NEW.size_bytes, NEW.sha256, NEW.valid_until, NEW.note,
      NEW.uploaded_by, NEW.created_at)
     IS DISTINCT FROM
     (OLD.owner_kind, OLD.agent_id, OLD.partner_id, OLD.doc_type, OLD.title, OLD.original_name,
      OLD.stored_name, OLD.mime, OLD.size_bytes, OLD.sha256, OLD.valid_until, OLD.note,
      OLD.uploaded_by, OLD.created_at) THEN
    RAISE EXCEPTION 'A document''s file and details never change; upload a new one instead';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_party_documents_guard BEFORE UPDATE ON party_documents
  FOR EACH ROW EXECUTE FUNCTION party_documents_guard();
CREATE TRIGGER trg_party_documents_updated_at BEFORE UPDATE ON party_documents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_party_documents_block_delete BEFORE DELETE ON party_documents
  FOR EACH ROW EXECUTE FUNCTION block_delete();
