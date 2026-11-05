Spec B20 - Certificates and completion letters (all modules), and client messages by email and WhatsApp

Purpose
Staff and clients can view, download and send certificates as PDF files, for every module, and
staff can send any client a message by email, WhatsApp or both, one client or a group at a time.
Owner decisions 2026-11-04:
- Certificates in all modules: Training keeps its course certificate; Student Consultancy, Job
  Processing and Immigration Processing get a "completion letter" for a completed case.
- Staff can view and download every certificate and letter (also before approval, as a draft).
- Messages: "Send message" on any client in every module, plus bulk messages to a filtered group.
  Staff choose the channel: email, WhatsApp or both. (Recommended option; owner may change.)
- Sending a certificate: the email carries the PDF as an attachment; WhatsApp carries a text with
  a secure download link, through the existing approved template (no new Meta template).
  (Recommended option; owner may change.)

Scope
In scope:
- db/migrations/0017_certificates_messages.sql (ADD only: no DROP anywhere).
- backend/app/certificates/ (new): pdf.py (one PDF layout for certificates and letters, drawn like
  drawCert() in the reference: 1000x707 landscape proportions, logo or company name, brand colour,
  "DRAFT - NOT APPROVED" watermark until approved), links.py (signed download links), fonts/
  (Sora, DM Sans and Noto Sans Bengali TTF files with their OFL licence text).
- backend/requirements.txt: fpdf2 (and its dependency Pillow). The only new packages.
- backend/app/notify: email attachments (built at send time from the notification's attachment
  reference, never stored as a file); the worker sends them; WhatsApp unchanged.
- backend/app/routers/certificates.py (new) and messages.py (new); main.py includes them.
- backend/tests/test_certificates.py, test_messages.py (new).
- frontend/src/lib/api: types and calls listed in the contract (http only).
- frontend: admin Courses tab (view / download / send certificate), case view in CasesTab (issue,
  view, download, send completion letter; "Send message" with channel choice), accounts lists in
  every module tab ("Send message"), a "Message a group" dialog in every module tab, applicant
  profile (download PDF for certificates and letters), /verify (accepts CERT- and LTR- ids).
Out of scope: message templates library, scheduled messages, SMS, WhatsApp document messages,
editing a certificate's text, certificates for cases that are not completed.

Database (0017_certificates_messages.sql)
- case_letters: id uuid PK, created_at,
  letter_id text NOT NULL UNIQUE CHECK (letter_id ~ '^LTR-[A-HJ-NP-Z2-9]{8}$'),
  application_id uuid NOT NULL UNIQUE FK applications ON DELETE RESTRICT,
  issued_by uuid NOT NULL FK admin_users ON DELETE RESTRICT (indexed),
  issued_at timestamptz NOT NULL DEFAULT now().
  Rows are only added (a trigger blocks UPDATE and DELETE). A letter is valid while its case is
  "completed"; if the case is reopened the letter shows as not valid (computed, never stored).
- notifications: ADD COLUMN attachment_kind text NULL CHECK (attachment_kind IN
  ('certificate', 'letter')), ADD COLUMN attachment_ref text NULL CHECK ((attachment_kind IS NULL)
  = (attachment_ref IS NULL)), ADD COLUMN sent_by uuid NULL FK admin_users ON DELETE RESTRICT
  (indexed). attachment_ref holds the certificate or letter id (CERT-/LTR-).
- message_batches: id uuid PK, created_at, module text NOT NULL CHECK (module IN ('course','study',
  'job','visa')), filters jsonb NOT NULL, channels text[] NOT NULL CHECK (channels <@
  ARRAY['email','whatsapp']::text[] AND cardinality(channels) > 0), subject text NOT NULL,
  body text NOT NULL, recipients integer NOT NULL CHECK (recipients >= 0), sent_by uuid NOT NULL FK
  admin_users ON DELETE RESTRICT (indexed). Append-only (trigger blocks UPDATE and DELETE).
  notifications ADD COLUMN batch_id uuid NULL FK message_batches ON DELETE RESTRICT (indexed).

Contract (all under /api; SA super admin, AD admin of that section, AP the applicant themself)
Channel = "email" | "whatsapp"
DocumentKind = "certificate" | "letter"
CertificateView: { kind: DocumentKind, id: string (CERT-/LTR-), module, holder_name, account_id
  (public id), title, subtitle, issued_at | null, approved: boolean, valid: boolean }
- GET  /admin/enrolments/{id}/certificate            SA, AD(course) -> CertificateView
- GET  /admin/enrolments/{id}/certificate.pdf        SA, AD(course) -> application/pdf (draft
       watermark until approved)
