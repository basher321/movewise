Spec B26 - EPS (Easy Payment System) payment gateway

Purpose
Add EPS as a separate online payment method, next to SSLCommerz, bKash and manual payment.
The payer chooses "EPS" at checkout, pays on the EPS page (cards, mobile wallets and internet
banking), comes back, and our server confirms the payment with EPS before anything is marked
paid. SSLCommerz and bKash stay exactly as they are (B07). EPS uses the same payment service,
invoices, ledger, refunds and audit as B07, so application fees (B07) and course enrolments
(B09) can both be paid with EPS.

Source documents (outside the repo, never committed):
- "EPS Merchant API Integration Guide" V5 (live) and V4 (sandbox), January 2024.
- EPS sandbox Postman collection (3 requests: GetToken, Initialize, CheckMerchantTransactionStatus).
- EPS footer and checkout logo images (EPS-PGW_Footer_Merchant_Website).
The merchant credentials (.docx files) are typed into admin Settings by the owner; they are never
read, copied or stored in files by the build.

Scope
In scope:
- db/migrations/0024_eps_gateway.sql:
  - settings: eps_enabled boolean NOT NULL DEFAULT false, eps_sandbox boolean NOT NULL DEFAULT true.
  - settings_payment_method_on: replace the CHECK so it also accepts eps_enabled
    (sslcommerz_enabled OR bkash_enabled OR nagad_enabled OR manual_enabled OR eps_enabled).
  - EPS secrets (eps.store_id, eps.username, eps.password, eps.hash_key) are stored in
    app_secrets (0008), whose name rule already allows them; settings_secrets is not changed.
  - payments.method CHECK: ('sslcommerz', 'bkash', 'manual', 'eps').
  - Replacing a CHECK needs ALTER TABLE ... DROP CONSTRAINT ... then ADD CONSTRAINT (two
    constraints; approved, see Decisions 1).
  - No new tables. No data rows.
- backend/app/payments/eps.py: EPS client (hash, token, initialize, status) using the shared
  httpx client, timeout and scrub() from gateway.py.
- backend/app/payments/gateway.py: Gateway adds "eps"; SECRET_FIELDS["eps"] = ("store_id",
  "username", "password", "hash_key"); gateway_config also reads app_secrets; "hash_key" and "x-hash" added to the secret key
  parts that scrub() removes.
- backend/app/payments/service.py: confirm_eps(conn, payment) and eps_status(...) in the same style
  as confirm_bkash / bkash_status; refresh_initiated also asks EPS for EPS payments.
- backend/app/routers/pay.py: "eps" in METHODS, the start branch, the return route below.
- backend/app/routers/settings.py: EPS in GATEWAY_LABELS, the secret names, and the settings map
  "eps_enabled" -> gateways.eps.enabled, "eps_sandbox" -> gateways.eps.sandbox.
- Frontend:
  - lib/api types: PAYMENT_METHODS = ["sslcommerz", "bkash", "eps", "manual"]; settings
    gateways.eps {enabled, sandbox}; mock and http layers updated the same way.
  - components/payment/methods.ts: METHOD_NAMES.eps = "EPS (cards, mobile wallets, banking)".
  - Admin Settings > Payment gateways: an EPS block like the bKash block (enabled switch,
    sandbox switch, four secret fields shown as "Saved" / "Not set", never the value).
  - Footer: when EPS is enabled, show the EPS "Pay with" strip from the EPS kit under the footer
    brand, light or dark image to match the theme, mobile image under 640px wide. Images copied to
    frontend/public/payments/eps/ (renamed footer-desktop-light.png, footer-desktop-dark.png,
    footer-mobile-light.png, footer-mobile-dark.png, checkout.png).
  - Checkout: under the method choice, when EPS is chosen, show checkout.png (max 360px wide,
    alt text "Pay with EPS").
- Tests (pytest and the frontend unit tests) as listed in Acceptance criteria.
Out of scope: refunds through the EPS API (refunds stay manual as in B07), Android / iOS
transaction types, the ProductList field, any change to SSLCommerz or bKash behaviour, new pages,
new packages.

Contract (all under /api)
Applicant (unchanged endpoints, one more method value):
- POST /me/{module}/applications/{id}/pay {method: "eps", phone}
  -> {payment_id, redirect_url} (redirect_url is the EPS RedirectURL)
- The B09 enrolment pay endpoint accepts method "eps" the same way.
- GET /me/payments/{id}: unchanged; for an initiated EPS payment it asks EPS for the status first
  (like bKash today).
Gateway return (public; exempt from the B03 Origin check; never trusted on its own):
- GET /pay/eps/return/{tran_id}/{outcome}   outcome in success | fail | cancel
  Whatever query string EPS adds is stored (scrubbed) in payment_events but never trusted.
  Ends with a 303 redirect to PUBLIC_SITE_URL/payment/result?id=<payment_id>.
  Unknown tran_id -> 404 NOT_FOUND, nothing changes. outcome not in the list -> 404 NOT_FOUND.
