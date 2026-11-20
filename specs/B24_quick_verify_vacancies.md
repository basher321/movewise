# B24 Quick verify of vacancies

Owner request (2026-11-09): opening and saving each vacancy to tick "Employer verified" takes too
long. A vacancy shows on /jobs only when it is open and its employer is verified; that rule stays.

## Scope

In Super Admin > Catalog > Employers & vacancies only (not Remote Jobs):

- A "Verify" link on every row that is open and not verified: one click verifies that vacancy.
- A "Verify all (n)" button, n = open vacancies that are not verified. It asks once before doing
  anything ("Yes, verify n"), and says those jobs will go live on the website.
- Closed vacancies are left out of both. Nothing else about a vacancy changes.

## API

POST /api/admin/vacancies/verify, body {"ids": [vacancy id, ...]} (1 to 1000 ids) -> {"verified": n}.

Order of checks: signed in -> Job Processing licensed -> super admin -> input valid -> work.
All or nothing, in one transaction. An unknown id, or the id of a remote job: NOT_FOUND 404. A
vacancy that is already verified is left as it is and not counted.

Audit: one "Employer verified" row per vacancy that changed, in the same transaction, the same as
ticking the box in the form.

## Tests

backend/tests/test_verify_vacancies.py, on movewise_test only: verifies and shows on the public
list; only the flag changes; already verified not counted; audit rows; unknown id and remote id
change nothing; empty list; check order (not signed in, unlicensed, admin, finance).
