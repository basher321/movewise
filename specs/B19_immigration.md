Spec B19 - Immigration Processing module (visa programmes), with agents and partners

Purpose
A fifth product area next to Training, Student Consultancy and Job Processing: the company handles
visa and immigration files for every country and every visa type. It works exactly like Student
Consultancy and Job Processing: the applicant chooses a visa programme, applies, pays the
processing fee, uploads documents and follows the stages in their profile; staff handle the case.
Owner decisions 2026-11-04:
- Catalogue item = "visa programme" per country (for example Canada Visitor Visa, UK Spouse Visa,
  Australia PR 189), added by the super admin. All countries, all visa types.
- Follow the same patterns as the other modules (code, look, licence, roles, fees, payments).
- Partner agents (B16) and B2B partners (B18) also work in this module.
- Migration 0016 may use ALTER TABLE ... DROP CONSTRAINT only to replace the module CHECK rules
  with wider ones (same pattern as the owner's exception in 0011). Nothing else is dropped.

Names
- Code name "visa"; label "Immigration Processing"; short "Immigration"; icon 🛂🌍 -> "🌍".
- Public pages under /immigration; profile /profile/visa; applicant ids "VIS-XXXXXX".
- Accent colour #E11D48 (rose), distinct from every other section.
- Licence: a key may list "visa" in its modules; licence.module_visa. A key without "visa" leaves
  the module locked (hidden in the UI, MODULE_NOT_LICENSED in the api).

Scope
In scope:
- db/migrations/0016_immigration.sql: table visa_programs; settings.default_fee_visa_poisha;
  licence.module_visa; applications.visa_program_id (+ index, one-open unique index for visa);
  module CHECK lists widened to include 'visa' on admin_users, applicant_accounts, sessions,
  signin_failures, password_resets, notifications, payments, invoices, ledger_entries (category
  'visa' = "Immigration application fees"), enquiries, partner_agents, partners, ai_questions;
  partner types 'visa_centre' and 'law_firm'.
- backend: licence, stages (8 stages, 7 document types), catalog (visa_program_view, VISA_TYPES),
  public endpoints, admin catalog, fees, settings default fee, match and rule-based agent, AI
  advisor facts, applications (applicant and admin), documents, finance outstanding, agents,
  partners, sign-in kinds, licence tool. Tests: backend/tests/test_immigration.py.
- frontend: module config, /immigration pages (list + agent, programme page, apply page), profile,
  header and footer links, admin Catalog "Visa programmes", Fees, Settings default fee, Cases,
  Accounts, Agents, Partners, Licence and Team sections, contact interest, api types (mock + http).
Out of scope: per-programme document checklists for uploads (uploads use the fixed visa document
types; the programme's own list is shown as information), embassy integrations, appointment
booking with embassies.

Database (0016_immigration.sql)
visa_programs: id, slug (unique), title, country, visa_type CHECK IN ('visit','tourist','business',
'family','spouse','work','student','permanent_residence','citizenship','transit','medical','other'),
processing_time, validity, government_fee (free text, e.g. "CAD 100"), description,
eligibility text[] (>= 1), required_documents text[] (>= 1), conditions, official_link (https or
''), embassy_email, fee_override_poisha (NULL or > 0), published, created_at, updated_at (trigger).
Never deleted: hidden with published = false.

Contract (all under /api)
VisaType = "visit" | "tourist" | "business" | "family" | "spouse" | "work" | "student"
  | "permanent_residence" | "citizenship" | "transit" | "medical" | "other"
VisaProgram (public): { id, slug, title, country, visa_type, visa_type_label, processing_time,
  validity, government_fee, description, eligibility[], required_documents[], conditions, fee_poisha }
AdminVisaProgram: VisaProgram + { official_link, embassy_email, fee_override_poisha, published,
  applied_count, updated_at }
- GET  /visa-programs                P (licensed) -> VisaProgram[] (published only)
- GET  /visa-programs/{slug}         P (licensed) -> VisaProgram (hidden: only for an applicant
                                     who applied to it)
- POST /match/visa                   P { country, visa_type: VisaType | "any", passport_ready,
                                     refused_before } -> Match[]
- GET  /catalog/options              adds visa_countries[] and visa_types[] (in use)
- GET  /admin/visa-programs          SA -> AdminVisaProgram[]
- POST /admin/visa-programs          SA -> AdminVisaProgram (audit catalog.visa_program_saved)
- PUT  /admin/visa-programs/{id}     SA -> AdminVisaProgram (audit catalog.visa_program_saved)
- /me/visa/applications ..., /admin/applications?module=visa ..., /me/visa/applications/{id}/pay,
  documents, notes, case emails (to: "provider" = the embassy email): same as study and job.
- Fees: GET /admin/fees adds defaults.visa and visa_programs[]; PUT /admin/fees accepts visa{};
  POST /admin/fees/reset accepts scope "visa". Settings default_fee_poisha.visa (optional on PUT:
  missing keeps the saved fee).
- Agents: sections may include "visa". Partners: module may be "visa".
Errors and audit as always: {code, message}; one audit row per change in the same transaction.

Stages (0-7)
Application started, Eligibility review, Documents checked, File prepared, Visa application
lodged, Biometrics / interview, Visa decision, Ready to travel ✈ (the last stage completes the case).

Document types
Valid passport (all pages); Passport-size photographs; Bank statement and proof of funds;
Employment or business documents; Invitation, sponsor or family documents; Previous visas and
travel history; Other supporting documents.

Acceptance criteria
- b153 Super admin creates, edits and hides a visa programme; each writes one audit row; the
  public sees only published programmes and never official_link, embassy_email or overrides.
- b154 An applicant signs up to Immigration (VIS- id), applies to a programme (one open
  application per programme), sees 8 stages, pays the fee and uploads documents.
- b155 Staff of the visa section see and move visa cases; an admin of another section is
  FORBIDDEN; the last stage completes the case; a case email to the provider goes to the embassy.
- b156 With "visa" not licensed every visa endpoint is MODULE_NOT_LICENSED and the UI hides it.
- b157 Agents with section "visa" can be linked to visa cases and earn commission; partners of
  module "visa" show only on /immigration.
- b158 Default fee and per-programme fees work like universities and vacancies.
- All earlier tests still pass.
