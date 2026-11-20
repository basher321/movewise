Spec B28 - NextGen LearninG AI CV Agent

Status: APPROVED by the owner on 2026-11-20 (all six Decisions: yes). Built in 6 phases; the owner approves each phase
before the next starts. Each phase is deployed live first, then localhost, then git push.

Purpose
A click-driven CV builder for overseas jobs, skilled migration, study applications and remote
work. The applicant clicks options, uploads documents and confirms; the AI agent reads the
documents, asks only for what is missing, writes the CV under the destination country's rules,
checks it, and exports an ATS-friendly PDF and DOCX of at most 2 pages (plus an optional cover
letter). It is part of Core: free, for any signed-in applicant of any service.

Owner decisions already taken (2026-11-20)
- PDF: fpdf2 (already installed; Playwright/Chromium cannot run on the cPanel server).
- Scans and photos: read by the AI providers already set up (Claude, ChatGPT, Gemini, Groq with
  B17 failover; Groq has no vision, so it is skipped for images). No Tesseract (not on the server).
- Access: Core (always on), any signed-in applicant of any service. Free.

How it fits the existing software (instead of the brief's own tables)
- users -> the existing applicant_accounts. A CV belongs to the account it was made in. The API
  lives under /me/{module}/cv/... like every applicant route; module is the service the person is
  signed in to (course, study, job, visa, remote). Licence: Core, so no MODULE_NOT_LICENSED
  check of its own beyond the service of the account.
- AI: app/ai providers + failover (B17); keys and models from Settings; nothing new to configure.
- audit_log: the existing table. Every data change writes one row as always. AI calls are counted
  in a new cv_ai_calls table (service, provider, tokens if given, status) - never document text.
- Rate limiting: the existing rate_events table.
- File storage: the existing storage folder (B06), encrypted with the existing app crypto.
- Payments, licence, settings: unchanged.

Placement in the website (owner: "one place, and an option in every service next to the agents")
- One page: /cv-agent - the dashboard and the wizard.
- In Consultancy, Jobs, Immigration, Remote Jobs and Courses: a "Build my CV with AI" card next to
  the existing agent (same card style), linking to /cv-agent?from=<service>.
- In each profile: "My CVs" link. Accent colour of the CV pages: #4F46E5 (profile).
- Signed out: the page shows what it does and the normal sign-in / sign-up of that service.

Wizard (as in the brief, Steps 1-8, with these exact choices)
1. CV type cards (9 types) + "Also create a cover letter" switch.
2. Destination country flags (18 countries + "Other" with a searchable list).
3. Category chips (16) + optional job advert text (a link is stored as text only; the server
   never fetches it).
4. Upload: PDF, DOC, DOCX, JPG, PNG; up to 10 files, 10 MB each; type checked by content.
   Document chips (Existing CV, Academic certificates, Experience letters, Training certificates,
   Professional licences, Language test, Passport). Consent checkbox required before upload:
   "I confirm these documents are mine and I agree to AI processing."
   No documents at all -> the agent asks the questions instead (Step 5 form).
   .doc (old Word) cannot be read on the server (Decisions 6): it is accepted, and the person is
   asked to upload it as PDF/DOCX or answer the questions instead.
5. "Reading your documents..." -> editable cards per section, each item with "From: <file>",
   low-confidence and conflicting items marked "Please confirm"; a short form (max 6 fields per
   screen, dropdowns / dates / chips) for missing essentials only.
6. Templates: Modern Professional, Corporate, Minimalist, Technical, Academic, Europass,
   International Recruitment - one "Recommended" from country + CV type. 1 page / 2 pages.
7. Split screen (stacked on phones): section editor + A4 preview drawn to the same layout as the
   PDF. Per section: Edit, Regenerate, Make shorter, Make stronger, Remove. Template change keeps
   content. Quality panel. "Approve CV" only with no blocking issues.
8. Export PDF and DOCX, file name Firstname_Lastname_CV_Country.pdf / .docx; cover letter tab
   with the same actions.
Dashboard: title "NextGen LearninG - AI CV Agent - Professional CV Builder", the tagline, "Create
new CV" + type cards, saved CVs (title, country, last edited, Draft / Approved) with Open,
Duplicate, Delete; footer badges PDF - DOCX - Maximum 2 pages - ATS-friendly.
The brand name shown comes from Settings (CLAUDE.md rule); "AI CV Agent" is the product label.
Progress auto-saves after every step.

AI services (backend/app/cv/, one file each, typed, strict JSON checked with Pydantic, one retry
on invalid JSON; prompts in backend/prompts/cv/*.md so the owner can edit them)
- extractor.py, merger.py, gap_checker.py, writer.py, reviewer.py, cover_letter.py.
- Every Writer / Reviewer / Cover letter prompt carries the brief's non-negotiable rules
  (never invent; no new numbers; no keyword stuffing; no job/visa guarantee; reverse
  chronological; country spelling).
- Code checks after the AI too: every employer, school, date, grade and number in the written CV
  must exist in the confirmed data; otherwise the item is rejected and regenerated (like the B17
  grounding check).
- Passport: sent to AI only when the "Passport" chip is ticked; only name and nationality are
  kept; the passport number is dropped and can never appear in the CV.

Country rules: backend/config/countries/*.yaml (18 countries + default + europass), fields as in
the brief. Needs the PyYAML package (see Packages). Sensitive fields (photo, date of birth,
marital status, nationality, gender, religion) are off unless the country allows them AND the
user turns them on; passport number never.

Quality checks (Reviewer + code): as in the brief section 6, blocking / warning. Page length is
checked by laying the CV out with fpdf2 (real page count), not guessed.

Data (migration per phase; no sample data)
- cv_projects: id, applicant_id -> applicant_accounts, module, cv_type, country, category,
  template, page_length (1|2), cover_letter boolean, status (draft|approved|deleted),
  job_advert_text, title, step (1-8), created_at, updated_at.
- cv_files: project_id, file_name, doc_kind, mime, size_bytes, storage_path, sha256,
  extraction_status, delete_after (created + 30 days), deleted_at.
- cv_versions: project_id, version, data jsonb (the CV schema), reason (extracted|edited|
  regenerated|...), created_at. Append-only; undo = make a new version from an old one.
- cover_letters: project_id, version, text, created_at (append-only like cv_versions).
- cv_ai_calls: project_id, service, provider, status, input_tokens, output_tokens, created_at.
All with the CLAUDE.md table rules (uuid id, created_at, updated_at trigger, indexed FKs,
ON DELETE RESTRICT, CHECK lists).

Privacy and security
- Files encrypted at rest; content removed after 30 days (setting cv_file_days, default 30) by
  the existing scheduled worker; the person can remove a file at any time. "Delete CV" sets
  status deleted and removes its files' content; rows stay for the audit trail (Decisions 2).
- No document text or personal data in logs, audit rows or cv_ai_calls.
- Rate limits (rate_events): uploads 30 per hour; AI calls 40 per person per day (setting
  cv_ai_per_day) since the agent is free.
- File type by content (magic bytes); a virus-scan hook as an interface that returns "clean"
  until a scanner is set up.
- Order of checks as always: signed in -> licensed service -> own project -> input -> work.

Packages (new; need the owner's yes - CLAUDE.md "no packages outside Scope")
- Backend: PyMuPDF (PDF text and page images), python-docx (DOCX read + write), PyYAML (country
  files). All three are plain pip wheels that install on the cPanel Python 3.12.
- Fonts: the PDF uses fonts embedded with fpdf2 (DejaVu Sans / Serif-like, Liberation fonts as
  Arial / Times / Calibri look-alikes, bundled in backend/fonts, open licences).
- No frontend packages.

Build phases (owner approves after each; each: live -> localhost -> git push)
1. Foundation: migration 0026 (cv_projects, cv_files, cv_versions, cover_letters, cv_ai_calls),
   project CRUD + auto-save, upload with content check, encryption, consent, limits, 30-day
   clean-up; pytest.
2. Wizard UI: /cv-agent dashboard, Steps 1-4 with auto-save, the "Build my CV with AI" cards in
   every service and "My CVs" in profiles. No AI yet.
3. AI extraction: Extractor, Merger, Gap Checker, Step 5 screen; prompts files; tests with fixture
   documents and mocked AI answers.
4. Generation: country YAML files, Writer, the 7 templates (fpdf2 + matching HTML preview),
   Steps 6-7, section actions, versions / undo.
5. Quality and export: Reviewer, quality panel, PDF and DOCX export, cover letter.
6. Hardening: privacy checks, rate limits, the full test list of the brief section 9 (except the
   browser end-to-end test, Decisions 4), README and deployment notes.

Acceptance (whole project): as in the brief - a person completes a CV only by clicking options,
uploading documents and answering the missing fields, and downloads an ATS-friendly PDF and
DOCX of at most 2 pages; USA CV never has a photo or date of birth; nothing is invented (the
grounding check refuses invented employers, dates, grades and numbers).

Decisions for the owner (answer before Phase 1)
1. New packages PyMuPDF, python-docx, PyYAML (backend) and bundled open-licence fonts. Allowed?
2. "Delete CV": status 'deleted' + file content removed, rows kept (the project never hard-deletes
   records). OK?
3. Bengali / English UI toggle: not built now; all CV Agent texts are kept in one strings file
   (frontend/src/components/cv/strings.ts) so Bengali can be added later. OK?
4. Browser end-to-end test (Playwright): it needs a new frontend dev package and a browser on
   the PC. Proposed instead: an API end-to-end pytest (sign in -> wizard -> upload sample CV ->
   generate -> export, AI mocked) plus the live server check like B27. OK?
5. Free with limits: 40 AI calls per person per day and files kept 30 days, both changeable by
   the super admin in Settings. OK?
6. The old .doc format cannot be read on the server (no LibreOffice). Proposed: accept .doc but
   ask the person to upload PDF/DOCX or answer questions instead. OK?
