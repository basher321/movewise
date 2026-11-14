Spec B25 - Remote Jobs partial match, and agents that know the signed-in applicant

Purpose
1. The Remote Jobs search (/remote-jobs) and the Remote Jobs agent show every open remote role
   that meets at least one of the applicant's criteria, best first, the same way the Student
   Consultancy match already does. Today a role is shown only when its skill is exactly the one
   chosen, so a visitor often sees nothing.
2. Every advisor agent (study, job, visa, remote) works in two modes:
   - General mode (visitor, or home page / public pages, not signed in to that module): answers
     as now, from the public catalog only.
   - Applicant mode (an applicant signed in to that module asks): answers from that applicant's
     own records as well, for example "What is my status?", "Which documents are missing?",
     "Is my fee paid?", "When is my interview?". Never anything about another applicant.

Scope
In scope:
- backend/app/match.py: match_remote rule change (below). Labels in the same style as study.
- Agent ask (POST /api/agent/{module}/ask): read the applicant session of that module, if any.
  No new endpoint, no new field in the request. The response stays {answer}.
- backend/app/ai/context.py: in applicant mode, add a "my_cases" block to the facts (below).
- Rule-based fallback (app/match.py agent_answer): status questions in applicant mode answered
  from the same "my_cases" data.
- Frontend: no change in layout. The remote results list shows the per-criterion ticks it
  already shows for other modules.
Out of scope: Job Processing match (unchanged), new pages, new tables or migrations, changes to
the agent form fields, staff (admin) chat, any change to what a visitor sees in general mode.

Contract
- POST /api/match/remote: same request and response as now. Rule:
  - Only open, employer-verified remote roles (unchanged). An unverified or closed role is
    never shown (an admin must tick "Employer verified").
  - The country filter stays a filter (unless empty or "Any country").
  - Criteria, each counting equally: skill is the chosen one, experience >= minimum, education
    >= minimum, English >= minimum, salary >= goal (or no goal).
  - A role is shown when it meets at least one criterion. match_percent = round(30 + 70 x met /
    total). Sorted by match_percent, then the chosen skill first, then the highest salary,
    then title.
  - Labels: "<skill> role" / "Different skill (<role skill>)", and the existing experience,
    education, English and salary labels.
- POST /api/agent/{module}/ask: same request and response.
  - Applicant mode applies when the request carries a valid applicant session for that same
    module. A session for another module does not count (that is general mode).
  - Order of checks unchanged: module licensed -> input valid -> answer.

Functional rules
- "my_cases" (applicant mode only) holds, for each of the applicant's applications in that
  module, newest first, at most 10: reference, item name and country, status, stage name and
  "stage N of M", fee paid yes/no and, if not paid, the amount to pay (the case fee from the
  case-fee change, else the item fee), the latest payment status, missing document types,
  rejected documents with the rejection note shown to the applicant, deadline, interview date
  and time in Asia/Dhaka (job, visa, remote), whether a completion letter is issued, and the
  last 3 public history lines. Nothing staff-only: no internal notes, no private history, no
  staff emails, no assigned staff member other than the advisor name already shown to the
  applicant, no agent commission.
- The AI prompt says: answer questions about "my application / status / documents / fee" only
  from my_cases; if my_cases is empty, say there is no application yet and how to apply.
  The grounding check (numbers and phones must come from the facts) also covers my_cases.
- Rule-based fallback, applicant mode: questions containing status, stage, application,
  document, missing, paid, payment, fee, interview, deadline or letter get an answer built
  from my_cases (one short paragraph per case, at most 3 cases, newest first). Other questions
  are answered as in general mode.
- General mode is exactly the current behaviour.
- No change of data, so no audit row (as now for agent questions).

Edge cases
- Signed in but no application in that module: "You have no <module> application yet." plus
  the general answer.
- Withdrawn and completed applications are included with their status.
- A session that expired between page load and question: general mode, no error.
- Remote: no open verified remote roles at all: [] and the agent says none are open now.

Non-functional rules
- No new packages, no migration.
- An applicant's data never reaches another person: tests check this.
- pytest, npm run build, npm run lint and npm test pass.

Acceptance criteria
- b25-1 match_remote returns a role whose skill differs but experience fits, with "Different
  skill (...)" unticked and a lower match_percent than an exact-skill role; a role meeting
  no criterion is not returned; closed or unverified roles are never returned.
- b25-2 /agent/remote/ask after the form finds a role whose skill differs.
- b25-3 Visitor asks "what is my status" -> general answer, no applicant data.
- b25-4 Applicant A (signed in to study) asks "what is my status" -> answer has A's reference
  and stage; never B's reference.
- b25-5 Applicant signed in to job asks the study agent -> general mode.
- b25-6 my_cases never contains internal notes, private history or staff emails.
- b25-7 Unpaid case with a case fee -> the agent states that case fee.
- Manual checks on the live site: /remote-jobs search with a different skill shows partial
  matches; a signed-in applicant asks each agent "what is my status" and gets their own case.

Assumptions
- B17 (AI advisors) and the case-fee change (commit c93507a) are live.
