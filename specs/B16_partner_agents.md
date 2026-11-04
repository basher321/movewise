Spec B16 - Partner agents: records, referred applications and commission

Purpose
The company works with partner firms and agents who refer students (Student Consultancy) and
workers (Job Processing). Staff keep one list of these agents, link each application to the
agent who referred it, and see the commission owed and paid per agent.
Owner decisions 2026-11-02:
- Records and commission only. Agents do NOT sign in; there is no new role.
- Agents are internal and never shown on the website. B2B partners with logos are a separate
  tab and spec (B18).
- Part of Core (always on), not a licensed module. Which sections an agent works in still
  follows the module licence (an unlicensed module is hidden and refused as usual).

Scope
In scope:
- db/migrations/0013_partner_agents.sql: tables partner_agents and agent_commissions, column
  applications.agent_id.
- backend/app/routers/agents.py (new) with the endpoints below; backend/app/main.py includes it.
- backend/app/routers/admin_applications.py: the case view and case list show the agent;
  PUT /admin/applications/{ref}/agent links or unlinks one.
- backend/tests/test_partner_agents.py (new).
- frontend/src/lib/api: types PartnerAgent, AgentCommission, and listAgents(), createAgent(),
  updateAgent(), setApplicationAgent(), listCommissions(), setCommission(), payCommission(),
  cancelCommission() (mock and http).
- frontend: new admin tab "Agents" (src/components/admin/AgentsTab.tsx), entry in
  src/lib/admin/tabs.ts, and an "Agent" row with a change link in the case view (CasesTab).
Out of scope: agent sign-in or portal, applicants choosing an agent themselves, automatic
payouts, commission in the ledger or invoices, course enrolments (Training has no agents).

Database (0013_partner_agents.sql)
- partner_agents: id uuid PK, created_at, updated_at (trigger),
  name text NOT NULL CHECK (btrim(name) <> '' AND length(name) <= 120),
  firm text NOT NULL DEFAULT '' CHECK (length(firm) <= 120),
  phone text NOT NULL DEFAULT '' CHECK (length(phone) <= 40),
  email text NOT NULL DEFAULT '' CHECK (length(email) <= 254),
  country text NOT NULL DEFAULT '' CHECK (length(country) <= 80),
  address text NOT NULL DEFAULT '' CHECK (length(address) <= 300),
  sections text[] NOT NULL DEFAULT '{}' CHECK (sections <@ ARRAY['study','job']::text[]),
  commission_type text NOT NULL DEFAULT 'fixed' CHECK (commission_type IN ('fixed','percent')),
  commission_poisha bigint NOT NULL DEFAULT 0 CHECK (commission_poisha >= 0),
  commission_percent_bp integer NOT NULL DEFAULT 0 CHECK (commission_percent_bp BETWEEN 0 AND 10000)
    (basis points: 1250 = 12.50 %; no floats),
  notes text NOT NULL DEFAULT '' CHECK (length(notes) <= 1000),
  active boolean NOT NULL DEFAULT true.
  Unique index on lower(email) where email <> ''. Index on active.
- applications: ADD COLUMN agent_id uuid NULL REFERENCES partner_agents (id) ON DELETE RESTRICT,
  with an index.
- agent_commissions: id uuid PK, created_at, updated_at (trigger),
  agent_id uuid NOT NULL FK partner_agents ON DELETE RESTRICT (indexed),
  application_id uuid NOT NULL FK applications ON DELETE RESTRICT (indexed),
  amount_poisha bigint NOT NULL CHECK (amount_poisha >= 0),
  status text NOT NULL DEFAULT 'due' CHECK (status IN ('due','paid','cancelled')),
  paid_at timestamptz NULL, paid_by uuid NULL FK admin_users ON DELETE RESTRICT (indexed),
  pay_reference text NOT NULL DEFAULT '' CHECK (length(pay_reference) <= 120),
  note text NOT NULL DEFAULT '' CHECK (length(note) <= 300).
  CHECK (status = 'paid') = (paid_at IS NOT NULL).
  Unique index on application_id where status <> 'cancelled' (one live commission per case).
  A trigger blocks DELETE. A paid or cancelled row cannot change any more (trigger).
