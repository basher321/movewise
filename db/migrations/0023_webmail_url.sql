-- 0023_webmail_url: the company webmail address (for example https://webmail.example.com), set in
-- Settings by the super admin and opened from the admin panel. Empty: no Webmail button. Only a
-- column is added.

ALTER TABLE settings
  ADD COLUMN webmail_url text NOT NULL DEFAULT ''
    CHECK (webmail_url = '' OR (webmail_url LIKE 'https://%' AND length(webmail_url) <= 500));
