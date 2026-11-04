Spec B11 - Course groups and Add course screens, Settings test buttons, end-to-end test

Purpose
Close the last gaps so a buyer can run the whole system from an empty database without a
developer: create course groups and courses, test that email and WhatsApp work from Settings,
and prove with one automatic browser test that a full day of real use works from start to end.

Scope
In scope - frontend:
- Catalog tab, Courses part: a "Course groups" list (name, description, order, active) with
  "+ Add group" and Edit; and "+ Add course" with the full form: group, title, icon (one emoji),
  colour, price (৳), duration, level, short description, "What you will learn" (one per line),
  syllabus modules (one per line), "Hide from website". Edit uses the same form. Layout follows
  the existing Catalog look in reference/nextgen-learning-v2.html.
- Settings tab: "Send test email" (asks for an address) under Email, and "Send test WhatsApp"
  (asks for a number) under WhatsApp; each shows "Sent ✓" or the backend's error message.
- Remove the F06 "fee is 0" path from the application page (fees are always above ৳0 now).
In scope - end-to-end test:
- backend/tests_e2e/ using Python Playwright (dev only) and psycopg. A runner script
  python -m tests_e2e.run starts the backend on port 8100 with DATABASE_URL = E2E_DATABASE_URL and
  APP_ENV=development and NOTIFY_WORKER=off, starts the frontend dev server on port 3100 pointing
  at it, runs the test, and stops both.
- The runner applies migrations to movewise_e2e first, and refuses to start unless the database
  name ends with "_e2e".
Out of scope: real gateway payments in the automatic test (manual checklist below), load testing,
deployment, the limited production database user (next spec).

Contract
- Uses the B04 admin course-group and course endpoints and the B08 test-email / test-WhatsApp
  endpoints. No backend change except what the E2E runner needs to start; if anything else seems
  needed, stop and tell me.
- New dev-only packages: playwright (Python) in backend/requirements-dev.txt. Ask before installing
  it and before running "playwright install chromium".

Functional rules
- Course group: name required (max 80), order is a whole number; a group with courses cannot be
  hidden while it still has published courses (show the backend's message).
- Course form validation shows the backend's messages next to the form; price is entered in taka
  and sent as poisha.
- The E2E test reads verification codes only from the notifications table of movewise_e2e. It
  never touches movewise or movewise_test.
- Every run uses new emails and names with a run number (for example student-<run>@example.com),
  so it can run again and again without cleaning the database. Nothing is deleted.
- The super admin: on the first run the test signs up E2E_ADMIN_EMAIL as the first admin and
  applies E2E_LICENCE_KEY; on later runs it signs in with them.

The end-to-end journey (one test, in this order, each step checks what the user sees)
1. Super admin signs in (or signs up on the first run), applies the licence, sets the company name,
   uploads a small PNG logo, turns on Bank transfer / office payment, saves Settings.
2. Creates a course group and a course (৳12,000), a university (Canada, Bachelor, Computer
   Science & AI) and a vacancy with a verified employer.
3. A visitor sends the Contact form; the enquiry appears in Enquiries.
4. A student signs up in Student Consultancy, verifies with the code from the database, uses the
   agent, opens the university, applies, uploads a PDF, and pays the fee by bank transfer with a
   reference.
5. A second admin signs up (pending); the super admin approves them with only the study section.
6. Finance: the super admin changes a third admin to Finance Officer; finance verifies the
   student's payment; the student sees "Fee paid" and the invoice.
7. The study admin moves the stage to "University review" with a note, verifies the PDF with an
   expiry, and emails the university; the student sees the stage, the note and "Verified".
8. A learner signs up in Courses, enrols, pays by bank transfer; finance verifies; the super admin
   approves the certificate; /verify shows it as valid.
9. The student requests a refund; finance approves it; the invoice shows Refunded and the ledger
   shows the money out.
10. Finance adds an expense and reverses it; the balance returns to the earlier value.
11. The super admin applies a "study only" licence key (made in the test with the test key pair is
    not possible - so this step uses a second key from E2E_LICENCE_KEY_STUDY if set, otherwise it
    is skipped and reported as SKIPPED).
12. The audit log shows the actions above with the right people.
At every step the test also checks there is no sideways scroll at 390px width on that page.

Edge cases
- If a step fails, the runner saves a screenshot and the page text to backend/tests_e2e/output/
  (in .gitignore) and stops both servers.
- If the backend or frontend does not start within 60 seconds, the runner stops with a clear message.

Non-functional rules
- Only the new dev package above. npm run build, npm run lint, npm test and backend pytest pass.

Acceptance criteria
- f04 Course groups and courses can be added and edited from the Catalog; a new course appears on
  the Courses page under its group.
- f05 Send test email and Send test WhatsApp show the backend's result.
- f06 python -m tests_e2e.run passes all steps (step 11 may be SKIPPED), twice in a row on the same
  movewise_e2e database.
- f07 The runner refuses a database whose name does not end in "_e2e".
- npm run build, npm run lint, npm test and backend pytest pass.

Assumptions
- Specs B01-B10 are complete and committed.
- movewise_e2e exists and the E2E_* lines are in backend/.env (added by hand).
