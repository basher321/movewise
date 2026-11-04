Spec F05 - Courses: list, details, enrolment with checkout, invoices, certificates, certificate check

Purpose
Let a learner browse courses, enrol and pay, get an invoice, and receive a certificate once the
company approves it - and let anyone check a certificate ID online. The payment checkout and
invoice viewer built here are shared components that the Student Consultancy and Job Processing
specs reuse later. Screens must look and behave like the Courses page, course detail page,
Enrol dialog, "My courses & certificates", "My invoices", invoice dialog, admin Courses tab and
Verify certificate page in reference/nextgen-learning-v2.html.

Scope
In scope:
- /courses: hero, course groups (Artificial Intelligence, English Language, Quantum Computing)
  and "How learning works", with course cards loaded from listCourses(). Unpublished courses are
  not shown.
- /courses/[id]: course detail exactly like the reference (crumb, tag, title, lead, meta chips,
  price card, "What you will learn", Syllabus band). Button: "Enrol & purchase", or
  "Enrolled ✓ Open my profile" when already enrolled.
- Enrol dialog: title "Enrol in <course>", price line, fields Full name, Email (read-only),
  Phone, Country, Education or occupation, then the shared Checkout part.
- Shared component PaymentCheckout (src/components/payment/): payment method list built from
  enabled gateways in Settings (SSLCommerz, bKash, Nagad, Bank transfer / office), the manual
  payment receipt-number box and instructions, the error line, the pay button, and while the
  mock is used a "Demo: simulate a failed payment" tick box (behind SHOW_DEMO_CODES).
- Shared component InvoiceDialog: shows one invoice exactly like the reference invoice, with
  "Print / Save as PDF" (opens the browser print view with only the invoice).
- Profile, Courses tab (replaces the F04 placeholder for the course module only):
  "My courses & certificates" - one card per enrolment with order no, amount, method, date,
  the certificate preview, and either "Download certificate (PNG)" (approved) or
  "🔒 Download locked" plus the text "View only. Download unlocks after you complete the course
  and <company> approves your certificate." Below it "My invoices" - one card per invoice with
  number, description, date, amount, email status, "View / print invoice" and "Request refund".
  Pending manual payments show the blue "waiting for verification" banner.
- Certificate drawing: a 1000x707 canvas drawn exactly like the reference drawCert, using the
  company logo and name from Settings. Not approved = "VIEW ONLY" watermark.
- Admin panel, Courses tab (admins with the course section, and super_admin): list of enrolments
  (learner, email, course, order, paid, date, certificate ID, status) with search, and an
  "Approve certificate" button for each not-yet-approved one.
- /verify: certificate ID box; result "✓ Valid certificate. <name> completed <course>" or
  "No approved certificate found with ID <id>."
- Request refund dialog (reason, required) calling requestRefund. The finance side comes later.
Out of scope: course catalog editing (Catalog spec), finance screens, application fees, real
gateways, real PDF files, lessons or video content.

Contract
- Uses: listCourses, getCourse, enrol, myEnrolments, myInvoices, requestRefund, updateMyProfile,
  approveCertificate, verifyCertificate, getPublicSettings, getSession, openAuth (from F04).
- New action: listEnrolments(search) -> enrolments joined with learner and course
  (S, course section). HTTP later: GET /admin/enrolments. Add a test t24.
- Enrolment.certificate_id format: CERT- + 8 letters/digits, created at enrolment, unique.
- PaymentCheckout props: amount_poisha, purpose text, onPay(method, txnRef) -> Promise,
  onDone(result). It never decides that a payment succeeded; it only shows what the api returns.
- InvoiceDialog props: invoice, open, onClose.

Functional rules
- "Enrol & purchase" when not signed in to Courses: opens the auth dialog in Sign up mode for
  Courses with the note "Create your Courses account to enrol, then sign in."; after sign-in and
  verification the Enrol dialog opens by itself (openAuth "after").
- Enrol form: name required; phone must be valid (same rule as F04); the entered name, phone,
  country and education are saved to the profile with updateMyProfile before paying.
- Gateway payment success: dialog closes, the profile Courses tab opens and shows the new course
  and its invoice. Failure: the error "Payment failed or was cancelled at <method>. No money
  was taken. Please try again." and the dialog stays open.
- Manual payment: receipt number required; success message "Payment reference sent. We will
  email you once it is verified."; the course appears only after finance verifies it.
- Enrolling in a course the learner already owns or has a pending payment for shows
  "You already have this course or a payment waiting for verification." and charges nothing.
- Certificate download makes a PNG named <certificate_id>.png. Locked certificates cannot be
  downloaded (no button, and the api never returns approved=true for them).
- Request refund: one per invoice; after requesting, the button is replaced by a
  "Refund requested" badge; refunded invoices show "Refunded".
- Money is shown as ৳ with thousands separators; amounts are poisha inside the code.

Edge cases
- Course id that does not exist or is unpublished: "Course not found" card with a link to /courses.
- No payment method enabled in Settings: the checkout shows "No payment method is set up yet.
  Please contact us." and no pay button.
- Very long names or course titles: the certificate uses a smaller font, as in the reference.
- Logo not loaded yet when drawing: the company name is drawn instead, as in the reference.
- Training module not licensed: every page and the admin tab in this spec show the locked card.

Non-functional rules
- No new packages. Pages import only from src/lib/api/index.ts.
- Checkout and invoice are generic and contain no course-specific text, so F06 and F07 can reuse them.
- Looks exactly like the reference; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t24 listEnrolments returns enrolments with learner and course names; a job-only admin gets FORBIDDEN.
- Manual checks:
  - /courses shows all published courses in their groups; a course hidden in data does not appear.
  - Not signed in -> Enrol & purchase -> sign up + verify -> Enrol dialog opens by itself.
  - Pay with bKash -> profile shows the course, a locked certificate preview with the learner's
    name, and invoice <prefix>-<year>-NNNN; the invoice dialog matches the reference and prints
    only the invoice.
  - Pay with "simulate failed payment" ticked -> failure message, no course, no invoice.
  - Pay by Bank transfer / office -> blue waiting banner; no course until verified.
  - Enrolling again in the same course is refused with the message above.
  - Admin with the course section approves the certificate -> learner's profile shows
    "Download certificate (PNG)" and the file downloads.
  - /verify with that ID shows the valid message; a random ID shows not found; an unapproved
    certificate's ID shows not found.
  - Request refund -> badge "Refund requested"; a second request is not possible.
  - With only bKash enabled in Settings, the checkout lists only bKash.
  - With the "Student Consultancy only" licence, /courses, /courses/[id], /verify and the admin
    Courses tab show the locked card.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F04 are complete and committed.
- Course data and texts come from the seed (F02), which copies the reference.
