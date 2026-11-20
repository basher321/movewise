-- 0024_eps_gateway: EPS (Easy Payment System) as a separate payment method, spec B26.
-- Two settings columns, and the payment method rules widened to allow 'eps'.
-- EPS secrets live in app_secrets (eps.store_id, eps.username, eps.password, eps.hash_key),
-- whose name rule already allows them, so settings_secrets is not changed.
--
-- The owner allowed the DROP CONSTRAINT statements below (2026-11-19, spec B26 Decisions 1).
-- Each one removes an old CHECK rule and at once adds a wider rule that also allows EPS.
-- No table, column, index or row is removed.

ALTER TABLE settings
  ADD COLUMN eps_enabled boolean NOT NULL DEFAULT false,
  ADD COLUMN eps_sandbox boolean NOT NULL DEFAULT true;

ALTER TABLE settings DROP CONSTRAINT settings_payment_method_on;
ALTER TABLE settings
  ADD CONSTRAINT settings_payment_method_on
    CHECK (sslcommerz_enabled OR bkash_enabled OR nagad_enabled OR manual_enabled OR eps_enabled);

ALTER TABLE payments DROP CONSTRAINT payments_method_check;
ALTER TABLE payments
  ADD CONSTRAINT payments_method_check CHECK (method IN ('sslcommerz', 'bkash', 'manual', 'eps'));
