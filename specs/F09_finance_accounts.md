Spec F09 - Finance: Accounts tab (payments to verify, refunds, outstanding, ledger, invoices)

Purpose
Give the Super Admin and the Finance Officer one place to control money: confirm bank / office
payments, decide refunds, see who still owes money and remind them, keep a reliable ledger of all
money in and out with a running balance, add other income and expenses, export the ledger, and
find any invoice. Screens must look and behave like the Accounts tab of the Admin panel in
reference/nextgen-learning-v2.html, including the v2 cards (Payments to verify, Refund requests,
Outstanding balances).

Scope
In scope (the "💳 Accounts" admin tab):
- Summary cards: Current balance (all time), Money in, Money out, Net - for the chosen period.
- Period switch: All time / This month.
- Three bar cards as in the reference: "Where money came from" (by category), "Received through"
  (by method), "Where money went" (by category).
- "Payments to verify (n)" card: each pending manual payment with name, what it is for, method,
  receipt ref, date, amount, Verify and Reject.
- "Refund requests (n)" card: name, description, invoice, reason, amount, Approve and Decline.
- "Outstanding balances · ৳total" card: each unpaid or waiting fee with name, what it is for,
  status (Unpaid / Waiting verification), amount and "Remind".
- "Add an entry" form: Type (Money in / Money out), Category (list changes with the type, copied
  from the reference), Date, Amount (৳), Received from / paid to, Method, Note, "Add to ledger".
- Ledger: filter All / Money in / Money out, "Export CSV", rows with Date, From / to (+ note and
  email), Category badge (+ method, ref, "auto"), Amount (+ / −) and running Balance.
- Invoices table: search by invoice number, name or email; Invoice, Customer, Module, Amount,
  Status (Paid / Refunded), confirmation email status, View (InvoiceDialog from F05) and Resend.
Out of scope: real bank or gateway reconciliation, accounting reports (trial balance, VAT
returns), salary or payroll, editing invoices, multi-currency.

Contract
- Uses: listPendingPayments, verifyPayment, rejectPayment, listRefunds, approveRefund,
  declineRefund, listOutstanding, sendPaymentReminder, listLedger, addLedgerEntry, listInvoices,
  resendNotification, getSession.
- New actions (add to the contract, mock and tests):
  ledgerSummary(period: "all" | "month") -> { balance_all_time_poisha, in_poisha, out_poisha,
  net_poisha, by_source, by_method, by_expense } (F). HTTP later: GET /admin/ledger/summary.
  reverseLedgerEntry(entryId, reason) (F) - see rules. HTTP later: POST /admin/ledger/{id}/reverse.
  exportLedgerCsv(filter) -> CSV text (F). HTTP later: GET /admin/ledger.csv.
- Ledger categories (fixed lists in types.ts, labels from the reference):
  in: course fees, student application fees, job application fees, other income, opening balance;
  out: salaries, rent & utilities, marketing, paid to universities / employers,
  software & tools, refunds, other expenses.

Functional rules
- Only super_admin and finance can open the tab or call these actions (FORBIDDEN otherwise).
- Verify payment: confirm dialog "Confirm that ৳<amount> with reference <ref> has arrived in your
  account?" -> payment paid with every side effect from F02 (invoice, ledger "in", enrolment or
  fee_paid, history, notification, audit). The payer's page then shows the course or the paid fee.
- Reject payment: reason required; payment status rejected; the payer is told by email and
  can pay again.
- Approve refund: "Refunded via" (method) and "Refund reference" required -> invoice refunded,
  payment refunded, ledger "out" entry in the refunds category, notification, audit.
  Decline: reason required; the person is told.
- Outstanding: unpaid or pending fees of active and on-hold applications and unpaid enrolments
  of licensed modules. Withdrawn and rejected applications are not counted. "Remind" sends a
  payment reminder (email and WhatsApp) and writes an audit entry.
- Add entry: amount must be a whole number above 0; date required and not in the future;
  "Received from / paid to" required. Saved as amount_poisha.
- The ledger is append-only. No entry can be edited or deleted - not even manual ones
  (this replaces the reference's Delete button). A mistake is fixed with "Reverse" on a manual
  entry: reason required; it adds an opposite entry with the same amount and the note
  "Reversal of <entry ref>: <reason>", and marks the original "reversed". Automatic entries
  (fees, refunds) cannot be reversed here; refunds are the only way to return a fee.
- Running balance is calculated in date order, oldest first; the list shows newest first.
- Money is shown as ৳ with thousands separators; negative amounts show a minus sign in red.
- CSV: columns Date, Type, Category, Party, Email, Description, Method, Reference, Amount;
  amounts in taka with 2 decimals; money out negative; UTF-8 with a byte-order mark so Excel shows
  ৳ and Bangla names correctly; file name ledger-<YYYY-MM-DD>.csv.

Edge cases
- No transactions: the reference message "No transactions yet. Fees from courses and
  applications appear here automatically."
- Verify or approve clicked twice quickly: the second call gets CONFLICT and the screen shows
  "Already done."
- A refund for a payment made in a module that is now unlicensed can still be decided (money
  rules do not depend on the licence).
- Very large amounts (crores) still format correctly and never use decimals in storage.

Non-functional rules
- No new packages; bars are plain CSS as in the reference.
- Pages import only from src/lib/api/index.ts.
- Looks exactly like the reference Accounts tab; works at 390px and in dark mode.
- npm run build, npm run lint and npm test pass.

Acceptance criteria
- t33 ledgerSummary("month") counts only this month's entries; the all-time balance counts all.
- t34 There is no update or delete function for ledger entries; reverseLedgerEntry on a manual
  entry adds an opposite entry and the balance returns to the earlier value; on an automatic
  entry it is CONFLICT.
- t35 addLedgerEntry with amount 0, a decimal amount, or a future date is VALIDATION.
- t36 exportLedgerCsv has the header row and money out as negative numbers.
- t37 An admin (role "admin") gets FORBIDDEN for every action in this spec.
- Manual checks:
  - A manual course payment from F05 appears in "Payments to verify"; Verify -> the learner's
    profile shows the course and invoice; the ledger has the "in" entry.
  - Reject another manual payment with a reason -> the payer sees they can pay again.
  - Approve the refund requested in F05 -> invoice shows Refunded; ledger shows −amount in Refunds.
  - Outstanding shows an unpaid application fee; Remind writes a notification.
  - Add an expense of ৳5,000 -> Money out and balance change; Reverse it -> balance returns.
  - Switching to "This month" changes the cards and bars.
  - Export CSV opens in Excel with ৳ and names shown correctly.
  - The Finance Officer sees only Accounts and Notifications tabs; an admin does not see Accounts.
  - All screens: no sideways scroll at 390px, correct in dark mode.
- npm run build, npm run lint and npm test pass.

Assumptions
- Specs F01-F08 are complete and committed.
- Category labels, method list and layout are copied from the reference showAccounts.
