Spec B08 - Notifications: real email (SMTP) and WhatsApp (Cloud API) sending, retries, delivery log

Purpose
Actually deliver the messages that every earlier spec writes to the notifications outbox -
verification codes, application updates, payment receipts, reminders - by email and WhatsApp,
retry when a provider is down, record what happened to each message, and let staff see and
resend them. Endpoints follow the notify part of specs/F02_api_contract_mock.md and F10.

Scope
In scope:
- db/migrations/0008_notifications_sending.sql:
  - notifications: add next_attempt_at, sent_at, last_error (short, no secrets),
    provider_message_id, and status value 'sending'. Index on (status, next_attempt_at).
  - settings: replace the mail API key with smtp_host, smtp_port, smtp_security CHECK
    ('starttls','ssl','none'), smtp_username; SMTP password goes to settings_secrets.
    Add whatsapp_phone_number_id, whatsapp_template_name, whatsapp_template_language,
    whatsapp_api_version (default 'v21.0'); the WhatsApp access token stays in settings_secrets.
    The old mail API key secret is no longer used (not deleted).
- app/notify/: outbox.py (the single function every spec uses to queue a message - replace any
  direct inserts from B03-B07 with it), email_smtp.py (Python's built-in smtplib and
  email.message - no new package), whatsapp.py (httpx), worker.py.
- Worker: started with the app (FastAPI lifespan). Every 10 seconds it takes up to 20 due
  messages with SELECT ... FOR UPDATE SKIP LOCKED, sends them, and records the result.
- Endpoints below. PUT /api/settings (B02) accepts and validates the new fields.
Out of scope: SMS, push notifications, marketing or bulk email, email templates editable by the
admin, receiving replies, read receipts.

Contract (all under /api)
- GET  /admin/notifications?channel=&status=&q=&page=  (50 per page)   any admin role
  -> time, channel, to, to_name, module, event, subject, body (codes masked), status, tries,
     sent_at, last_error.
- POST /admin/notifications/{id}/resend   any admin role - only for 'failed' or 'queued';
  sets status queued and next_attempt_at now (CONFLICT for 'sent' or 'sending').
- POST /admin/settings/test-email {to}      SA -> sends one test email at once, returns
  {ok, error?}; writes no outbox row.
- POST /admin/settings/test-whatsapp {to}   SA -> same for WhatsApp.
- queue_message(conn, to_name, email?, phone?, module?, event, subject, body) -> writes one email
  row (if email) and one WhatsApp row (if phone) in the caller's transaction.

Functional rules
- Email is sent only if smtp_host, sender email and the SMTP password are set; otherwise the row
  stays queued with last_error "Email is not set up". WhatsApp likewise needs phone number id,
  access token and template name.
- Email: From "<sender name> <sender email>", Reply-To the company email, plain-text body plus a
  simple HTML version (company name at the top, body text escaped - never raw HTML from data,
  footer with company address). Subject max 200 characters. Timeout 20 seconds.
- WhatsApp: POST https://graph.facebook.com/<api version>/<phone number id>/messages with
  "Authorization: Bearer <token>", type "template", the configured template name and language,
  and one body parameter = the message text shortened to 1,000 characters. Phone numbers are
  changed to international form (01XXXXXXXXX -> 8801XXXXXXXXX); an invalid number makes the row
  failed with "Invalid phone number" and no retry. Confirm the request format against Meta's
  current WhatsApp Cloud API documents before writing the client; if it differs, stop and tell me.
- Retries: a temporary failure (timeout, connection error, SMTP 4xx, HTTP 5xx or 429) retries
  after 1 minute, then 5 minutes, then 30 minutes; after 4 tries the status is failed. A permanent
  failure (SMTP 5xx, HTTP 4xx other than 429, bad address) is failed at once.
- 'sending' rows older than 10 minutes (for example after a crash) go back to queued.
- A message is never sent twice on purpose: the row is marked 'sending' and committed before the
  provider is called; the result is saved right after.
- Masking: in the admin list and in logs, 6-digit codes in messages with event
  email_verification or password_reset are shown as "••••••". The real code is only in the
  message that leaves the system.
- In development (APP_ENV=development) verification and reset codes are still printed to the
  console (B03) whether or not sending works.
- At most 30 emails and 30 WhatsApp messages per minute; the rest wait for the next round.
- Secrets (SMTP password, WhatsApp token) never appear in last_error, logs, responses or audit rows.
- Audit rows: "Message resent", "Test email sent", "Test WhatsApp sent", and "Settings saved"
  (B02) for the new fields. Sending by the worker is recorded on the notification row, not in audit.

Edge cases
- Provider down for an hour: messages wait and go out after it comes back (within the retry plan),
  or end as failed and can be resent.
- The app runs with two workers at once: SKIP LOCKED makes sure each message is taken by one only.
- Settings changed while messages are queued: the next attempt uses the new settings.
- Very long body: email keeps it; WhatsApp sends the first 1,000 characters plus "…".

Non-functional rules
- No new packages.
- Tests never contact a real mail server or Meta: SMTP and HTTP are replaced with fakes.
- The worker can be turned off with NOTIFY_WORKER=off in backend/.env (tests do this and call the
  sending function directly).
- pytest passes, including all earlier tests.

Acceptance criteria
- b86 Migration 0008 applies; old notifications rows are kept.
- b87 With SMTP not set up, a queued email stays queued with "Email is not set up".
- b88 With fake SMTP set up, the worker sends a queued email, sets sent and sent_at, and the fake
  received From, Reply-To, subject, text and HTML parts; the HTML part has the body escaped.
- b89 A fake SMTP timeout retries after 1, 5 and 30 minutes and is failed after 4 tries; an SMTP
  550 is failed at once.
- b90 Fake WhatsApp: the request has the template name, language, the phone as 8801XXXXXXXXX and
  the Bearer token header; a 401 is failed at once; a 429 retries.
- b91 Two workers running together send each message exactly once.
- b92 A 'sending' row older than 10 minutes goes back to queued.
- b93 The admin list masks verification and reset codes; resend works for failed and is CONFLICT for sent.
- b94 test-email and test-whatsapp return ok with the fakes and write an audit row; as an admin
  (not super) they are FORBIDDEN.
- b95 No log line, last_error, response or audit row contains the SMTP password or WhatsApp token.
- b96 B03-B07 now queue messages only through queue_message (the test searches the code for
  other
