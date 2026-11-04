Spec F07 - Job Processing: page, job agent, vacancy details, apply, fee, documents, my application

Purpose
Let a job seeker find verified overseas roles they qualify for, read every condition, apply,
pay the application fee so the processing team starts work, upload their documents and follow
their application stage by stage. This spec reuses AgentWidget, ItemPage and ApplicationPage
from F06 with a job configuration; it adds no new shared component. Screens must look and behave
like the Job Processing page, the job agent, the job item page and the job Apply page in
reference/nextgen-learning-v2.html.

Scope
In scope:
- /jobs: hero, agent section, "Explore job opportunities" cards (open, verified vacancies,
  grouped by occupation as in the reference cards), the band "Eligibility & documents" and
  "Country & job details", and the call-to-action, as in the reference.
- Job configuration for AgentWidget: title "Meet your Job Processing Agent", subtitle, fields
  (Your occupation, Preferred country, Experience (years), Education, English level, Passport,
  Expected salary (USD/month) - optional), button "Find my job match", chat placeholder
  "Ask about salary, documents, process…". Results are grouped by country with a heading
  "<flag> <country> · <n> role(s)", exactly like the reference.
- /jobs/[id] using ItemPage with the job configuration: facts (Salary per month, Experience,
  Education, English, Contract, Benefits, Application fee), the badge
  "✓ Verified employer · licence <no>", seats and "Apply by" badges when set, the conditions
  list (including "Passport valid for 18+ months"), the job stage roadmap and the Apply button.
- /jobs/[id]/apply using ApplicationPage with the job configuration: same parts as F06, with
  these job differences:
  - Pay button text "🔒 Pay ৳<fee> to apply" and the reference text about the processing team.
  - After payment, no external link; instead the reference text "Your application is with our
    processing team. We verify your documents, coordinate with <employer> and update the stages
    on this page..."
  - Status card shows Interview (date and time or "Not scheduled"), Interview result and
    Offered salary (when set), instead of Application deadline.
  - Documents card uses the job document list from the reference.
- Profile, Job Processing tab: "My applications" and "My invoices", same as F06.
Out of scope: admin case handling, interview scheduling by staff, employer accounts,
vacancy editing (later specs).

Contract
- Uses: listVacancies, getVacancy, matchVacancies, askAgent, startApplication, myApplications,
  getMyApplication, payApplicationFee, uploadDocument, withdrawApplication, myInvoices,
  requestRefund, getPublicSettings, getSession, openAuth.
- getMyApplication for a job application returns interview_at, interview_result and
  offered_salary_usd, and never returns apply_link.
- Module config lives in src/config/modules/job.ts next to study.ts from F06; the shared
  components read everything module-specific from these files.

Functional rules
- Match: same scoring as the reference match() for jobs (experience, education, English,
  passport, salary goal). Only vacancies that are not closed and whose employer is verified;
  filtered by occupation and by country unless "Any country".
- Experience is required in the agent form; salary goal is optional (empty = always meets).
- "Apply now" not signed in to Job Processing: auth dialog in Sign up mode with
  "Create your Job Processing account to apply, then sign in to continue."; afterwards the
  application page opens by itself.
- Payment, documents, withdraw, status banner and history work exactly as in F06.
- A vacancy that becomes closed or unverified after a person applied stays visible to that
  person on their application page, but disappears from the public list and the agent.
- The application's last job stage is "Ready to fly ✈" (index 7) and shows status Completed.

Edge cases
- Vacancy id unknown, closed or unverified (and not applied): "This vacancy is not open." card
  with a link back to /jobs.
- No vacancies match: the reference message with the "book a free consultation" link.
- Seats or Apply by not set: their badges are not shown.
- Job Processing not licensed: every page and the profile tab show the locked card.

Non-functional rules
- No new packages, no new shared components, no copy of F06 components - only configuration.
  If a shared component needs a change, make it generic and keep F06 working.
- Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass (all F06 checks still pass).

Acceptance criteria
- t28 matchVacancies never returns a closed vacancy or one with an unverified employer, and
  filters by country unless "Any country".
- t29 getMyApplication for a job never contains apply_link, before or after payment.
- Manual checks:
  - /jobs shows only open, verified vacancies in "Explore job opportunities".
  - Agent with Construction, Any country, 3 years, Diploma, Good English, passport ready shows
    results grouped by country with match % and chips; the chat answers a question.
  - Item page shows the verified-employer badge, facts and conditions.
  - Not signed in -> Apply now -> sign up + verify -> application page opens by itself.
  - Pay with bKash -> "✓ Fee paid", invoice line, the processing-team text and no link.
  - The Status card shows "Interview: Not scheduled".
  - Uploads use the job document list; wrong file type and size are refused.
  - Profile Job Processing tab shows the application and the invoice.
  - The F06 study pages still work exactly as before.
  - With the "Student Consultancy