- POST /admin/enrolments/{id}/certificate/send       SA, AD(course) { channels: Channel[] }
       -> { queued: number }  (approved only, else CONFLICT)
- POST /admin/applications/{id}/letter               SA, AD -> CertificateView (case must be
       "completed", else CONFLICT; once per case; audit letter.issued; email + WhatsApp
       "Your completion letter is ready" to the client)
- GET  /admin/applications/{id}/letter               SA, AD -> CertificateView | null
- GET  /admin/applications/{id}/letter.pdf           SA, AD -> application/pdf (draft preview
       before issue)
- POST /admin/applications/{id}/letter/send          SA, AD { channels } -> { queued }
- GET  /me/course/enrolments/{id}/certificate.pdf    AP -> PDF (approved only, else NOT_FOUND)
- GET  /me/{module}/applications/{id}/letter.pdf     AP -> PDF (issued only, else NOT_FOUND)
- GET  /certificates/{id}                            public check, now also LTR- ids (module
       licensed, same rate limit as today)
- GET  /certificates/{id}/pdf?t=<token>              public, signed link from WhatsApp:
       HMAC-SHA256 with SECRET_KEY over the id and an expiry (30 days); wrong or expired token
       is NOT_FOUND; rate-limited like the check.
- POST /admin/messages                               SA, AD of the account's module
       { account_id (uuid), channels: Channel[], subject, body } -> { queued }
       A channel the client has no address for is skipped; none left = VALIDATION.
- POST /admin/messages/bulk/preview                  SA, AD { module, filters } -> { recipients,
       with_email, with_whatsapp }
- POST /admin/messages/bulk                          SA, AD { module, filters, channels, subject,
       body, expected_recipients } -> { batch_id, queued }. If the count changed since the
       preview: CONFLICT. At most 1000 recipients per batch.
  filters: { status?: AppStatus, stage?: number, item_id?: uuid (university, vacancy, visa
  programme or course), has_application?: boolean, enrolment_status? (course only) }
Rules: subject 1-200 characters (email only; WhatsApp sends "subject + body" in the template's
one variable, cut at 1000 characters), body 1-5000. Finance: FORBIDDEN on all of these.
Every send writes one audit row (message.sent / message.bulk_sent / certificate.sent /
letter.sent) in the same transaction as its notification rows. The worker sends them as today
(rate limits, retries, Notifications tab, resend).

Completion letter text (per module)
- study: "has completed the Student Consultancy process with {company} for {university},
  {country}." job: "...the Job Processing process ... for {job title} at {employer}, {country}."
  visa: "...the Immigration Processing ... for {programme} ({visa type}), {country}."
  Plus reference APP-..., completion date, letter id, verify address (/verify).

Frontend
- Admin Courses tab: each enrolment card gets "View certificate" (opens the PDF in a new tab),
  "Download PDF" and "Send" (dialog: email / WhatsApp / both).
- Case view (CasesTab), when the case is completed: "Issue completion letter"; once issued:
  View, Download PDF, Send. The "✉ Email applicant" dialog becomes "✉ Message applicant" with
  channel checkboxes.
- Accounts lists (every module tab, Training too): "Send message" per account.
- Every module tab: "Message a group" (filters as above, live recipient count from preview,
  channel choice, confirm "Send to N clients").
- Applicant profile: course certificate also downloads as PDF (the PNG stays); a completed case
  with a letter shows "Completion letter" with Download PDF.
- /verify accepts certificate and letter ids.
- Same look as the reference; works at 390px, light and dark.

Acceptance criteria
- b159 Staff of the section view and download a draft and an approved course certificate PDF;
  an applicant can download only their own approved one; finance is FORBIDDEN.
- b160 A letter can be issued only for a completed case, once; it shows valid at /verify and not
  valid after the case is reopened; its PDF has the module's text.
- b161 Sending a certificate queues an email with the PDF attachment and a WhatsApp text with a
  signed link; the link downloads the PDF; a changed or expired token is NOT_FOUND.
- b162 "Send message" queues one notification per chosen channel the client can receive, with
  sent_by; an admin of another section is FORBIDDEN; an unlicensed module is MODULE_NOT_LICENSED.
- b163 Bulk preview counts match the filters; bulk send queues exactly those recipients, one
  message_batches row and one audit row; a changed count is CONFLICT; over 1000 is VALIDATION.
- b164 case_letters and message_batches cannot be changed or deleted (triggers).
- All earlier tests still pass.

Assumptions
- PDF fonts: Sora (headings) and DM Sans (text) as on the site; Noto Sans Bengali is used for
  names in Bangla script. All three are SIL Open Font Licence and are committed with the licence.
- The PDF is generated when asked for and never stored on disk.
