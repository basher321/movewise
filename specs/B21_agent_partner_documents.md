# B21 Agent and partner documents

Owner request (2026-11-04): upload and store agreements and other documents for partner agents
(B16) and partners (B18). Owner chose: files up to 10 MB; the people who may edit an agent or
partner may also upload and archive its documents.

## Scope

- Documents of an agent or a partner: type, optional title, optional valid-until date, optional
  note, and one file (PDF, JPG or PNG, 1 byte to 10 MB, type taken from the file's first bytes).
- Types: agreement, trade_licence, id_document, bank_details, other.
- Never deleted, never changed. An old document is archived (who and when are kept); an archived
  document is final. Archived documents stay listed (hidden by default in the UI) and viewable.
- Shown status, computed, never stored: archived; else by valid_until: expired (before today),
  expiring (within 60 days), active.
- Files stored like applicant documents (B06): STORAGE_DIR/<year>/<month>/<random hex>.

## Who may do what

Order of checks: signed in -> module licensed -> role and section -> input valid -> work.

| | View list and files | Upload and archive |
|---|---|---|
| Agent documents | super_admin; admin with one of the agent's licensed sections | super_admin only |
| Partner documents | super_admin; admin of the partner's section | same as view |
| Finance | never | never |

No licensed section for the agent (or the partner's module not licensed): MODULE_NOT_LICENSED 403.

## Database

Migration 0018_agent_partner_documents.sql: table party_documents (owner_kind agent/partner with
exactly one of agent_id / partner_id), CHECK lists for owner_kind, doc_type, mime, status; size
CHECK <= 10485760; triggers: updated_at, block delete, and a guard that allows only
active -> archived and refuses any other change.

## API

| Method | Path | Result |
|---|---|---|
| GET | /api/admin/agents/{id}/documents | PartyDocument[] (active first, newest first) |
| POST | /api/admin/agents/{id}/documents | multipart: file, doc_type, title, valid_until, note -> PartyDocument |
| GET | /api/admin/agents/{id}/documents/{doc_id}/file | the file (inline, nosniff, sandbox, no-store) |
| POST | /api/admin/agents/{id}/documents/{doc_id}/archive | PartyDocument; 409 CONFLICT if already archived |

The same four for /api/admin/partners/{id}/documents.

PartyDocument: id, doc_type, title, original_name, mime, size_bytes, valid_until, note, status,
shown_status, uploaded_at, uploaded_by_name, archived_at, archived_by_name, file_url.

Errors (VALIDATION 422): "Please choose a file.", "Please choose the document type.",
"Valid until must be a date like 2027-12-31.", "The title must be at most 120 characters.",
"The note must be at most 500 characters.", "The file must be from 1 byte to 10 MB.",
"Only PDF, JPG or PNG files.". A document reached through another owner: 404.

Request body limit: 3 MB everywhere, except POST to the two upload paths: 11 MB
("The file must be 10 MB or smaller."). deploy/nginx.conf allows 11m on those two paths only.

Audit, one row each: agent_document.uploaded / .archived / .viewed and partner_document.* the same.

## Frontend

- api layer: listPartyDocuments, uploadPartyDocument, archivePartyDocument (lib/api/http/partyDocuments.ts).
- Agents tab and Partners tab: a "Documents" link per row opens a dialog listing the documents
  with status badges, Open, Archive (with a confirm step), "Show archived (n)", and an upload form
  for people who may upload.

## Tests

backend/tests/test_party_documents.py: upload, list, view, archive for both owners; expiry status;
10 MB limit and file type; input checks; who may do what; unlicensed module; other owner 404;
database refuses change and delete.
