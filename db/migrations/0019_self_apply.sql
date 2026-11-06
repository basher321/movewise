-- 0019_self_apply: Self Apply for universities. The applicant pays a separate self-apply fee and
-- then gets the official application link; staff do not process stages or documents for it.
-- Only adds columns. Nothing is dropped or deleted.

-- The self-apply fee per university, set by staff. NULL: Self Apply is not offered yet.
ALTER TABLE universities
  ADD COLUMN self_apply_fee_poisha bigint
    CHECK (self_apply_fee_poisha IS NULL OR self_apply_fee_poisha > 0);

-- true: a Self Apply record (payment and link only); false: the agent-processed application.
ALTER TABLE applications
  ADD COLUMN self_apply boolean NOT NULL DEFAULT false
    CHECK (NOT self_apply OR module = 'study');
