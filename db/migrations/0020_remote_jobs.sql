-- Remote jobs: a vacancy can be done remotely (work from home, no travel to the employer's country).
-- The job agent form can then look for remote or on-site roles only.

ALTER TABLE vacancies ADD COLUMN remote boolean NOT NULL DEFAULT false;

CREATE INDEX vacancies_remote_idx ON vacancies (remote);
