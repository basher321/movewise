Spec F06 - Student Consultancy: page, eligibility agent, university details, apply, fee, documents, my application

Purpose
Let a student find universities they can realistically get into, read every condition, apply,
pay the application fee to unlock the official application link, upload their documents and
follow their application stage by stage. The agent widget, item detail page and application
page built here are generic, so Job Processing (F07) reuses them with its own settings.
Screens must look and behave like the Student Consultancy page, the agent widget, the item
(university) page, the Application fee dialog and the Apply page (with the Status, Documents
and History cards) in reference/nextgen-learning-v2.html.

Scope
In scope:
- /consultancy: hero, agent section, "Your application roadmap" band, "Everything you need in one
  dashboard" cards, "Popular study destinations" chips and the call-to-action, as in the reference.
- Generic AgentWidget (src/components/agent/), configured for study: tag "AI agent", title,
  subtitle, the input form (Study level, Field of study, GPA, IELTS, Budget per year), the
  "Find my universities" button, the chat card with an input and Ask button, and the results
  grid (name, country, city, match %, green/red condition chips, "Select & view details").
  The last inputs are remembered in the browser and shown again on return.
- Generic ItemPage at /consultancy/[id]: crumb, tag, name, lead, the match chips if the student
  has used the agent, facts card (Tuition per year, Minimum GPA, IELTS, Intakes, Deadline,
  Scholarships, Application fee), "All conditions" list, the stage roadmap, and the button
  "Apply now" or "Open my application →".
- Generic ApplicationPage at /consultancy/[id]/apply: progress % and "Stage x of y", the stage
  list (done / current / upcoming), "Next step" card, "Your details" card (the agent inputs),
  and the v2 cards: Status (status badge, your advisor, application deadline), Documents
  (one row per required document with Upload / Upload again, status badges, View), History
  (public events only) and "Withdraw this application".
- Next step card: before payment - text and button "🔒 Pay ৳<fee> to unlock link" which opens the
  Application fee dialog (fee box, mobile number field, then the shared PaymentCheckout from F05).
  After payment - "✓ Fee paid · ৳<amount> via <method> · <payment id>", the invoice line with
  "View / print invoice", the official application link button (or "Application link coming soon"
  if the admin has not set one), and the text from the reference.
- Profile, Student Consultancy tab: "My applications" cards (name, country, stage x of y, bar),
  then "My invoices" (reuse from F05).
- New action askAgent(module, question, inputs) -> text. The mock answers with the same
  rule-based replies as the reference fallback (fb). HTTP later: POST /agent/{module}/ask
  (the backend will use an LLM with the same prompt as the reference). Add test t25.
Out of scope: admin case handling (F08), document review by staff (F08), job pages (F07),
finance verification screens, a real LLM.

Contract
- F02 correction (update types.ts, the mock and tests): stage lists come from the reference.
  StudyStage has 9 stages (index 0-8). JobStage has 8 stages (index 0-7): Application started,
  Profile screening, Employer interview, Job offer & contract, Medical & police clearance,
  Work permit & visa, Flight booked, Ready to fly ✈. The last stage of each module sets status
  completed. Add stageCount(module) and use it everywhere; never hardcode 8.
- Required document lists per module are copied from the reference DOCS lists into types.ts.
- Uses: listUniversities, getUniversity, matchUniversities, askAgent, startApplication,
  myApplications, getMyApplication, payApplicationFee, uploadDocument, withdrawApplication,
  myInvoices, requestRefund, getPublicSettings, getSession, openAuth.
- getMyApplication returns: application, item, stages, public history, documents (latest per
  type, with computed expiring/expired), payment (if any) and invoice (if any), assigned
  advisor name, apply_link (only when fee_paid is true - the api never sends it before payment).
- AgentWidget props: module, config (title, subtitle, fields, button text, chat placeholder),
  onSelect(itemId). ItemPage and ApplicationPage take module and id.

Functional rules
- Match: same scoring as the reference sc() and match(); only published universities that offer
  the chosen level and field; sorted by match % (highest first).
- "Apply now" not signed in to Student Consultancy: open the auth dialog in Sign up mode with
  "Create your Student Consultancy account to apply, then sign in to continue."; after sign-in
  the application page opens by itself.
- Apply creates the application with the agent inputs as answers (empty if the agent was not
  used) and opens the application page. Applying again to the same university opens the same one.
- The official application link is never shown, sent or present in the page before the fee is
  paid (a test checks the api response).
- Fee dialog: mobile number must be a valid Bangladeshi mobile; payment rules as in F05
  (gateway success / failure / manual pending). After a manual payment the Next step card shows
  the blue waiting banner instead of the pay button.
- Documents: pdf, jpg, jpeg, png only, max 2 MB; after upload the row shows "Waiting review".
  Rejected, expired or expiring documents show "Upload again". Upload is possible only while
  status is active.
- Status card shows the status badge; for any status other than active, a banner at the top of
  the page shows the status and the latest public reason.
- Withdraw asks for confirmation, then sets status withdrawn; the pay button, uploads and
  withdraw link disappear.
- Chat: empty question does nothing; the reply appears under "Thinking…" in the chat log.

Edge cases
- University id unknown or unpublished (and the student has not applied): "Not found" card with
  a link back to /consultancy. A student who already applied can still open it.
- Fee is 0: no payment step; the link shows at once.
- Settings with no payment method: the fee dialog shows the F05 "No payment method" message.
- Student Consultancy not licensed: every page and the profile tab show the locked card.

Non-functional rules
- No new packages. Pages import only from src/lib/api/index.ts.
- AgentWidget, ItemPage and ApplicationPage contain no study-only text; all text comes from
  the module config, so F07 can reuse them.
- Looks exactly like the reference; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t25 askAgent returns a non-empty answer; with the study module unlicensed it throws
  MODULE_NOT_LICENSED.
- t26 getMyApplication has no apply_link before payment and has it after payment.
- t27 stageCount("study") is 9 and stageCount("job") is 8; changeStage(job app, 7) sets completed
  and changeStage(job app, 8) is VALIDATION.
- Manual checks:
  - Agent with GPA 3.5, IELTS 7, budget 30000, Bachelor, Computer Science & AI shows matches
    sorted by %, with green and red chips; returning to the page shows the same results.
  - Ask "What scholarships?" in the chat -> a reply appears.
  - Select a match -> item page with facts, conditions and match chips.
  - Not signed in -> Apply now -> sign up + verify -> application page opens by itself.
  - Pay the fee with bKash -> "✓ Fee paid", invoice line, link button; the invoice opens.
  - Failed payment -> error, still locked. Manual payment -> waiting banner.
  - Upload a passport PDF -> "Waiting review"; a 3 MB file and a .docx are refused.
  - Withdraw -> status Withdrawn banner, no uploads or pay button.
  - Profile Student Consultancy tab shows the application card with the right stage.
  - With the "Jobs only" licence, /consultancy and its sub-pages show the locked card.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F05 are complete and committed.
- University data, fields, texts and stage names come from the seed, which copies the reference.
