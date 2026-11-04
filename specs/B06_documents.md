Spec B06 - Documents: secure upload, storage, viewing, review and expiry

Purpose
Let applicants upload the documents their application needs, keep the files safe on the server,
let only the owner and the right staff open them, let staff verify or reject them with an expiry
date, and show what is missing, expiring or expired. Endpoints follow the docs parts of
specs/F02_api_contract_mock.md, F06, F07, F08 and F10.

Scope
In scope:
- db/migrations/0006_documents.sql:
  - documents: id, application_id, applicant_id, type, original_name, stored_name, mime,
    size_bytes, sha256, status CHECK ('pending','verified','rejected','replaced'), expiry date,
    note, uploaded_at, reviewed_by, reviewed_at, updated_at. A trigger blocks DELETE.
    Indexes on application_id, applicant_id, status, expiry.
- File storage: a folder set by STORAGE_DIR in backend/.env (default backend/storage, which is
  in .gitignore). Files are saved as <stored_name> (a random uuid with no extension) inside
  sub-folders by year/month. The original file name is kept only in the database.
- app/files.py: detect type from the file's first bytes, save safely, open for reading.
- Endpoints below; B05 detail responses now include documents.
Out of scope: virus scanning, image or PDF editing, previews / thumbnails, documents not linked
to an application, deleting files.

Contract (all under /api)
Applicant (A, module licensed, own application only - otherwise 404):
- POST /me/{module}/applications/{id}/documents   multipart: type, file  -> the document
- GET  /me/{module}/documents/{doc_id}/file        -> the file
Admin (require_section of the application's module):
- GET  /admin/documents?filter=pending|expiring|expired|rejected|verified|all&q=&page=
  (50 per page) -> each row: document, applicant name and email, application ref, item title,
  application status. Only modules the admin may open.
- GET  /admin/documents/{id}/file
- POST /admin/documents/{id}/verify {expiry?: "YYYY-MM-DD"}
- POST /admin/documents/{id}/reject {reason}
B05 changes:
- GET /me/{module}/applications/{id} and GET /admin/applications(/{id}) now include
  documents (the latest non-replaced one per type, with shown_status), required_types, and
  missing_count.
- shown_status = "expiring" if verified and expiry is within the next 60 days (Asia/Dhaka date),
  "expired" if verified and expiry is before today, otherwise the stored status. Never stored.

Functional rules
- Upload is allowed only while the application is active (CONFLICT otherwise).
- type must be one of the required document types of that module (from app/stages.py).
- Allowed files: PDF (starts with %PDF-), JPEG (FF D8 FF) and PNG (89 50 4E 47 0D 0A 1A 0A),
  checked by the first bytes, never by the name or the browser's content type. Anything else is
  VALIDATION "Only PDF, JPG or PNG files." Size 1 byte to 2 MB, otherwise VALIDATION.
- original_name is cleaned: path parts removed, only the last 200 characters kept, control
  characters removed.
- Saving: write to a temporary file in the same folder, then rename into place, then insert the
  row - all inside one database transaction. If the database step fails, the temporary or new
  file is removed so no orphan file is left.
- Uploading a type that already has a pending, verified or rejected document marks the older one
  replaced (it stays stored and in the database).
- Upload limits: at most 20 uploads per applicant per hour and 60 documents per application
  (TOO_MANY_TRIES / VALIDATION).
- Upload adds a public event "Uploaded <type>" (B05 app_events).
- Opening a file: sent with its stored mime type, Content-Disposition inline with the cleaned
  original name, X-Content-Type-Options: nosniff, Content-Security-Policy: sandbox, and
  Cache-Control: private, no-store.
- Each time an admin opens a file, an audit row "Document viewed" is written (who, which
  document). Applicant views are not audited.
- Verify: only a pending document; optional expiry must be a real date; sets reviewed_by and
  reviewed_at; public event "<type> verified".
- Reject: only a pending document; reason required (max 500 characters); public event
  "<type> rejected" with the reason; the applicant gets "Please upload your <type> again" in
  the outbox.
- A replaced document can still be opened by staff (history), but is not counted as current.
- Every change writes exactly one audit row in the same transaction.

Edge cases
- File with a .pdf name that is really HTML: VALIDATION.
- Same file uploaded twice: both stored (sha256 is kept for reference; no error).
- Stored file missing from disk (for example, a bad restore): 500 INTERNAL "File is missing",
  logged with the document id; the row is not changed.
- Application withdrawn later: its documents stay viewable by the applicant and staff, but no
  new uploads.
- Module unlicensed later: all document endpoints for that module return 403; files stay.

Non-functional rules
- No new packages.
- The storage folder is never inside the web root and never served directly.
- README: add "Back up the database AND the storage folder together."
- pytest uses a temporary storage folder that is created for the test run.
- pytest passes, including all earlier tests.

Acceptance criteria
- b58 Migration 0006 applies; DELETE on documents fails.
- b59 Uploading a real small PDF works; the file on disk has a uuid name and no extension; the row
  has the right size and sha256.
- b60 A .pdf that is really text, a .exe, an empty file and a 2.1 MB file are VALIDATION.
- b61 Uploading the same type again marks the older document replaced; both files still exist.
- b62 Another applicant gets 404 for the file; an admin with only the job section gets FORBIDDEN
  for a study document; finance gets FORBIDDEN.
- b63 Opening a file returns the right mime type and the headers nosniff, sandbox and no-store;
  an admin view writes "Document viewed" to the audit log.
- b64 Verify with expiry 30 days ahead shows "expiring"; with a past date, "expired"; verifying a
  rejected document is CONFLICT.
- b65 Reject without a reason is VALIDATION; with a reason it adds a public event and an outbox row.
- b66 Upload on a withdrawn application is CONFLICT.
- b67 If the database insert fails during upload (forced in the test), no file is left in storage.
- b68 /admin/documents?filter=expiring returns only verified documents expiring within 60 days.
- b69 missing_count in the application detail drops by one after each required type is uploaded.
- b70 Every successful change writes exactly one audit row.

Assumptions
- Specs B01-B05 are complete and committed.
- STORAGE_DIR may be added to backend/.env by hand; without it the default folder is used.
