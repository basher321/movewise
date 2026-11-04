Spec B04 - Catalog (course groups, courses, universities, vacancies), fees, match and agent answers

Purpose
Store everything the company offers - course groups and courses, universities, and overseas
vacancies with employer verification - plus the application fees, and serve them to the public
website and the matching agents with the module lock applied. The database starts empty; the
Super Admin adds every item. Endpoints follow the catalog, match and fee parts of
specs/F02_api_contract_mock.md, F06, F07 and F11.

Scope
In scope:
- db/migrations/0004_catalog.sql:
  - course_groups: id, name, description, sort_order, active. (The headings on the Courses page,
    for example "Artificial Intelligence - Practical tracks for builders...".)
  - courses: id, slug (unique, made from the title, never changed), group_id, title, icon
    (one emoji), colour (#RRGGBB), price_poisha CHECK > 0, duration, level, description,
    learn_points text[] ("What you will learn"), syllabus text[] (modules), published,
    created_at, updated_at.
  - universities: id, slug, name, country, city, levels text[], fields text[], tuition_usd,
    min_gpa numeric(3,2) CHECK 0-4, min_ielts numeric(2,1) CHECK 0-9, intakes, deadline_text,
    scholarships, work_rights, conditions, apply_link, admissions_email, fee_override_poisha
    (null = default), published, created_at, updated_at.
  - vacancies: id, slug, title, employer, country, occupation, min_experience, min_education
    (0-3), min_english (0-2), salary_usd, seats, apply_by, contract, benefits, conditions,
    employer_licence, employer_email, employer_verified, closed, fee_override_poisha,
    created_at, updated_at.
  - No rows are inserted. No sample data.
- Routers: public catalog, admin catalog, fees, match, agent answers (below).
- app/match.py: the scoring rules below, shared by match and agent.
Out of scope: applications and the "already applied" visibility exception (B05), enrolments
(B09), payments, a real LLM for the agent (a later optional spec), images for items, deleting
anything.

Contract (all under /api)
Public (P) - module must be licensed, otherwise 403 MODULE_NOT_LICENSED:
- GET /courses -> course groups (active, sort_order) each with its published courses.
- GET /courses/{slug}                         404 if missing or unpublished.
- GET /universities, GET /universities/{slug} only published.
- GET /vacancies, GET /vacancies/{slug}       only open (not closed) with employer_verified.
- Every public university and vacancy includes fee_poisha = effective fee.
- POST /match/study {level, field, gpa, ielts, budget_usd}
- POST /match/job {occupation, country, experience, education, english, passport_ready,
  salary_goal_usd}
  Both return [{item, checks: [{ok, label}], match_percent}] sorted by match_percent, highest first.
- POST /agent/{module}/ask {question, inputs} -> {answer} (rule-based for now, same replies as
  the reference fallback).
- GET /catalog/options -> {study_levels, study_fields, occupations, countries, education_levels,
  english_levels} built from published data plus the fixed lists, for the agent forms.
Admin (SA, module licensed):
- GET /admin/course-groups, POST /admin/course-groups, PUT /admin/course-groups/{id}
- GET /admin/courses, POST /admin/courses, PUT /admin/courses/{id}
- GET /admin/universities, POST, PUT /admin/universities/{id}
- GET /admin/vacancies, POST, PUT /admin/vacancies/{id}
  Admin lists return every item, including unpublished, closed and unverified, with
  applied_count (0 until B05 adds applications).
- GET /admin/fees -> {defaults: {study, job}, universities: [...], vacancies: [...]} with
  default, override and effective fee per item.
- PUT /admin/fees {study: {id: poisha|null}, job: {id: poisha|null}}
- POST /admin/fees/reset {scope: "study"|"job"|"all"}
- There is no DELETE endpoint for any catalog item.

Functional rules
- Match scoring (must match the reference sc() exactly): each check has a weight; match_percent
  = round(30 + 70 x (sum of weights of passed checks) / (sum of all weights)).
  Study: only published universities offering the level and the field. Checks: GPA >= min (2),
  IELTS >= min (2; label "IELTS <min> needed" when ielts is 0), budget >= tuition (1.5).
  Job: only open, verified vacancies with the occupation, and the country unless "Any country".
  Checks: experience >= min (2), education index >= min (1.5), English index >= min (1),
  passport ready (2), salary >= goal or no goal (1).
  Labels are copied from the reference match().
- Validation exactly as F11: course price whole taka above 0 (stored x100 as poisha), title and
  group required, colour #RRGGBB, at least one learn point and one syllabus module; university
  GPA 0-4, IELTS 0-9 in steps of 0.5, at least one level and one field, apply_link must start with
  https://, valid emails; vacancy salary above 0, experience 0 or more, seats 1 or more if given,
  apply_by not in the past while open.
- Slugs: lower-case words joined by "-", made from the name or title at creation, a short
  suffix if taken, never changed by later edits.
- effective fee = fee_override_poisha if set, else the default for that module from settings.
  A fee override equal to the default is stored as null. Every fee must be a whole number above 0.
- Fee changes never change payments that already exist (enforced in B07; noted here).
- Changing employer_verified writes its own audit row ("Employer verified" / "Employer
  unverified"). Every other create or update writes one audit row naming the item and the
  changed field names.
- All money in requests and responses is poisha (integers).

Edge cases
- Empty catalog: public lists return [] (not an error); match returns [].
- A course group with no published courses is not returned on the public page.
- Unknown slug: 404 NOT_FOUND.
- A vacancy whose apply_by date passes stays open (staff decide) but the admin list flags it
  "past apply-by date".

Non-functional rules
- No new packages.
- Public list endpoints return at most 500 items and use indexes on published / closed /
  employer_verified.
- pytest passes, including all earlier tests.

Acceptance criteria
- b32 Migration 0004 applies; the catalog tables are empty.
- b33 With only study licensed, GET /courses and GET /vacancies are 403 MODULE_NOT_LICENSED and
  GET /universities works; admin course endpoints are 403 for a super_admin too.
- b34 SA creates a course group and a course with price 12000 taka; it is stored as 1200000 poisha
  and appears in GET /courses; unpublishing hides it.
- b35 A vacancy with employer_verified false or closed true is not in GET /vacancies nor in
  /match/job; it is in GET /admin/vacancies.
- b36 /match/study gives the same match_percent and labels as the reference for three fixed
  inputs (expected numbers written in the test).
- b37 /match/job filters by country unless "Any country" and handles an empty salary goal.
- b38 Effective fee: default when override is null; override when set; PUT /admin/fees with a value
  equal to the default stores null; 0 or 12.5 is VALIDATION; reset clears overrides.
- b39 University validation: GPA 5, IELTS 6.3 and an http:// link are VALIDATION.
- b40 An admin (role admin) and a finance user get FORBIDDEN on every /admin catalog and fee endpoint.
- b41 There is no DELETE route for any catalog item (the test lists the app routes).
- b42 Changing employer_verified writes "Employer verified"; every create or update writes exactly
  one audit row.
- b43 Slug stays the same after the name is edited; a second item with the same name gets a suffix.
- b44 /agent/study/ask returns a non-empty answer; with study unlicensed it is 403.

Assumptions
- Specs B01-B03 are complete and committed.
- Default fees and the licence come from B02; actors and roles from B03.
