Spec B07 - Payments: SSLCommerz, bKash, manual payments, invoices, ledger, refunds, outstanding

Purpose
Take application-fee payments safely and keep the money records reliable: start a payment, send
the payer to SSLCommerz or bKash, confirm the payment on the server with the gateway, accept
bank / office payments that finance verifies, issue gap-free invoices, keep an append-only ledger,
handle refunds, and never charge twice. A shared payment service is built so B09 can use it for
course enrolments. Endpoints follow the money parts of specs/F02_api_contract_mock.md, F05, F06,
F07 and F09.

Scope
In scope:
- db/migrations/0007_payments.sql:
  - payments: id, applicant_id, module, ref_type CHECK ('application','enrolment'), ref_id,
    purpose, amount_poisha CHECK > 0, currency 'BDT', method CHECK ('sslcommerz','bkash',
    'manual'), status CHECK ('initiated','pending_verify','paid','failed','cancelled',
    'abandoned','rejected','refunded','duplicate'), tran_id (our id, unique), gateway_ref,
    manual_ref, payer_phone, verified_by, decision_note, created_at, paid_at, updated_at.
    A partial unique index allows only ONE payment per (ref_type, ref_id) in status
    'initiated', 'pending_verify' or 'paid'. DELETE blocked by trigger.
  - payment_events: id, payment_id, at, kind, detail jsonb (gateway answers with secrets removed).
    UPDATE and DELETE blocked.
  - invoice_counters: year, last_no. invoices: no (unique), payment_id (unique), applicant_id,
    module, name, email, description, method, amount_poisha, issued_at, company_name,
    company_address, company_email, vat_bin, footer (a snapshot at issue time), refunded,
    refunded_at. DELETE blocked; only refunded and refunded_at may change (trigger).
  - ledger_entries: id, at, direction CHECK ('in','out'), category CHECK (the F09 lists), party,
    email, description, method, amount_poisha CHECK > 0, ref, auto, reverses_id, created_by.
    UPDATE and DELETE blocked.
  - refunds: id, invoice_no (unique - one refund per invoice), applicant_id, amount_poisha,
    reason, status CHECK ('requested','approved','declined'), decided_by, decision_note,
    refund_method, refund_ref, requested_at, decided_at. DELETE blocked.
- app/payments/: service.py (start, confirm, mark paid, on_paid handler registry), sslcommerz.py,
  bkash.py (gateway clients using httpx), invoices.py, ledger.py.
- New config: PUBLIC_API_URL (the backend address the gateways call back) and
  PUBLIC_SITE_URL (the frontend address the payer returns to), in backend/.env.
- Endpoints below. The application on_paid handler: sets fee_paid true, adds the public event
  "Application fee paid (৳x)" (B05).
Out of scope: course enrolment payments (B09 registers its own on_paid handler), direct Nagad,
automatic refunds through the gateway API, subscriptions, real email sending (B08 - this spec only
writes to the outbox).

Contract (all under /api)
Applicant (A, own records only - otherwise 404):
- POST /me/{module}/applications/{id}/pay {method, phone, manual_ref?}
  -> gateway: {payment_id, redirect_url}; manual: {payment_id, status: "pending_verify"}
