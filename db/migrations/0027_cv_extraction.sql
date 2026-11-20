-- 0027_cv_extraction: the CV Agent keeps what the Extractor read from each file, and whether it
-- was already merged into the CV (spec B28, phase 3). Two columns are added; nothing is removed.

ALTER TABLE cv_files
  ADD COLUMN extracted jsonb,
  ADD COLUMN merged boolean NOT NULL DEFAULT false;
