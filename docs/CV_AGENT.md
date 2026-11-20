# AI CV Agent (spec B28)

A click-driven CV builder for overseas jobs, skilled migration, study applications and remote
work. Part of Core: free for every signed-in applicant of any licensed service.

- Page: `/cv-agent` (dashboard and the 8-step wizard). Each service page (Courses, Consultancy,
  Jobs, Immigration, Remote Jobs) has a "Build my CV with AI" card next to its agent, and every
  profile has a "My CVs" button.
- The CV belongs to the account of the service the person came from (`?from=job`).

## How it works

1. CV type, 2. country, 3. category and optional job advert, 4. documents (consent first),
5. the agent reads the documents and asks only for what is missing, 6. template and length,
7. review with live A4 preview (the real PDF), section actions and the quality check, approve,
8. download PDF / DOCX and the cover letter.

The AI never writes facts. Employers, schools, titles, dates and grades are copied by the code
from the confirmed data; the AI only writes the summary, the bullets and the order of skills.
After every AI answer the code drops any number that is not in the person's own data, any skill
the person does not have, and any promise of a job, visa or admission.

## Files

| What | Where |
|---|---|
| Services (one per file) | `backend/app/cv/` - `extractor.py`, `merger.py`, `gap_checker.py`, `writer.py`, `reviewer.py`, `cover_letter.py` |
| AI calls (JSON, retry, counting, daily limit) | `backend/app/cv/ai_client.py` |
| Prompts - edit freely, read on every call | `backend/prompts/cv/*.md` (`rules.md` is added to the writer, reviewer and cover letter prompts) |
| Country rules - edit freely, read at start-up | `backend/config/countries/*.yaml` (18 countries, `default.yaml`, `europass.yaml`) |
| Layout, PDF, DOCX | `backend/app/cv/layout.py`, `render_pdf.py` (fpdf2), `render_docx.py` (python-docx) |
| Fonts (SIL Open Font Licence) | `backend/app/cv/fonts/` - Carlito (Calibri metrics), Tinos (Times metrics) |
| Encrypted file storage, clean-up | `backend/app/cv/storage.py`, `cleanup.py` |
| API | `backend/app/routers/cv.py` (projects, uploads), `cv_agent.py` (AI, review, export) |
| Screens | `frontend/src/components/cv/`, texts in `strings.ts` (ready for a Bengali version) |
| Tests | `backend/tests/test_cv_foundation.py`, `test_cv_agent.py`; `frontend/src/lib/cv/__tests__/` |

## Settings (super admin)

Admin -> Settings -> "AI CV Agent": AI actions per person per day (default 40) and days uploaded
documents are kept (default 30). The AI providers and keys are the ones under "AI assistants".

## Privacy

- Nothing is uploaded before the consent box is ticked. File types are checked by content.
- Files are stored encrypted (AES-256-GCM, key from SECRET_KEY) under `STORAGE_DIR/cv/` and their
  content is removed after the keep period by the every-minute job (`python -m app.notify.run --once`).
  The person can remove a file at any time; "Delete CV" removes all its files.
- A passport is read only when the "Passport" chip is ticked, and only for name and nationality.
- Document text is never logged; `cv_ai_calls` keeps only service, provider, status and tokens.
- A virus-scan hook is in `storage.scan_for_viruses()` (passes every file until a scanner is added).

## Deployment notes (cPanel)

1. Back up the database (`releases/backup_db.sh`).
2. Copy the backend files, then install the three new packages in the app's virtualenv:
   `~/virtualenv/movewise/backend/3.12/bin/pip install pymupdf==2.1 python-docx==1.2.0 PyYAML==6.0.3`
3. Run `python -m app.db.migrate` (adds 0026 and 0027), then `touch backend/tmp/restart.txt`.
4. Build the frontend with `API_ORIGIN` set and swap `standalone/` as usual.
5. No crontab change: the clean-up runs inside the existing notification job.

## What to test by hand

1. Open Jobs -> "Build my CV" -> sign in -> choose "Overseas Jobs", Germany, Construction.
2. Tick "Existing CV", tick consent, upload a PDF CV and an experience letter (a photo works too).
3. Step 5: check the cards; confirm any yellow "Please confirm" item; answer missing questions.
4. Step 6: pick a template (Recommended is marked), 1 or 2 pages -> "Write my CV".
5. Step 7: try Regenerate / Make shorter / Remove / Undo; change the template; run "Check
   spelling with AI"; approve.
6. Step 8: download PDF and DOCX (name `Firstname_Lastname_CV_Germany.pdf`), write the cover letter.
7. Without any document: a new CV for the UK, press Next on Step 4 and answer the questions.
8. On a phone (390 px) and in dark mode.
