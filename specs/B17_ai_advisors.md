Spec B17 - AI advisors for Student Consultancy and Job Processing, AI keys in Settings

Purpose
The two existing chat agents (Student Consultancy and Job Processing, F06/F07, POST
/agent/{module}/ask) answer with an AI model, using only facts from this installation's
database. The Super Admin sets the AI providers and keys in Settings. Providers fail over:
when one fails, the next one answers. This is the AI provider spec planned after B10.
Owner decisions 2026-11-02:
- Providers: Claude (Anthropic), ChatGPT (OpenAI), Gemini (Google) and Groq. The Super Admin
  enables each, enters its key and model, and sets the order. Default order: Claude, ChatGPT,
  Gemini, Groq.
- When the database has no matching information, the advisor never invents facts. It says
  politely that it has no information on that yet and suggests a free consultation, with the
  contact details from Settings.

Scope
In scope:
- db/migrations/0014_ai_providers.sql: column settings.ai (jsonb).
- backend/app/ai/ (new): providers.py (one small httpx client per provider), failover.py,
  context.py (the database facts for a question), advisor.py (prompt and answer).
- backend/app/routers/catalog.py: ask_agent uses advisor.answer(); the request and response
  shapes of POST /agent/{module}/ask do not change ({ answer }).
- backend/app/routers/settings.py: the ai block in GET/PUT /settings and the four keys as
  secrets; POST /admin/settings/test-ai.
- backend/tests/test_ai_advisor.py (new). Tests never call a real provider: the HTTP calls are
  replaced by a fake transport.
- frontend/src/lib/api: the ai block in Settings / SettingsInput types, testAiProvider().
- frontend: a new "AI assistants" card in the Settings tab (SettingsTab.tsx). The chat widget
  (AgentWidget) is unchanged.
Out of scope: an AI for the Training module, chat history stored in the database, streaming,
staff-facing AI, uploading documents to the AI, any new package (httpx is already used).

Database (0014_ai_providers.sql)
- settings: ADD COLUMN ai jsonb NOT NULL DEFAULT
  '{"order":["claude","openai","gemini","groq"],"providers":{
    "claude":{"enabled":false,"model":"claude-sonnet-5-5"},
    "openai":{"enabled":false,"model":""},
    "gemini":{"enabled":false,"model":""},
    "groq":{"enabled":false,"model":""}}}'
  with CHECK (jsonb_typeof(ai) = 'object').
- Keys live encrypted in app_secrets (B08) under ai.claude_key, ai.openai_key, ai.gemini_key,
  ai.groq_key. They are never returned, logged or put in an audit row.

Contract (additions)
- Settings (super admin view) gains:
  ai: { order: Provider[], providers: { [p in Provider]: { enabled: boolean, model: string,
  key: SecretStatus } } }   with Provider = "claude" | "openai" | "gemini" | "groq".
  SettingsInput.ai is the same with key: string ("" keeps the saved key). PublicSettings does
  not contain ai.
  Rules: order holds each provider exactly once; an enabled provider needs a saved key and a
  model (1-100 characters, letters, digits, . _ : / -), else VALIDATION. Audit row
  "settings.updated" lists "ai" and, for a key, "ai.<p>_key" (name only, never the value).
- POST /admin/settings/test-ai  SA  { provider } -> { ok: boolean, message: string }
  Sends one short test prompt with the saved key and model; the message names the provider
  and the error code returned, never the key.
- POST /agent/{module}/ask: unchanged shape and checks (module licensed -> question not
  empty). New: at most 20 questions per IP per 10 minutes -> TOO_MANY_TRIES 429; question at
  most 500 characters -> VALIDATION.

How an answer is made (advisor.py)
1. Facts (context.py), read with the request's connection, published rows only:
   - study: universities (name, country, city, levels, fields, tuition_usd, min_gpa,
     min_ielts, intakes, deadline_text, scholarships, work_rights, conditions); job: vacancies
     that are not closed (title, employer, country, occupation, min_experience, min_education,
     min_english, salary_usd, seats, apply_by, contract, benefits, conditions,
     employer_verified).
   - Which rows: the agent matches for the inputs (match_study / match_job, best first) when
     the form was filled, plus rows whose name, country, city, fields, title, employer or
     occupation contain a word of the question; at most 8 rows.
   - Always: the application fee for the module (default or the row's override, shown in
     taka), the stage names of the module, and the company name, phone, email, address and
     hours from Settings.
2. Prompt: a fixed system text: you are the <company> advisor for <Student Consultancy | Job
   Processing>; answer only from FACTS; never invent universities, jobs, fees, salaries,
   deadlines, requirements or visa rules; if FACTS do not answer the question, say so politely
   and suggest a free consultation with the contact details in FACTS; reply in the language of
   the question (English or Bangla), at most 120 words, plain text. Then FACTS as JSON, the
   applicant's form inputs, and the question. Applicant data other than the form inputs is
   never sent.
3. Failover (failover.py): providers in the saved order, enabled and with a key. Each call has
   a 20 second timeout; a timeout, network error, HTTP 401/403/408/429/5xx or an empty reply
   moves to the next provider. The first non-empty reply is the answer.
4. When no provider is enabled, or all fail: the existing rule-based answer (agent_answer in
   match.py) is returned, so the chat always works.
5. The server log gets one line per failed provider (provider name and status only, never
   the key, prompt or question).

Frontend (Settings tab, Super Admin only)
- Card "AI assistants" in the existing Settings layout (fgrid, fl, cards, banner):
  for each provider in order: name, Enabled switch, Model field, API key field (password
  style, "Saved" badge when a key is stored, empty keeps it), "Test" button showing the
  result in a banner, and up / down buttons to change the order.
- A short note: "The advisors answer only from your published universities, jobs and fees.
  If no provider works, the simple built-in replies are used."
- Same style as the other Settings cards; works at 390px, light and dark.

Acceptance criteria
- b139 GET /settings shows ai with key status only; PUT saves order, models and keys; a key is
  stored encrypted and never appears in any response or audit detail.
- b140 Enabling a provider without a key or model is VALIDATION; an order with a missing or
  repeated provider is VALIDATION.
- b141 With Claude failing (fake 500) and ChatGPT answering, ask returns ChatGPT's answer;
  with all failing, ask returns the rule-based answer.
- b142 The prompt sent contains only published rows, the module fee, stage names and Settings
  contact details; an unpublished university or closed vacancy is never in it.
- b143 A question with no matching rows still sends the contact details and the "no
  information" rule; nothing from another module is sent.
- b144 test-ai returns ok true with a working fake provider and ok false with a message for a
  failing one; only the super admin may call it.
- b145 The 21st question from one IP within 10 minutes is TOO_MANY_TRIES; an unlicensed
  module is MODULE_NOT_LICENSED before any provider is called.
- All earlier tests still pass.

Assumptions
- Provider APIs: Anthropic Messages API, OpenAI Chat Completions, Google Gemini
  generateContent, Groq (OpenAI-compatible Chat Completions). Exact endpoint paths and default
  models are checked against each provider's current documentation when building.
- Each provider bills the owner's own account; the per-IP limit keeps costs down.
