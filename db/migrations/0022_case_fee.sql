-- 0022_case_fee: a fee set by staff for one application (case). NULL: the case pays the fee of
-- its item (university, vacancy, visa programme or remote job). Only a column is added.

ALTER TABLE applications
  ADD COLUMN fee_override_poisha bigint
    CHECK (fee_override_poisha IS NULL OR fee_override_poisha > 0);
