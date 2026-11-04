Spec B05 - Applications, stages, status, case handling, history and case emails

Purpose
Store every Student Consultancy and Job Processing application and everything that happens to
it: the applicant's answers, the stage, the status, who handles it, the deadline or interview and
offer, a history that can never be changed, and emails to the applicant or the university /
employer. Endpoints follow the apply and cases parts of specs/F02_api_contract_mock.md, F06,
F07 and F08.

Scope
In scope:
- db/migrations/0005_applications.sql:
  - applications: id, ref (APP- + 6 characters, unique), module CHECK ('study','job'),
    applicant_id, university_id, vacancy_id (exactly one set, matching the module - CHECK),
    stage int, status CHECK ('active','on_hold','rejected','withdrawn','completed'),
    assigned_to (admin id, nullable), deadline date, interview_at timestamptz,
    interview_result CHECK ('pending','passed','failed'), offered_salary_usd, fee_paid boolean
    default false, answers jsonb, created_at, updated_at.
    A partial unique index allows only one active or on_hold application per applicant and item.
  - app_events: id, application_id, at, by_kind ('applicant','admin','system'), by_id, by_name,
    text, note, public boolean. Triggers block UPDATE and DELETE.
- app/stages.py: stage names and stageCount per module, copied from the reference
  (study 9 stages, index 0-8; job 8 stages, index 0-7). Required document lists per module
  (used by B06) live here too.
- Routers for applicants and admins (below). Notifications are written to the outbox from B03.
- The B04 "already applied" exception for public item pages.
Out of scope: documents and uploads (B06), payments and fee_paid becoming true (B07 - until then
fee_paid stays false), real sending of email / WhatsApp (B08), enrolments (B09).

Contract (all under /api)
Applicant (A, module licensed, signed in to that module):
- POST /me/{module}/applications {item_slug, answers} -> the application (new, or the existing
  active / on-hold one for that item).
- GET  /me/{module}/applications -> list with item title, country, stage, stage name, stage count,
  status, fee_paid.
- GET  /me/{module}/applications/{id} -> application, item, stages, public history (newest
  first), assigned advisor name, fee_poisha (effective fee now, until paid), apply_link
  (study only, and only when fee_paid is true; never for job), interview and offer fields (job).
  Documents, payment and invoice are added by B06 and B07.
- POST /me/{module}/applications/{id}/withdraw
Admin (require_section(module)):
- GET  /admin/applications?module=&q=&status=&assigned=me|none|<admin id>&page=  (50 per page)
  -> each row: application, applicant (name, email, phone, public id), item title / employer /
  country, provider email, answers, history (all events), emails sent.
- GET  /admin/applications/{id}
- POST /admin/applications/{id}/stage {stage, note, notify}
- POST /admin/applications/{id}/status {status, reason}
- PATCH /admin/applications/{id} {assigned_to?, deadline?, interview_at?, interview_result?,
  offered_salary_usd?}
- POST /admin/applications/{id}/notes {note}
- POST /admin/applications/{id}/email {to: "applicant"|"provider", subject, body}
- GET  /admin/accounts?module= -> applicant accounts of that module (public id, name, email,
  phone, created_at).
- An applicant can read only their own applications (another id is 404, never 403, so ids
  cannot be guessed). An admin without the module section gets FORBIDDEN.

Functional rules
- Starting an application: the item must be visible to the public at that moment (published /
  open and verified). answers may contain only the agent fields of that module (study: level,
  field, gpa, ielts, budget_usd; job: occupation, country, experience, education, english,
  passport_ready, salary_goal_usd) with the right types; anything else is VALIDATION. Max 4 KB.
- New application: stage 0, status active, interview_result pending, public event
  "Application started", notification "Application received - <ref>" with the fee to pay.
- Stage change (admin): only while status is active (CONFLICT otherwise); stage must be 0 to
  stageCount-1 (VALIDATION otherwise); moving to the last stage sets status completed. Adds a
  public event "Stage -> <name>" with the note. If notify is true, the applicant gets
  "Update on <ref>: <stage name>".
- Status change (admin): allowed values active, on_hold, rejected, completed. on_hold and
  rejected need a reason (VALIDATION). Reopening a rejected or completed application to active
  needs a reason too. withdrawn can be set only by the applicant, and a withdrawn application
  cannot be reopened. Adds a public event "Status -> <status>" with the reason and notifies the
  applicant.
- Withdraw (applicant): only from active or on_hold; public event "Withdrawn by applicant".
- PATCH: saves only fields that changed; if nothing changed, returns 200 with changed: [] and
  writes nothing. assigned_to must be an approved, active admin who is not finance and has the
  module in sections (or a super_admin). interview_at is given and shown in Asia/Dhaka time.
  Setting a new interview_at notifies the applicant "Interview scheduled - <ref>". Changes add one
  internal event "Case updated: <list>".
- Internal note: internal event "Internal note" with the text.
- Case email: "applicant" goes to the applicant's email (and WhatsApp if they have a phone);
  "provider" goes to the university admissions_email or the vacancy employer_email - VALIDATION
  "No email on file" if missing. Subject and body required (body max 10,000 characters). Adds an
  internal event "Email sent to <applicant|university|employer>: <subject>".
- Every change locks the application row while it works (no lost updates from two staff at once)
  and writes exactly one audit row in the same transaction.
- Public item pages (B04 change): GET /universities/{slug} and /vacancies/{slug} also return a
  hidden, closed or unverified item if the signed-in applicant has an application for it.
- applied_count in the B04 admin lists now counts applications that are not withdrawn.
- History events and audit rows are never changed or deleted.

Edge cases
- Item hidden or closed after the person applied: their application keeps working; the item
  title is still shown.
- Applying again to the same item while the old application is rejected, withdrawn or completed:
  a new application is created.
- Assigned admin later deactivated: the application keeps the name in history; assigned_to is
  shown as "(deactivated)" and can be changed.
- Module unlicensed later: every endpoint for that module returns 403; data stays.

Non-functional rules
- No new packages. List endpoints use indexes on (module, status), applicant_id, assigned_to.
- pytest passes, including all earlier tests.

Acceptance criteria
- b45 Migration 0005 applies; UPDATE or DELETE on app_events fails.
- b46 Applying twice to the same item returns the same application; after withdrawing, applying
  again creates a new one.
- b47 answers with an unknown key or a wrong type is VALIDATION.
- b48 An applicant reading another applicant's application gets 404.
- b49 apply_link is not in the study detail while fee_paid is false (set it true directly in the
  test database to check it appears); a job detail never has apply_link.
- b50 Stage: study 8 sets completed; job 7 sets completed; job 8 is VALIDATION; a stage change on
  an on_hold application is CONFLICT.
- b51 Status rejected without a reason is VALIDATION; with a reason it adds a public event and an
  outbox notification; an admin cannot set withdrawn; a withdrawn application cannot be reopened.
- b52 PATCH with no changes writes no event and no audit row; assigning a finance user is VALIDATION.
- b53 Case email to the provider without a provider email is VALIDATION; with one, an outbox row
  and an internal event are written.
- b54 An admin with sections ["study"] gets FORBIDDEN on job applications; finance gets FORBIDDEN on both.
- b55 A hidden university is returned by GET /universities/{slug} only to an applicant who applied to it.
- b56 Two stage changes on the same application at the same moment both finish without losing
  either event.
- b57 Every successful change writes exactly one audit row.

Assumptions
- Specs B01-B04 are complete and committed.
- Stage names and document lists are copied from the reference (ST, JT, DOCS).
