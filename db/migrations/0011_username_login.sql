-- 0011_username_login: applicants sign up and sign in with a username and password, without an
-- email code (owner decision, 2026-11-01). Email becomes optional.
--
-- The owner allowed exactly the two statements below that contain DROP (2026-11-01). Neither
-- deletes any row or data: they only let applicant_accounts.email be empty (NULL).

ALTER TABLE applicant_accounts
  ADD COLUMN username text CHECK (username IS NULL OR username ~ '^[a-z0-9._]{3,30}$');

-- One username per module (stored in lower case). Accounts made before this have no username
-- and keep signing in with their email.
CREATE UNIQUE INDEX applicant_accounts_module_username_key
  ON applicant_accounts (module, username) WHERE username IS NOT NULL;

-- Allowed by the owner (1 of 2):
ALTER TABLE applicant_accounts ALTER COLUMN email DROP NOT NULL;

-- Allowed by the owner (2 of 2): the old rule "email must not be empty", replaced at once by one
-- that also allows no email.
ALTER TABLE applicant_accounts DROP CONSTRAINT applicant_accounts_email_check;
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_email_not_blank CHECK (email IS NULL OR btrim(email) <> '');

-- Every account needs a way to sign in: a username or (older accounts) an email.
ALTER TABLE applicant_accounts
  ADD CONSTRAINT applicant_accounts_has_login CHECK (username IS NOT NULL OR email IS NOT NULL);
