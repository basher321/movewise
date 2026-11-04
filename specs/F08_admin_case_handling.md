Spec F08 - Admin case handling for Student Consultancy and Job Processing

Purpose
Give staff one place per module to run every application: see the applicant and their answers,
move the stage with a note, pause / reject / complete it, assign it to a staff member, set the
deadline or the interview and offer, review documents, read the full history, and email the
applicant or the university / employer. Screens must look and behave like the Student
Consultancy and Job Processing tabs of the Admin panel in reference/nextgen-learning-v2.html,
including the v2 additions (filters, case box, documents, history).

Scope
In scope (one generic screen, configured per module, shown in the "🎓 Student Consultancy" and
"🛂 Job Processing" admin tabs):
- Summary cards: Applications (count) and "Fee paid · sent to admin" (count).
- Filter row: search (name, email, university / job, ref), status filter (default Active),
  assignment filter (Anyone / Assigned to me / Unassigned).
- One card per application, as in the reference: status badge, "Student" or "Job" badge,
  "Fee paid" / "Fee pending" badge, name, item title (+ employer for jobs), country, the key-value
  list (Ref, Account ID, Invoice, Applicant email, Phone, University / Employer email, then every
  agent answer), the "Processing stage" select, the buttons "✉ Email applicant" (or
  "✉ Email job holder") and "✉ Email university" (or "✉ Email employer"), and the list of
  emails already sent.
- Case box under each card (v2): Status, Assigned to, Application deadline (study) or Interview
  date & time, Interview result and Offered salary (job), "Reason / note to applicant", and
  "Save case". Then "Documents" with a missing-count badge and one row per uploaded document
  (status, View, Verify, Reject). Then "History (n)" that opens to show every event, with an
  "internal" badge on non-public ones. Then an "Add internal note" field.
- Stage dialog: opened when the stage select changes - title "Move to: <stage>", optional note
  to the applicant, "Email / WhatsApp the applicant about this change" (ticked by default),
  Save stage / Cancel. Cancel puts the select back.
- Verify document dialog with an optional expiry date; Reject document dialog with a required reason.
- Email dialog as in the reference: To, Subject, Message pre-filled from the reference templates
  (applicant update / provider letter with the applicant's details), "Send", "Copy text" and Cancel.
- Below the cards, the reference "<module> accounts (n)" table (Account ID, Name, Email) and
  "Invoices & confirmation emails (n)" table (Invoice, Customer, Confirmation email status,
  Amount, View, Resend).
Out of scope: Enquiries, the Documents tab, Notifications tab, Accounts (finance), Team,
Catalog, Fees, Audit (later specs). Bulk actions. Employer or university logins.

Contract
- Uses: listApplications, getApplication, changeStage, changeStatus, updateCase, addInternalNote,
  listDocuments, verifyDocument, rejectDocument, listAdmins (for the Assigned-to list),
  listInvoices, resendNotification, getSession.
- New actions (add to the contract, the mock and tests):
  sendCaseEmail(appId, to: "applicant" | "provider", subject, body) - S with that module section;
  writes a notification (email; plus WhatsApp for the applicant if they have a phone), a
  non-public history event "Email sent to <applicant|university|employer>: <subject>" and an
  audit entry. HTTP later: POST /admin/applications/{id}/email.
  listModuleAccounts(module) - S with that module section. HTTP later: GET /admin/accounts?module=.
- listApplications(module, filters) returns, for each application: application, applicant
  (name, email, phone, account id), item title / employer / country, provider email, invoice
  number, missing-document count, documents, full history, emails sent.

Functional rules
- Only admins with the module in their sections (and super_admin) see and use the tab; finance
  never sees it. Every action re-checks this in the api (FORBIDDEN otherwise).
- Stage change: allowed only while status is active; the last stage sets status Completed.
  If "Email / WhatsApp" is ticked, the applicant gets
  "Update on <ref>: <stage>" with the note. A public history event "Stage → <stage>" is added.
- Save case: compares old and new values and saves only what changed; if nothing changed,
  shows "Nothing changed." Status Rejected or On hold needs a reason (focus the note box and show
  the message). A status change sends the applicant "Your application <ref> is <status>"
  with the reason and adds a public history event. Other changes add one internal history event
  "Case updated: ..." listing the changes. Setting an interview date sends the
  "Interview scheduled" message to the applicant.
- Assigned to: lists approved admins who are not finance.
- Assigned-to-me filter uses the signed-in admin.
- Verify document: status verified, optional expiry saved, public history event
  "<type> verified". Reject: reason required; status rejected; public history event with the
  reason; the applicant is asked by email to upload again.
- History shows newest first, with date and time (Asia/Dhaka) and who did it.
- Email dialog: To must be a valid email; Subject and Message required. If the provider email is
  missing, the provider button shows "No email on file" and is disabled.
- After any action, the card list reloads and keeps the current filters and scroll position.

Edge cases
- No applications yet: the reference message "No applications yet. They appear here after a
  student or job seeker signs in and applies."
- Filters with no match: "No applications match these filters."
- Document uploaded while the admin has the tab open: it appears after the next reload or action.
- Application whose item was deleted: shows "(removed)" as the title and still works.
- Module becomes unlicensed while the tab is open: the next action shows the 403 banner and the
  tab disappears.

Non-functional rules
- One generic case-screen component configured by module (reuse src/config/modules/).
- No new packages. Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference admin tab; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t30 sendCaseEmail by an admin without that section is FORBIDDEN; with it, a notification, a
  non-public history event and an audit entry are written.
- t31 updateCase with no changes writes no history and no audit entry.
- t32 listModuleAccounts("study") returns only Student Consultancy accounts.
- Manual checks (use the application made in F06 and the one in F07):
  - Study tab shows the student card with all answers, the fee badge and the invoice number.
  - Move the stage with a note -> the applicant's application page shows the new stage and the
    note in History; a notification exists.
  - Cancel in the stage dialog puts the select back.
  - Set On hold without a reason -> message; with a reason -> applicant sees the banner.
  - Assign to another admin; "Assigned to me" filter shows only that admin's cases.
  - Job tab: set an interview date -> applicant's Status card shows it and gets the message.
  - Verify a document with an expiry -> applicant sees Verified; reject another with a reason
    -> applicant sees Rejected and "Upload again".
  - Email university opens a pre-filled letter; Send writes it to the history as internal.
  - An admin with only the study section does not see the Job Processing tab; a finance user
    sees neither tab.
  - Accounts and Invoices tables at the bottom match the reference.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F07 are complete and committed.
- Email templates and table layouts are copied from the reference (tmpl, openMail, secExtra).
