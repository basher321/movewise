Spec F02 - API contract, mock data layer and licence lock

Purpose
Define every piece of data the system uses and every action the screens can ask for, in one
place (frontend/src/lib/api/). For now the actions run against a mock store in the browser, so
the frontend can be built and tested before the backend exists. Later the backend implements
the same contract, and only the inside of this folder changes. This spec also adds the licence
lock and role checks to the data layer, the second of the two places where the licence is
enforced.

Scope
In scope:
- frontend/src/lib/api/types.ts      All data types and fixed value lists.
- frontend/src/lib/api/errors.ts     ApiError and the error codes.
- frontend/src/lib/api/storage.ts    Storage adapter: browser localStorage, and in-memory for tests.
- frontend/src/lib/api/licence.ts    Licence key check (mock version).
- frontend/src/lib/api/guard.ts      requireLogin, requireRole, requireModule, requireSection.
- frontend/src/lib/api/seed.ts       Starting data copied from reference/nextgen-learning-v2.html.
- frontend/src/lib/api/mock/*.ts     Mock implementation of every action in the Contract.
- frontend/src/lib/api/index.ts      The only file pages may import from.
- Unit tests with Vitest (the only new package, as a dev dependency) in frontend/src/lib/api/__tests__/.
Out of scope: any page or UI change, real HTTP calls, real payment gateways, real email or
WhatsApp, AI agents, file storage outside the browser. These come in later specs.

Contract

1. Fixed value lists (string unions)
- Module: "course" | "study" | "job"
- AdminRole: "super_admin" | "admin" | "finance"
- AppStatus: "active" | "on_hold" | "rejected" | "withdrawn" | "completed"
- StudyStage (index 0-8): Application started, Documents submitted, University review,
  Offer letter received, Tuition deposit & confirmation, Visa application,
  Visa interview / biometrics, Visa decision, Ready to fly
- JobStage (index 0-8): copy the job stage names exactly from the reference (JT list).
- PaymentMethod: "sslcommerz" | "bkash" | "nagad" | "manual"
- PaymentStatus: "unpaid" | "pending_verify" | "paid" | "failed" | "rejected" | "refunded"
- DocStatus: "pending" | "verified" | "rejected" | "replaced"
  (shown status "expiring" = verified and expiry within 60 days; "expired" = verified and past expiry;
  these two are computed, never stored)
- RefundStatus: "requested" | "approved" | "declined"
- EnquiryStatus: "new" | "contacted" | "converted" | "closed"
- Channel: "email" | "whatsapp";  NotifyStatus: "sent" | "queued" | "failed"
- InterviewResult: "pending" | "passed" | "failed"

2. Data types (all ids are strings; all money fields end in _poisha and are whole numbers)
- Settings: name, tagline, brand_color, logo (data URL or ""), hero_image, hero_title, hero_text,
  stats (3 x {number,label}), about_title, about_text, address, phone, email, hours, facebook,
  website, invoice_prefix, invoice_footer, vat_bin, gateways {sslcommerz, bkash, nagad: {enabled,
  sandbox, key fields}, manual: {enabled, instructions}}, mail {sender_name, sender_email, api_key},
  whatsapp {number, token}
- PublicSettings: Settings without any key, password, token or api_key field.
- Licence: key, modules {course, study, job: boolean}, activated_at
- AdminUser: id, name, email, role, approved, sections (Module[]), created_at
- ApplicantAccount: id (prefix by module: CRS-, STU-, JOB- + 6 chars), module, name, email, phone,
  country, email_verified, created_at
- Course: id, title, category, price_poisha, duration, level, description, syllabus (string[]),
  colour, published
- Enrolment: id, account_id, course_id, order_no, paid_poisha, method, certificate_id,
  certificate_approved, enrolled_at
- University: id, name, country, city, levels, fields, tuition_usd, min_gpa, min_ielts, intakes,
  deadline_text, app_fee_poisha, scholarships, work_rights, conditions, apply_link,
  admissions_email, published
- Vacancy: id, title, employer, country, occupation, min_experience, min_education (index),
  min_english (index), salary_usd, seats, apply_by, app_fee_poisha, contract, benefits,
  conditions, employer_licence, employer_email, employer_verified, closed
- Application: id, ref (APP- + 6 chars), module ("study" | "job"), account_id, item_id, stage,
  status, assigned_to (admin id or null), deadline, interview_at, interview_result,
  offered_salary_usd, fee_paid, answers (the apply form values), created_at, updated_at
- AppEvent: id, application_id, at, by_name, text, note, public
- Document: id, application_id, account_id, type, file_name, size_bytes, data (data URL, only
  if 400 KB or smaller), status, expiry, note, uploaded_at, reviewed_by
- Payment: id, account_id, module, purpose, ref_type ("enrolment" | "application" | "other"),
  ref_id, amount_poisha, method, txn_ref, status, invoice_no, created_at, paid_at
- Invoice: no, payment_id, account_id, name, email, description, method, amount_poisha, issued_at,
  refunded
- Refund: id, invoice_no, account_id, amount_poisha, reason, status, decided_by, decision_note,
  refund_ref, requested_at, decided_at
- LedgerEntry: id, at, direction ("in" | "out"), category, party, description, method,
  amount_poisha, ref, auto
- Notification: id, at, channel, to, to_name, module, event, subject, body, status, tries
- Enquiry: id, at, name, contact, interest, preferred_date, message, status, assigned_to, notes
- AuditEntry: id, at, by_name, by_role, action, detail

3. Errors - every action either returns its result or throws ApiError {code, status, message}
- UNAUTHENTICATED 401, FORBIDDEN 403, MODULE_NOT_LICENSED 403, NOT_FOUND 404,
  CONFLICT 409, VALIDATION 422 (message names the field), EXPIRED 410, TOO_MANY_TRIES 429

4. Actions (each is an async function; the HTTP column is the endpoint the backend will build later)
Who: P = public, A = signed-in applicant, S = signed-in admin with the needed role/section,
SA = super_admin only, F = super_admin or finance.

| Group | Function | HTTP | Who | Module |
| settings | getPublicSettings() | GET /settings/public | P | - |
| settings | getSettings() / saveSettings(s) | GET, PUT /settings | SA | - |
| licence | getLicence() | GET /licence | P (modules only) | - |
| licence | applyLicenceKey(key) | PUT /licence | SA | - |
| auth | applicantSignUp(module, name, email, password) | POST /auth/applicant/signup | P | yes |
| auth | sendEmailCode(module, email) / verifyEmail(module, email, code) | POST /auth/applicant/verify | P | yes |
| auth | applicantSignIn(module, email, password) | POST /auth/applicant/signin | P | yes |
| auth | requestPasswordReset(module, email) / resetPassword(module, email, code, newPassword) | POST /auth/applicant/reset | P | yes |
| auth | adminSignUp(name, email, password) / adminSignIn(email, password) | POST /auth/admin/* | P | - |
| auth | signOut(), getSession() | POST /auth/signout, GET /auth/session | P | - |
| catalog | listCourses() / getCourse(id) | GET /courses | P | course |
| catalog | listUniversities() / getUniversity(id) | GET /universities | P | study |
| catalog | listVacancies() / getVacancy(id) | GET /vacancies | P | job |
| catalog | saveCourse / saveUniversity / saveVacancy | PUT /catalog/... | SA | matching |
| match | matchUniversities(input) / matchVacancies(input) | POST /match/{module} | P | matching |
| course | enrol(courseId, method, txnRef?) | POST /enrolments | A | course |
| course | myEnrolments() | GET /me/enrolments | A | course |
| course | approveCertificate(enrolmentId) | POST /enrolments/{id}/certificate | S | course |
| course | verifyCertificate(certificateId) | GET /certificates/{id} | P | course |
| apply | startApplication(module, itemId, answers) | POST /applications | A | yes |
| apply | myApplications() / getMyApplication(id) | GET /me/applications | A | yes |
| apply | payApplicationFee(appId, method, phone, txnRef?) | POST /applications/{id}/pay | A | yes |
| apply | withdrawApplication(appId) | POST /applications/{id}/withdraw | A | yes |
| cases | listApplications(module, filters) / getApplication(id) | GET /admin/applications | S | yes |
| cases | changeStage(appId, stage, note, notify) | POST /admin/applications/{id}/stage | S | yes |
| cases | changeStatus(appId, status, reason) | POST /admin/applications/{id}/status | S | yes |
| cases | updateCase(appId, {assigned_to, deadline, interview_at, interview_result, offered_salary_usd}) | PATCH /admin/applications/{id} | S | yes |
| cases | addInternalNote(appId, note) | POST /admin/applications/{id}/notes | S | yes |
| docs | uploadDocument(appId, type, file) | POST /applications/{id}/documents | A | yes |
| docs | listDocuments(filter) | GET /admin/documents | S | licensed only |
| docs | verifyDocument(docId, expiry?) / rejectDocument(docId, reason) | POST /admin/documents/{id}/... | S | yes |
| money | listPendingPayments() / verifyPayment(id) / rejectPayment(id, reason) | /admin/payments | F | - |
| money | requestRefund(invoiceNo, reason) | POST /refunds | A | - |
| money | listRefunds() / approveRefund(id, method, ref) / declineRefund(id, reason) | /admin/refunds | F | - |
| money | listOutstanding() / sendPaymentReminder(accountId) | /admin/outstanding | F | - |
| money | listLedger(filter) / addLedgerEntry(entry) | /admin/ledger | F | - |
| money | listInvoices(filter) / myInvoices() | GET /invoices | F or A | - |
| notify | listNotifications(filter) / resendNotification(id) | /admin/notifications | S (any role) | - |
| enquiry | submitEnquiry(form) | POST /enquiries | P | - |
| enquiry | listEnquiries(filter) / addEnquiry / updateEnquiry(id, changes) | /admin/enquiries | S (not finance) | - |
| team | listAdmins() / approveAdmin(id) / setRole(id, role) / setSections(id, modules) / removeAdmin(id) | /admin/team | SA | - |
| audit | listAudit(search) | GET /admin/audit | SA | - |

Functional rules
- Order of checks inside every action: signed in (if needed) -> module licensed (if the action
  belongs to a module) -> role and section -> input valid -> do the work.
- An action for an unlicensed module throws MODULE_NOT_LICENSED even for a super_admin.
- Licence key (mock): format LIC-<letters>-<6 digits>, letters are any of C (course), S (study),
  J (job), each at most once. The 6 digits are a checksum computed the same way as keyFor() in
  the reference. Any other key is VALIDATION. The default installation key is all three modules.
  (The real backend will use a signed key; only licence.ts changes then.)
- The first admin who signs up becomes super_admin and approved. Later admins are unapproved
  with role admin until a super_admin approves them. Unapproved admins cannot sign in (FORBIDDEN).
- An admin (role "admin") can act only in modules listed in their sections. Finance can act only
  in the money and notify groups.
- There must always be at least one approved super_admin; removing or demoting the last one is
  CONFLICT.
- Applicant accounts belong to one module. The same email may have one account per module.
  Sign-up in a module where that email already exists is CONFLICT.
- New applicant accounts are not verified. Sign-in with a correct password but unverified email
  throws FORBIDDEN with code text "EMAIL_NOT_VERIFIED" in the message, and a new code is sent.
- Codes are 6 digits, valid 15 minutes, at most 5 wrong tries (then TOO_MANY_TRIES and the code
  is deleted). An expired code is EXPIRED. In the mock, the code is written to the notification
  log so tests and the demo can read it.
- Passwords: at least 6 characters. Mock stores only a hash, never the plain password.
- An applicant can have only one active or on-hold application per item; starting another for
  the same item returns the existing one.
- A university or vacancy that is unpublished, closed, or (for vacancies) has an unverified
  employer is hidden from list/get/match for the public, but still visible to admins and to an
  applicant who already applied to it.
- Paying by sslcommerz, bkash or nagad in the mock succeeds immediately unless txnRef is
  "FAIL" (then status failed, nothing is charged, nothing is written to the ledger).
- Paying by manual requires txnRef and creates status pending_verify. Only verifyPayment turns
  it into paid.
- When a payment becomes paid, in this order: payment.status = paid, invoice created with the
  next number <invoice_prefix>-<year>-<4 digits>, ledger "in" entry written, the enrolment is
  created or application.fee_paid = true, a history event is added, a notification is sent,
  an audit entry is written.
- A payment that is already paid or pending_verify cannot be paid again (CONFLICT). No double charge.
- Only gateways enabled in Settings may be used; others are VALIDATION.
- Approving a refund marks the invoice refunded, the payment refunded, and writes a ledger "out"
  entry. A refund can be requested once per invoice.
- changeStage: stage must be 0..8; moving to the last stage sets status completed. Only active
  applications can change stage (CONFLICT otherwise).
- changeStatus to rejected or on_hold needs a reason (VALIDATION). The reason is a public
  history event and is sent to the applicant.
- Document upload: only pdf, jpg, jpeg, png; max 2 MB (VALIDATION). Uploading the same type again
  marks the older one replaced. Only the owner and admins with access to that module can see it.
- Every change of data writes one audit entry. Audit entries can never be changed or deleted.
- Notifications: email status is "sent" if Settings has a sender email, else "queued";
  WhatsApp is sent only if the person has a phone, and is "sent" if Settings has a WhatsApp
  number, else "queued". resendNotification re-checks and increments tries.
- getPublicSettings never returns key, password, token or api_key fields.
- Seed: courses, universities, vacancies and the default settings are copied from the reference
  file, with taka converted to poisha. No applicant, admin or payment is seeded.

Edge cases
- Browser storage full: the action throws VALIDATION "Storage is full" and nothing is half-saved.
- Corrupt or missing stored data: the store resets that collection to the seed, never crashes.
- Two quick clicks on pay: the second call gets CONFLICT.
- Email matching is case-insensitive and trims spaces.
- Changing the licence while signed in: the very next action on a removed module is refused.

Non-functional rules
- Pages and components import only from src/lib/api/index.ts, never from mock/ or storage.ts.
- No any type. TypeScript strict passes.
- Every action is async, even in the mock, so the backend can replace it without page changes.
- The mock waits 0 ms in tests and about 150 ms in the browser, to behave like a network.
- Vitest is the only new package (dev dependency). npm run build, npm run lint and npm test pass.

Acceptance criteria (each is one Vitest test, run with the in-memory storage)
t01 getPublicSettings returns the reference company name and no secret fields.
t02 With licence "study only", listCourses and listVacancies throw MODULE_NOT_LICENSED and
    listUniversities works - also when signed in as super_admin.
t03 applyLicenceKey with a wrong checksum throws VALIDATION; with a valid key it changes modules.
t04 First adminSignUp gives an approved super_admin; second gives an unapproved admin who
    cannot sign in until approved.
t05 Removing or demoting the last super_admin throws CONFLICT.
t06 An admin with sections ["study"] can list study applications and gets FORBIDDEN for job.
    A finance user gets FORBIDDEN for listApplications and works for listPendingPayments.
t07 Applicant sign-up then sign-in before verifying is refused; after verifyEmail with the
    code from the notification log, sign-in works. 6 wrong codes give TOO_MANY_TRIES.
t08 Same email can sign up in study and job, but twice in study gives CONFLICT.
t09 startApplication twice for the same item returns the same application id.
t10 payApplicationFee with bkash makes fee_paid true, creates invoice <prefix>-<year>-0001,
    a ledger "in" entry with the fee in poisha, a notification and an audit entry.
t11 Paying the same application again throws CONFLICT; txnRef "FAIL" leaves status failed and
    no ledger entry.
t12 Manual payment is pending_verify; verifyPayment makes it paid with the same side effects as t10.
t13 changeStage to 8 sets status completed; changeStage on a withdrawn application is CONFLICT.
t14 changeStatus to rejected without a reason is VALIDATION; with a reason it adds a public
    history event and a notification.
t15 Uploading a 3 MB file or a .exe is VALIDATION; uploading the same type twice marks the
    first one replaced.
t16 A verified document with expiry 30 days ahead shows as expiring; with a past date, expired.
t17 Approving a refund marks the invoice refunded and adds a ledger "out" entry; a second refund
    request for the same invoice is CONFLICT.
t18 A vacancy with an unverified employer is hidden from listVacancies and matchVacancies.
t19 Every action that changes data adds exactly one audit entry; there is no function that edits
    or deletes audit entries.
t20 Pages import only from src/lib/api/index.ts (a test scans src/app and src/components for
    imports of lib/api/mock or lib/api/storage and fails if any exist).

Assumptions
- Spec F01 is complete and committed.
- reference/nextgen-learning-v2.html is the source for seed data and stage names.
- The real backend (B-series specs) will follow this contract exactly.
