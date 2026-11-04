Spec B09 - Course enrolments, certificates, public certificate check, enquiries, audit list

Purpose
Let learners enrol in a course and pay through the B07 payment engine, let staff approve
certificates, let anyone check a certificate ID, capture enquiries from the Contact page and
follow them up, and give the Super Admin the read-only audit list. Endpoints follow the course,
enquiry and audit parts of specs/F02_api_contract_mock.md, F05 and F10.

Scope
In scope:
- db/migrations/0009_enrolments_enquiries.sql:
  - enrolments: id, order_no (ORD- + 6 characters, unique), applicant_id (a course account),
    course_id, price_poisha (locked when the enrolment starts), status CHECK
    ('awaiting_payment','active','completed','cancelled'), certificate_id (CERT- + 8 characters,
    unique, set when it becomes active), certificate_approved boolean, certificate_approved_by,
    certificate_approved_at, created_at, updated_at. A partial unique index allows only one
    enrolment per applicant and course that is not cancelled. DELETE blocked.
  - enquiries: id, name, contact, interest, preferred_date, message, status CHECK
    ('new','contacted','converted','closed'), assigned_to, ip, created_at, updated_at.
    DELETE blocked.
  - enquiry_notes: id, enquiry_id, at, by_id, by_name, text. UPDATE and DELETE blocked.
- B07 additions: an on_paid handler for ref_type 'enrolment' and an on_refunded handler
  registry (applications: nothing; enrolments: status cancelled).
- Endpoints below.
Out of scope: lessons, videos, attendance, quizzes, drawing the certificate image (the frontend
draws it), course reviews.

Contract (all under /api)
Learner (A, module course licensed, own records only - otherwise 404):
- POST /me/course/enrolments {course_slug, method, phone, manual_ref?}
  -> {enrolment, payment_id, redirect_url?} (same payment rules as B07)
- GET  /me/course/enrolments -> each: order_no, course (title, duration, level, icon, colour),
  price_poisha, status, payment status, method, enrolled date, certificate_id (only when active or
  completed), certificate_approved, certificate_approved_at.
Staff (require_section("course")):
- GET  /admin/enrolments?q=&status=&page=  (50 per page) - learner name / email / public id,
  course title, order no, price, payment status, date, certificate id and approval.
- POST /admin/enrolments/{id}/approve-certificate
Public (module course licensed):
- GET  /certificates/{certificate_id} -> {valid: true, name, course_title, duration, level,
  issued_at} or 404 NOT_FOUND. Never any other personal data.
Enquiries:
- POST /enquiries {name, contact, interest, preferred_date?, message?, website?}   P
- GET  /admin/enquiries?status=&q=&page=   admin or super_admin (not finance)
- POST /admin/enquiries {name, contact, interest, message?}        same
- PATCH /admin/enquiries/{id} {status?, assigned_to?}               same
- POST /admin/enquiries/{id}/notes {text}                           same
Audit:
- GET /admin/audit?q=&page= -> {rows, total} 50 per page, newest first        SA
  (no other audit route exists; nothing can change audit rows)

Functional rules
Enrolments
- Starting: the course must be published. If the learner already has an active or completed
  enrolment for that course: CONFLICT "You already have this course." If one is
  awaiting_payment with a payment that is paid or pending_verify: CONFLICT "A payment for this
  course is waiting for verification." If one is awaiting_payment with no open payment, it is
  reused (same order_no) and a new payment is started.
- The price is the course price at the moment the enrolment is created and never changes.
- on_paid: status active, certificate_id created, public notification "You are enrolled in
  <course>" (invoice notification comes from B07).
- on_refunded: status cancelled; a cancelled enrolment's certificate is never valid.
- Approve certificate: only for active or completed enrolments not yet approved (CONFLICT
  otherwise); sets completed, approved, who and when; notification "Your certificate is ready";
  audit row.
- Certificate check: valid only if approved and not cancelled. Rate limit: 60 checks per minute
  per IP (TOO_MANY_TRIES). Matching ignores case.
Enquiries
- name (max 120) and contact required; contact must be a valid email or Bangladeshi / international
  phone; interest is one of the licensed modules or "other"; message max 2,000 characters;
  preferred_date, if given, is today or later.
- website is a hidden "honeypot" field: if it is filled, answer 200 as if saved but save nothing
  (stops simple bots).
- Rate limit: 5 enquiries per IP per hour (TOO_MANY_TRIES). The same name + contact + message
  within 2 minutes is saved once.
- A new enquiry queues "New enquiry from <name>" to the company email (via queue_message).
- assigned_to must be an approved, active admin who is not finance (or a super_admin).
- Notes are added, never changed or removed; each records who and when.
General
- Every change writes exactly one audit row in the same transaction (public enquiries use the
  actor "Visitor"; payment-driven changes use "System").

Edge cases
- Course hidden after someone enrolled: their enrolment and certificate keep working.
- Training module unlicensed: learner, staff and certificate endpoints return 403; enquiries with
  interest "course" are refused as VALIDATION, older ones stay.
- Learner account in another module cannot enrol (enrolments belong to course accounts only).
- Approving a certificate twice quickly: one succeeds, the other is CONFLICT.

Non-functional rules
- No new packages.
- pytest passes, including all earlier tests.

Acceptance criteria
- b97 Migration 0009 applies; DELETE on enrolments and enquiries fails; UPDATE on enquiry_notes fails.
- b98 Enrol with fake bKash success -> active, certificate_id set, invoice and ledger entry exist;
  enrolling again is CONFLICT.
- b99 Manual payment -> awaiting_payment; GET /me/course/enrolments shows it with payment
  pending_verify; finance verify -> active.
- b100 A course price change after the enrolment started does not change price_poisha or the payment.
- b101 Certificate check is 404 before approval, valid after approval, 404 after a refund is
  approved; the answer contains only the listed fields.
- b102 61 certificate checks in one minute from one IP give TOO_MANY_TRIES.
- b103 Approve certificate by an admin without the course section is FORBIDDEN; on an
  awaiting_payment enrolment it is CONFLICT.
- b104 Enquiry with the honeypot filled saves nothing but answers 200; the 6th enquiry in an hour
  from one IP is TOO_MANY_TRIES; a duplicate within 2 minutes is saved once.
- b105 A new enquiry queues a message to the company email; finance gets FORBIDDEN on admin
  enquiry endpoints.
- b106 Enquiry notes cannot be changed or deleted; assigning a finance user is VALIDATION.
- b107 GET /admin/audit returns 50 rows per page newest first with the total; an admin (not super)
  gets FORBIDDEN; the test confirms no route changes audit rows.
- b108 Every successful change writes exactly one audit row.

Assumptions
- Specs B01-B08 are complete and committed.
