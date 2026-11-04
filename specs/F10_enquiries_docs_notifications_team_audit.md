Spec F10 - Enquiries, Documents, Notifications, Team and Audit log tabs; Contact form

Purpose
Finish the everyday admin tools: capture every website enquiry and follow it up, review all
uploaded documents in one list and catch expiring ones, see every email and WhatsApp message
and its delivery status, control who works in the panel and what they can open, and see an
unchangeable record of who did what. Screens must look and behave like the Enquiries, Documents,
Notifications, Team and Audit log tabs and the Contact form in reference/nextgen-learning-v2.html.

Scope
In scope:
- Contact page form (/contact): Full name, Phone or email, Interested in (licensed modules +
  Other), Preferred date, Your question, Send. Saves an enquiry and shows the thank-you message.
- "💬 Enquiries" tab (super_admin and admin): status filter, "+ Add enquiry" button, table with
  Received, Name (+ contact), Interest (+ preferred date), Message (+ notes), Status (+ assigned
  person), and "Update" (dialog: status, assigned to, add a note).
- "📄 Documents" tab (super_admin and admin): filter Waiting review / Expiring in 60 days /
  Expired / Rejected / Verified / All; each row shows person, email, application ref and title,
  then the document row with View, Verify (optional expiry), Reject (reason) - same dialogs as F08.
  Only documents of modules the admin may open are listed.
- "🔔 Notifications" tab (every admin role): banner when email sending is not set up, channel
  filter (All / Email / WhatsApp), status filter (All / Delivered / Queued / Failed), search,
  table with Time, Channel, To, Message, Status, View (dialog with the full text) and Resend.
- "👥 Team" tab (super_admin only): the reference text, one row per admin with name, email, role
  select (Admin / Finance Officer; Super Admin shown as a badge), Approved / Pending /
  Deactivated badge, section tick boxes for approved admins (licensed modules only), Approve,
  and "Deactivate" (or "Reject" for pending) / "Reactivate".
- "🛡 Audit log" tab (super_admin only): search, table with Time, By (+ role), Action, Detail.
  Paged, 50 rows per page.
Out of scope: Catalog and Fees tabs (F11), dashboards and charts, exporting notifications,
real email or WhatsApp sending (backend specs), inviting admins by email.

Contract
- Uses: submitEnquiry, listEnquiries, addEnquiry, updateEnquiry, listDocuments, verifyDocument,
  rejectDocument, listNotifications, resendNotification, listAdmins, approveAdmin, setRole,
  setSections, listAudit, getPublicSettings, getSession.
- F02 change (update contract, mock and tests): removeAdmin(id) is replaced by
  deactivateAdmin(id) and reactivateAdmin(id). Admin accounts are never deleted. A deactivated
  admin cannot sign in, keeps their name in every history and audit entry, and is not listed in
  "Assigned to" choices. Rejecting a pending admin also deactivates (does not delete).
  HTTP later: POST /admin/team/{id}/deactivate, POST /admin/team/{id}/reactivate.
- listAudit(search, page) returns { rows, total } with 50 rows per page, newest first.

Functional rules
- Contact form: name and contact required; contact must be a valid email or phone. On success
  the form is replaced by "Thank you! We received your enquiry and will contact you within one
  working day." The company email (from Settings) gets a "New enquiry from <name>" notification.
  The form works without signing in.
- Enquiry statuses: New, Contacted, Converted, Closed. Notes are added, never edited or removed;
  each note shows who added it and when.
- Enquiries, Documents: finance gets FORBIDDEN. An admin sees only documents of their sections.
- Notifications: Resend re-checks Settings; status becomes Delivered if the channel is set up,
  else stays Queued or becomes Failed; tries goes up by one. Message bodies are shown as plain
  text, never as HTML.
- Team: the first Super Admin cannot be changed from this screen. Approving a new admin gives
  role Admin with all licensed sections ticked. Changing role to Finance Officer removes all
  sections. The last active Super Admin can never be deactivated or demoted (CONFLICT).
  An admin cannot change their own role or deactivate themselves.
- Deactivating a signed-in admin signs them out on their next action.
- Every change in these tabs writes an audit entry. The audit log has no edit or delete button,
  and the api has no function to change it.

Edge cases
- No enquiries / documents / messages yet: a short muted message, as in the reference.
- Contact form sent twice quickly: only one enquiry is saved.
- A document whose application was withdrawn still shows, with the application status next to the ref.
- Audit search with no result: "No activity matches."
- Licence changes: section tick boxes for unlicensed modules disappear; existing assignments stay
  stored and come back if the module is licensed again.

Non-functional rules
- No new packages. Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference tabs; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t38 submitEnquiry works without a session; listEnquiries as finance is FORBIDDEN.
- t39 deactivateAdmin keeps the admin record; that admin cannot sign in; reactivateAdmin restores
  sign-in; there is no function that deletes an admin.
- t40 Deactivating or demoting the last active super_admin is CONFLICT; an admin changing their
  own role is FORBIDDEN.
- t41 listDocuments for an admin with sections ["job"] returns no study documents.
- t42 listAudit returns 50 rows per page, newest first, and the total count.
- Manual checks:
  - Send the Contact form -> thank-you message; the enquiry appears in Enquiries as New;
    the company gets a notification.
  - Update the enquiry: Contacted, assign it, add a note -> the table shows all three.
  - Documents tab "Expiring in 60 days" shows the document verified in F08 with a near expiry.
  - Notifications show Queued while email is not set up; after setting a sender email in
    Settings, Resend shows Delivered.
  - Team: a second admin signs up -> Pending; Approve -> Admin with all sections; untick Job ->
    that admin no longer sees the Job Processing tab; change to Finance Officer -> sees only
    Accounts and Notifications; Deactivate -> cannot sign in, name still shows in history.
  - Audit log lists every action above with the right person.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F09 are complete and committed.
- Layouts and texts are copied from the reference (aEnq, aDocs, aNotifs, showTeam, aAudit and
  the contact form).