- No DELETE, DROP or TRUNCATE anywhere. Agents are switched off with active = false.

Contract (all under /api; SA = super admin, AD = admin of the section, FI = finance)
PartnerAgent: { id, name, firm, phone, email, country, address, sections: ("study"|"job")[],
  commission_type: "fixed"|"percent", commission_poisha, commission_percent_bp, notes, active,
  created_at, referred: number, due_poisha: number, paid_poisha: number }
AgentCommission: { id, agent_id, agent_name, application_ref, module, applicant_name,
  amount_poisha, status: "due"|"paid"|"cancelled", paid_at, pay_reference, note, created_at }
- GET  /admin/agents  SA, AD  ?q, section, active -> PartnerAgent[]
  An admin sees only agents that share one of their sections (licensed sections only).
- POST /admin/agents  SA  body without id/created_at/totals -> PartnerAgent
- PUT  /admin/agents/{id}  SA  same body -> PartnerAgent (active false switches the agent off;
  it keeps its history and can no longer be linked to new cases)
- PUT  /admin/applications/{ref}/agent  SA, AD of that module  { agent_id: string | null }
  -> the case. The agent must be active and work in the case's section, else VALIDATION.
  Linking creates a "due" commission from the agent's terms: fixed = commission_poisha;
  percent = application fee paid (poisha) x bp / 10000, rounded down; 0 when nothing is paid
  yet (staff can set the amount later). Changing the agent cancels the old due commission and
  creates a new one; unlinking cancels it. A paid commission blocks the change (CONFLICT 409
  "The commission for this case is already paid.").
- GET  /admin/agents/commissions  SA, FI, AD  ?agent_id, status, module -> AgentCommission[]
  (an admin only for their sections).
- PUT  /admin/agents/commissions/{id}  SA  { amount_poisha, note } -> AgentCommission (due only)
- POST /admin/agents/commissions/{id}/pay  SA, FI  { pay_reference } -> AgentCommission
- POST /admin/agents/commissions/{id}/cancel  SA  { note } -> AgentCommission (due only)
Errors: UNAUTHENTICATED 401, FORBIDDEN 403, MODULE_NOT_LICENSED 403 (section of the case or
filter), NOT_FOUND 404, VALIDATION 422, CONFLICT 409; JSON {code, message} as always.
Every change writes one audit row in the same transaction: agent.created, agent.updated,
application.agent_set, commission.updated, commission.paid, commission.cancelled.

Frontend
- Admin tab "Agents" (accent of admin #7C3AED), visible to Super Admin and to admins with at
  least one licensed section; Finance sees only the "Commissions" view.
  - Agents view: search, section and active filters, table (name/firm, country, sections,
    terms, referred, due, paid, active), "Add agent" and edit in the existing FormDialog.
  - Commissions view: filters (agent, status, section), table (case ref, applicant, agent,
    amount, status, paid date), "Mark paid" with a reference, "Edit amount", "Cancel".
  - Money shown as taka with thousands separators (formatMoney); entered in taka, sent in
    poisha.
- Case view (CasesTab): an "Agent" row with the agent name or "Direct", and "Change" to pick an
  active agent of that section or "Direct".
- Same look as the other admin tabs (AdminTable, tabs2, cards). Works at 390px, light and dark.

Acceptance criteria
- b132 Super admin creates, edits and switches off an agent; each writes one audit row.
- b133 An admin of study sees only agents with "study"; creating an agent is FORBIDDEN for them.
- b134 Linking a fixed agent to a study case makes one due commission with that amount;
  a percent agent uses the paid application fee; changing the agent cancels the old one.
- b135 Linking an inactive agent or an agent of another section is VALIDATION; a job case of an
  unlicensed job module is MODULE_NOT_LICENSED.
- b136 Finance marks a due commission paid; it can no longer be edited or cancelled (CONFLICT),
  and the case's agent can no longer change.
- b137 Agent totals (referred, due, paid) match the commission rows.
- b138 DELETE on agent_commissions is blocked by the trigger; no code path deletes agents.
- All earlier tests still pass.

Assumptions
- Commission is a record of what is owed and paid; the actual payout happens outside the
  software (bank or bKash), so it is not a ledger entry.