- GET  /me/payments/{id} -> {status, amount_poisha, purpose, invoice_no?} (for the result page)
- GET  /me/{module}/invoices, GET /me/{module}/invoices/{no}
- POST /me/{module}/refunds {invoice_no, reason}
Gateway callbacks (public; exempt from the B03 Origin check; never trusted on their own):
- POST /pay/sslcommerz/success | /fail | /cancel   (the payer's browser, form post)
- POST /pay/sslcommerz/ipn                          (SSLCommerz server)
- GET  /pay/bkash/callback?paymentID=&status=
  Each ends by redirecting the browser (303) to PUBLIC_SITE_URL/payment/result?id=<payment_id>.
Finance (require_finance_or_super):
- GET  /admin/payments/pending, POST /admin/payments/{id}/verify, POST /admin/payments/{id}/reject {reason}
- GET  /admin/refunds, POST /admin/refunds/{id}/approve {refund_method, refund_ref},
  POST /admin/refunds/{id}/decline {reason}
- GET  /admin/outstanding, POST /admin/outstanding/{applicant_id}/remind
- GET  /admin/ledger?direction=&period=all|month&page=, POST /admin/ledger,
  POST /admin/ledger/{id}/reverse {reason}, GET /admin/ledger/summary?period=,
  GET /admin/ledger.csv?direction=&period=
- GET  /admin/invoices?q=&module=&page=, GET /admin/invoices/{no}
  (also readable by require_section(module) for that module's invoices - the F08 table)

Functional rules
Starting a payment
- Only for an active or on_hold application with fee_paid false. The amount is the effective fee
  at that moment and is stored on the payment; later fee changes never change it.
- The method must be enabled in Settings, and a gateway must have its secrets saved
  (VALIDATION otherwise). phone must be a valid Bangladeshi mobile.
- If a payment for the same application is already 'paid' or 'pending_verify': CONFLICT.
  If one is 'initiated': ask the gateway for its status first; if it was paid, record it and
  return CONFLICT; otherwise mark it 'abandoned' and start the new one.
- manual: manual_ref required; status pending_verify.
SSLCommerz
- Start: POST to {base}/gwprocess/v4/api.php (sandbox base https://sandbox.sslcommerz.com, live
  https://securepay.sslcommerz.com, chosen by the sandbox flag) with store id and password,
  total_amount in taka (2 decimals), currency BDT, tran_id, success / fail / cancel / ipn URLs,
  customer name, email, phone, product name = purpose. Redirect the payer to GatewayPageURL.
- Confirm (success callback or IPN): take val_id, call {base}/validator/api/validationserverAPI.php
  with val_id, store id, password, format json. Accept only status VALID or VALIDATED, and only
  when tran_id, amount and currency BDT match the stored payment exactly. risk_level 1 -> status
  pending_verify with note "High-risk payment - check before accepting" (finance decides).
- fail / cancel callbacks mark the payment failed / cancelled only if it is still initiated.
bKash (tokenized checkout)
- Get a token with POST {base}/tokenized/checkout/token/grant (app key, app secret, username,
  password); keep it in memory until it expires. Sandbox base
  https://tokenized.sandbox.bka.sh/v1.2.0-beta; live https://tokenized.pay.bka.sh/v1.2.0-beta.
- Start: POST {base}/tokenized/checkout/create (mode 0011, payerReference = phone, callbackURL,
  amount in taka, currency BDT, intent sale, merchantInvoiceNumber = tran_id). Redirect to bkashURL.
- Callback with status=success: POST {base}/tokenized/checkout/execute with paymentID; if the
  answer is unclear or times out, POST {base}/tokenized/checkout/payment/status. Accept only
  transactionStatus Completed with the same amount and merchantInvoiceNumber. Store trxID as
  gateway_ref. status failure / cancel -> failed / cancelled.
- Before writing the clients, confirm request fields and header names against the official bKash
  and SSLCommerz developer documents; if anything differs from this spec, stop and tell me.
Marking paid (one database transaction, idempotent - running it twice changes nothing more)
- payment paid + paid_at -> invoice with the next number <invoice_prefix>-<year>-<4 digits>
  from invoice_counters (row lock, no gaps, no duplicates) -> ledger "in" entry (category from
  the module) -> the on_paid handler -> outbox notification "Payment received - <invoice no>"
  -> audit row -> payment_event.
- A success for a payment that is 'abandoned' while another payment of the same application is
  already paid: status 'duplicate', no invoice, and a refund request is created automatically with
  reason "Duplicate payment - refund required" so finance sees it.
Manual payments, refunds, outstanding, ledger
- Verify / reject exactly as F09 (verify = marking paid; reject needs a reason and notifies).
- Refund request: only for a paid, not-refunded invoice of the payer; one per invoice (CONFLICT).
  Approve: refund_method and refund_ref required -> invoice refunded, payment refunded, ledger
  "out" entry in Refunds, notification, audit. Decline: reason required, notification.
  Refunding does not reopen fee_paid (staff decide what happens to the application).
- Outstanding: applications that are active or on_hold with fee_paid false, with any open payment
  status, for licensed modules. Remind writes an outbox notification and an audit row.
- Ledger exactly as F09: append-only; manual entries need date (not in the future), party and a
  whole-taka amount above 0; reverse only manual, not already reversed entries; summary and CSV
  as F09 (UTF-8 with BOM, money out negative, 2 decimals).
General
- Every amount is stored as integer poisha; taka with 2 decimals only when talking to a gateway.
- Gateway secrets, tokens and full card data never appear in logs, payment_events or responses.
- Every change writes exactly one audit row in the same transaction (gateway callbacks use the
  actor "System").

Edge cases
- The same success callback or IPN arrives twice, or both arrive: one invoice, one ledger entry.
- Validation API unreachable: the payment stays initiated; the result page shows "We are
  confirming your payment"; the IPN or the next status check finishes it.
- Amount or tran_id mismatch: status failed, payment_event "mismatch", audit row, no invoice.
- Callback for an unknown tran_id or paymentID: 404, logged, nothing changes.
- Application withdrawn while a payment is initiated: a later success is still recorded as paid
  (money was taken) and appears in Outstanding / Refunds for finance to handle.

Non-functional rules
- No new packages (httpx is already installed; use it for gateway calls with a 20-second timeout).
- Tests never call the internet: gateway calls are replaced with a fake transport.
- pytest passes, including all earlier tests.

Acceptance criteria
- b71 Migration 0007 applies; DELETE on payments, invoices, ledger_entries and refunds fails;
  UPDATE on ledger_entries and payment_events fails.
- b72 Two payment starts for the same application at the same moment: only one is created.
- b73 SSLCommerz fake success with VALID and matching amount -> paid, invoice 0001, ledger entry,
  fee_paid true, outbox row; the same callback again changes nothing.
- b74 SSLCommerz VALID with a different amount -> failed, no invoice; INVALID_TRANSACTION -> not paid.
- b75 risk_level 1 -> pending_verify; finance verify -> paid.
- b76 bKash fake execute Completed -> paid with trxID stored; an execute timeout followed by a
  status Completed -> paid; status failure -> failed.
- b77 A late success for an abandoned payment when another is paid -> duplicate, no invoice,
  automatic refund request.
- b78 Invoice numbers stay gap-free and unique when 20 payments are marked paid in parallel.
- b79 Manual payment needs manual_ref; verify makes it paid; reject needs a reason.
- b80 Refund: second request for the same invoice is CONFLICT; approve writes the ledger "out"
  entry and marks the invoice refunded.
- b81 Ledger: reverse a manual entry restores the balance; reverse an automatic entry is CONFLICT;
  amount 0, 12.5 and a future date are VALIDATION; CSV has the header and negative money out.
- b82 An amount changed in Settings fees after a payment started does not change that payment.
- b83 Section admins read their module's invoices; they get FORBIDDEN on verify, refunds and ledger.
- b84 No response, log line or payment_event contains a gateway secret or token (the test scans them).
- b85 Every successful change writes exactly one audit row.

Assumptions
- Specs B01-B06 are complete and committed.
- PUBLIC_API_URL and PUBLIC_SITE_URL are added to backend/.env by hand.
- For local sandbox testing the payer's browser can reach the backend; the SSLCommerz IPN needs a
  public address and is a backup to the browser callback.

Decisions (2026-11-01, approved by the owner)
- SSLCommerz: the official v4 docs mark more fields as mandatory than this spec lists. The start
  request also sends: cus_add1 and cus_city (from the applicant profile, else "Dhaka"),
  cus_postcode "1000", cus_country (profile, else "Bangladesh"), product_category "Service fee",
  product_profile "non-physical-goods", shipping_method "NO", num_of_item 1.
- bKash: the official developer pages could not be opened on 2026-11-01. The client is built from
  this spec (tokenized checkout v1.2.0-beta) and must be tested in the bKash sandbox before going
  live.