Settings (super admin, existing endpoints):
- PATCH settings accepts gateways.eps.enabled and gateways.eps.sandbox.
- PUT /settings accepts gateways.eps {enabled, sandbox, store_id, username, password,
  hash_key}; a client that leaves out gateways.eps keeps the saved EPS settings. Public settings
  expose gateways.eps {enabled, sandbox} like the other gateways, never the secrets.
Error codes: the existing B07 codes only (VALIDATION, CONFLICT, NOT_FOUND, FORBIDDEN,
MODULE_NOT_LICENSED; a gateway that does not answer gives INTERNAL 500 "The payment gateway is
not answering..." exactly as B07 does). No new codes.

Functional rules
Base address, chosen by eps_sandbox:
- sandbox https://sandboxpgapi.eps.com.bd, live https://pgapi.eps.com.bd.
x-hash (every call):
- HMAC-SHA512 with key = hash_key encoded as UTF-8, message = the value named below encoded as
  UTF-8, result as standard Base64. Sent in the "x-hash" header.
1. Token: POST {base}/v1/Auth/GetToken, body {"userName", "password"}, x-hash of userName.
   Response {token, expireDate, errorMessage, errorCode}. A token is kept in memory (per process,
   per sandbox/live) until 60 seconds before expireDate; then a new one is fetched. errorCode not
   null or no token -> GatewayError.
2. Start: POST {base}/v1/EPSEngine/InitializeEPS with headers x-hash (of merchantTransactionId)
   and "Authorization: Bearer <token>". Body:
   - storeId: from the secrets (merchantId is not sent - see Decisions 3a).
   - CustomerOrderId: the payment tran_id. merchantTransactionId: the payment tran_id.
   - transactionTypeId 1 (Web), financialEntityId 0, transitionStatusId 0, version "1".
   - totalAmount: taka as a number with 2 decimals (amount_poisha / 100).
   - ipAddress: the payer's IP from the request (first X-Forwarded-For entry, else client host).
   - successUrl / failUrl / cancelUrl:
     {PUBLIC_API_URL}/api/pay/eps/return/{tran_id}/success | /fail | /cancel.
   - customerName, customerEmail, customerPhone (the phone given at checkout),
     CustomerAddress, CustomerCity, CustomerState, CustomerPostcode, CustomerCountry: from the
     applicant profile; empty values use the B07 SSLCommerz defaults (address and city "Dhaka",
     state "Dhaka", postcode "1000", country "BD"). Email empty -> the company email from Settings.
   - totalAmount is sent as text with 2 decimals ("1500.00"); the sandbox accepts it (no float).
   - ProductName = purpose, ProductProfile "non-physical-goods", ProductCategory "Service fee",
     NoOfItem "1", ShippingMethod "NO". ValueA = payment id. Shipment fields not sent.
   - Response {TransactionId, RedirectURL, ErrorMessage, ErrorCode}. Store TransactionId as
     gateway_session. No RedirectURL or ErrorCode not null -> GatewayError: the request ends
     with INTERNAL 500 as for the other gateways, and nothing is kept.
3. Status: GET {base}/v1/EPSEngine/CheckMerchantTransactionStatus?merchantTransactionId=<tran_id>
   with x-hash of tran_id and the bearer token.
   - Status "Success" AND MerchantTransactionId equal to tran_id AND TotalAmount equal to the stored
     amount (compared in poisha, parsed from the decimal text without float) -> mark paid through
     the B07 "Marking paid" path. EpsTransactionId (if present) is stored as gateway_ref;
     FinancialEntity is kept in the payment_event detail.
   - Status "Success" with a different amount or id -> record_mismatch (B07 rule: failed, no
     invoice).
   - Any other status ends the payment only as set out in Decisions 3e.
   - Any other status, an unclear answer or a timeout -> the payment stays initiated (result page
     shows "We are confirming your payment"; the next GET /me/payments/{id} checks again).
Return route:
- Find the payment by tran_id with method 'eps' (lock it). Always run the status check (3),
  whatever the outcome in the URL says. If the status check is unclear and outcome is fail or
  cancel, mark the payment failed / cancelled. A success outcome never marks anything paid by itself.
Starting a payment, duplicates, refunds, invoices, ledger, outstanding: exactly as B07.
tran_id for EPS: EPS asks for a unique string of at least 10 digits. EPS payments use a tran_id of
16 random digits (unique in payments.tran_id, same retry loop as new_tran_id). Other methods keep
the "MW-" format.
Settings:
- EPS can be enabled only when store_id, username, password and hash_key are saved (VALIDATION
  otherwise), the same rule the other gateways follow. merchant_id is not used (Decisions 3a).
- Turning sandbox off is allowed at any time by the super admin; the switch is audited.
General
- Gateway secrets, the token, the hash key and x-hash values never appear in logs,
  payment_events, audit rows or responses.
- Every change writes exactly one audit row in the same transaction (return route actor "System").
- Money stays integer poisha; taka with 2 decimals only in the EPS request.

Edge cases
- The payer opens the success URL twice, or reloads it: one invoice, one ledger entry.
- The payer closes the EPS page without returning: the payment stays initiated; the next status
  check (result page, a new pay attempt for the same item, or finance looking at it) settles it.
- EPS says Success for a payment that was abandoned while another payment of the same item is
  paid: duplicate + automatic refund request (B07 rule).
- Token expired mid-call (401 from EPS): fetch a new token once and retry once; still 401 ->
  GatewayError.
- Hash key saved with spaces at either end: trimmed when saved.

Non-functional rules
- No new packages (hmac, hashlib, base64 from the standard library; httpx already installed).
- Tests never call the internet: the fake transport answers for sandboxpgapi.eps.com.bd.
- Every page that changes still works at 390px width and in light and dark mode.
- pytest and the frontend tests pass, including all earlier tests.

Acceptance criteria
- b261 Migration 0024 applies on movewise_test; a payment with method 'eps' can be inserted;
  'paypal' is rejected; settings with only eps_enabled true passes the method-on check.
- b262 The x-hash function gives the known Base64 result for a fixed test key and message
  (test vector computed in the test with hmac/hashlib, not copied from the EPS PDF).
- b263 Start with fake EPS: token fetched once for two payments in a row; InitializeEPS gets the
  right headers, tran_id, amount "1500.00" for 150000 poisha, the three return URLs; redirect_url
  is the fake RedirectURL.
- b264 Return success + status Success with matching amount -> paid, invoice, ledger entry, outbox
  row; the same return again changes nothing.
- b265 Status Success with a different amount -> failed, no invoice, payment_event "mismatch".
- b266 Return fail with status unclear -> failed; return success with status unclear -> still
  initiated, result page status "initiated".
- b267 Unknown tran_id on the return route -> 404, nothing written.
- b268 401 on status -> one new token and one retry.
- b269 EPS cannot be enabled before the four required secrets are saved; public settings show
  gateways.eps {enabled, sandbox} and no secret.
- b270 No response, log line, payment_event or audit row contains any EPS secret, token or
  x-hash (the test scans them, like b84).
- b271 Frontend: EPS appears at checkout only when enabled; the footer strip shows only when EPS
  is enabled and switches image with the theme; Settings shows "Saved" / "Not set" for the four
  secrets and never a value.
- b272 SSLCommerz and bKash tests (b73-b77) still pass unchanged.

Assumptions
- B07 and B09 are complete; PUBLIC_API_URL and PUBLIC_SITE_URL are set on the live server.
- The sandbox and live APIs are the same apart from the base address (V4 and V5 guides match).
- EPS sends the payer back with a GET to the success / fail / cancel URL.

Decisions (2026-11-19, approved by the owner)
1. Migration 0024 may use ALTER TABLE ... DROP CONSTRAINT for the three CHECK constraints
   (settings_payment_method_on, the settings_secrets name check, the payments method check) and
   re-add them with EPS included. No table, column or row is dropped. Approved.
2. Footer: the EPS strip is shown on every public page while EPS is enabled.
3. Sandbox findings (EPS sandbox called directly on 2026-11-19 with the EPS demo account). These
   override the Functional rules above where they differ:
   a. merchantId: sending it makes InitializeEPS fail every time (ErrorCode 500 "An error
      occured while initalizing the transaction."). It is NOT sent and not stored in Settings.
   b. transactionTypeId 1 works.
   c. InitializeEPS sometimes answers ErrorCode 500 for a valid request. On ErrorCode 500 the
      start is retried once after 1 second with a NEW tran_id (the payment row's tran_id is
      replaced before the retry; nothing was created at EPS). A second failure -> INTERNAL 500 (B07 message).
   d. Errors come back as HTTP 200 with ErrorCode / ErrorMessage set (for example 400
      "Transaction Not Found.", 400 "Invalid hash provided."). An expired or wrong token gives
      HTTP 302. So: ErrorCode not null -> error; HTTP 302 or 401 -> fetch a new token, retry once.
   e. A started but unpaid transaction already reports Status "Cancel" with TotalAmount and an
      EPSTransactionId. So "Cancel" (and any non-"Success" status) does NOT end a payment on a
      plain status check. A payment is ended only:
      - by the return route with outcome fail / cancel and a status that is not "Success", or
      - by a status check when the payment is older than 30 minutes and the status is not
        "Success" (failed for "Fail"/"Failed", cancelled for anything else).
      "Success" with matching id and amount marks paid at any time.
   f. The token's expireDate has no time zone and is Asia/Dhaka time. It is read as Asia/Dhaka.
   g. Still to confirm by paying in the sandbox: the exact Status text of a paid and of a failed
      payment, and the query string EPS adds to the return URLs.
