Spec B27 - Custom payments (any amount) for every service

Status: APPROVED by the owner on 2026-11-20 (all four Decisions answered yes, plus the EPS
retry change below).

Purpose
Today each case (application) and each course enrolment has exactly one fee: the normal fee, or
the fee the super admin set for that case (0022). Once it is paid nothing more can be charged.
B27 adds custom payments on top of that, for all five services (course, study, job, visa,
remote), in two ways:
1. Payment request: staff ask the applicant to pay a set amount for a reason, for example
   "Visa processing fee 25,000 taka". The applicant sees it in their profile and pays it.
2. Own amount: the applicant pays an amount they choose against one of their cases or course
   enrolments, for example a deposit or an instalment, with a short note.
A case can have any number of custom payments. The normal fee and everything that exists today
stays exactly as it is.
Custom payments use the existing payment service (B07), methods (EPS, SSLCommerz, bKash, manual -
only the ones switched on in Settings), invoices, ledger, refunds, notifications and audit.

Scope
In scope:
- db/migrations/0025_custom_payments.sql:
  - New table payment_requests:
    id uuid PK DEFAULT gen_random_uuid(), ref text NOT NULL UNIQUE ("PR-" + 6 characters),
    module text NOT NULL CHECK (module IN ('course','study','job','visa','remote')),
    applicant_id uuid NOT NULL -> applicant_accounts(id),
    application_id uuid NULL -> applications(id), enrolment_id uuid NULL -> enrolments(id),
    CHECK (exactly one of application_id / enrolment_id is set; enrolment only for course),
    kind text NOT NULL CHECK (kind IN ('requested','own')),
    description text NOT NULL (1..200 characters),
    amount_poisha bigint NOT NULL CHECK (amount_poisha > 0),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid','cancelled')),
    created_by_kind text NOT NULL CHECK (created_by_kind IN ('staff','applicant')),
    created_by_admin uuid NULL -> admin_users(id) (staff requests only),
    cancelled_at timestamptz NULL, paid_at timestamptz NULL,
    created_at, updated_at (+ trigger). Every foreign key indexed, ON DELETE RESTRICT.
  - payments.ref_type CHECK becomes ('application','enrolment','request'). Replacing a CHECK
    needs ALTER TABLE ... DROP CONSTRAINT ... ADD CONSTRAINT for this one constraint only
    (same pattern as 0016, 0021, 0024; needs the owner's yes, see Decisions 1).
  - No data rows.
- backend: app/routers/custom_payments.py (new), an on_paid handler for ref_type 'request',
  registered like the application and enrolment handlers; small additions where the case and
  enrolment views list payments.
- frontend:
  - Admin case card (CasesTab, all four case modules) and admin course enrolment view: a
    "Custom payments" block - list (ref, description, amount, status, invoice no) and a form
    "Request a payment" (description + amount in taka) with a Cancel button on open requests.
  - Applicant profile, on each case and course enrolment: "Payments due" (open requests, each
    with a Pay button) and "Pay another amount" (amount in taka + note), both opening the
    existing checkout (PaymentCheckout) with the methods switched on in Settings.
  - lib/api (types, http, mock) for the endpoints below.
- EPS start retries (owner's yes, 2026-11-20): EPS sometimes refuses a valid start with
  ErrorCode 500. backend/app/routers/pay.py tries up to 3 times in all (was 2), each with a new
  16-digit tran_id and a 1 second pause. The B26 test of the retry is updated to match.
- Tests (pytest and frontend unit tests) as in Acceptance criteria.
Out of scope: changing the normal fee rules, partial refunds, payment links by email or SMS,
recurring or scheduled instalments, discounts, new pages (everything sits inside existing
screens), new packages.

Contract (all under /api)
Staff:
- GET  /admin/payment-requests?module=&case_id=   -> {items: [request view]}
- POST /admin/payment-requests {module, case_id, description, amount_poisha}
  -> request view. case_id is an application id (study/job/visa/remote) or an enrolment id
  (course). Sends the applicant a notification "Payment requested - PR-XXXXXX".
- POST /admin/payment-requests/{id}/cancel  -> request view. Only an open request with no payment
  started or waiting for verification; otherwise CONFLICT 409. A started bKash / EPS payment is
  first checked with the gateway; a start nobody came back from for over an hour is closed as
  abandoned and then no longer blocks the cancel.
Applicant (signed in to that module):
- GET  /me/{module}/payment-requests  -> {items: [request view]} (own requests only)
- POST /me/{module}/payment-requests/{id}/pay {method, phone, manual_ref}
  -> same answer as the B07 pay endpoints ({payment_id, redirect_url} or
  {payment_id, status: "pending_verify"}).
- POST /me/{module}/own-payments {case_id, amount_poisha, note, method, phone, manual_ref}
  -> creates a request of kind 'own' (description = note, or "Payment" if empty) and starts
  its payment in the same transaction; same answer as above.
Request view: {id, ref, module, case_id, case_ref, kind, description, amount_poisha, status,
payment: {id, status, method} | null, invoice_no | null, created_at, paid_at}.
Error codes: existing only (UNAUTHENTICATED, MODULE_NOT_LICENSED, FORBIDDEN, VALIDATION,
CONFLICT, NOT_FOUND, INTERNAL for a gateway that does not answer). No new codes.

Functional rules
- Order of checks as always: signed in -> module licensed -> role and section -> input -> work.
- Who may request or cancel: see Decisions 2.
- Amounts: whole taka (amount_poisha % 100 = 0), at least 100 taka, at most 10,00,000 taka
  (Decisions 3). Shown as ৳ with thousands separators.
- The case must belong to the applicant and be active or on hold (course: enrolment not
  cancelled); otherwise CONFLICT.
- Paying uses start_payment (B07) with ref_type 'request', ref_id = request id, purpose =
  "<description> - <case title> (<case ref>) · PR-XXXXXX". Duplicate rules, refresh of an
  initiated payment, gateway return, verify / reject of manual payments: exactly as B07/B26.
- When the payment is paid: request status 'paid', paid_at set, one invoice and one ledger entry
  (category = module) as for any payment, an app_event on the case "Custom payment received
  (৳X, PR-XXXXXX)", notification to the applicant. The case's fee_paid and the enrolment status
  are NOT changed by a custom payment.
- A rejected or failed payment leaves the request open, so it can be paid again. An 'own' request
  whose payment failed, was cancelled or rejected is set to 'cancelled' (the applicant simply
  starts a new one).
- Every change writes one audit row in the same transaction: payment_request.created,
  payment_request.cancelled, payment_request.paid (plus the existing payment.* rows).
- Finance sees custom payments in Accounts like any other payment; no new screen.

Edge cases
- Two clicks on Pay for the same request: one live payment only (B07 lock rule).
- Staff cancel a request while the applicant is on the gateway page: refused (CONFLICT) because a
  payment has started.
- Gateway success arrives for an own-amount request already set to cancelled: recorded as paid
  (B07 late success rule) and the request becomes paid.
- Module licence switched off: the endpoints answer MODULE_NOT_LICENSED and the UI hides the block.

Acceptance criteria (tests)
- b281 Migration 0025 applies on movewise_test; a 'request' payment can be inserted; the
  payment_requests CHECKs refuse a row with both or neither case ids.
- b282 Staff create a request on a study case; the applicant lists it and pays it by manual;
  finance verifies; request paid, one invoice, one ledger row (category study), audit rows,
  fee_paid of the case unchanged.
- b283 Same for a course enrolment (pays by EPS with the fake transport).
- b284 Own amount on a visa case: created and paid; amount below 100 taka or not whole taka ->
  VALIDATION; someone else's case -> NOT_FOUND.
- b285 Cancel: open request -> cancelled; with a started payment -> CONFLICT.
- b286 Order of checks: not signed in 401, module off 403 MODULE_NOT_LICENSED, admin without the
  section 403, finance cannot create requests.
- b287 Many requests on one case, each with its own invoice.
- b288 All earlier tests still pass.
- Frontend: the request form refuses amounts below 100 or with poisha; "Payments due" shows only
  open requests; works at 390px and in dark mode.

Decisions for the owner (answer before building)
1. Migration 0025 replaces one CHECK (payments.ref_type) with DROP CONSTRAINT + ADD CONSTRAINT,
   like 0024 did. Allowed? (Proposed: yes, this one constraint only.)
2. Who may create and cancel payment requests? Proposed: super admin, and admins in the section
   of that service (the same people who handle the case). Finance: no.
3. Limits for the applicant's own amount: proposed minimum 100 taka, maximum 10,00,000 taka,
   whole taka only. Staff requests: same limits.
4. Order of work, as the owner asked: build and test on the live server first (after a database
   backup), then the same on localhost, then commit and git push.
