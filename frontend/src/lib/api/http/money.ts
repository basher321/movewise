// Payments, invoices, refunds, outstanding fees and the ledger (B07).

import type {
  Invoice,
  LedgerDirection,
  LedgerEntry,
  LedgerPeriod,
  LedgerSummary,
  Module,
  NewLedgerEntry,
  OutstandingItem,
  Page,
  PaymentResult,
  PendingPayment,
  Refund,
} from "../types";
import { apiUrl, get, post } from "./client";

// ---------- the payer ----------

export const getMyPayment = (id: string) => get<PaymentResult>("/me/payments/" + encodeURIComponent(id));
export const myInvoices = (module: Module) => get<Invoice[]>(`/me/${module}/invoices`);
export const getMyInvoice = (module: Module, no: string) => get<Invoice>(`/me/${module}/invoices/${encodeURIComponent(no)}`);
export const requestRefund = (module: Module, invoiceNo: string, reason: string) =>
  post<Refund>(`/me/${module}/refunds`, { invoice_no: invoiceNo, reason });

// ---------- finance (super admin or finance) ----------

export const listPendingPayments = () => get<PendingPayment[]>("/admin/payments/pending");
export const verifyPayment = (id: string) => post<{ id: string; status: string }>(`/admin/payments/${id}/verify`);
export const rejectPayment = (id: string, reason: string) => post<{ id: string; status: string }>(`/admin/payments/${id}/reject`, { reason });

export const listRefunds = () => get<Refund[]>("/admin/refunds");
export const approveRefund = (id: string, refundMethod: string, refundRef: string) =>
  post<Refund>(`/admin/refunds/${id}/approve`, { refund_method: refundMethod, refund_ref: refundRef });
export const declineRefund = (id: string, reason: string) => post<Refund>(`/admin/refunds/${id}/decline`, { reason });

export const listOutstanding = () => get<{ items: OutstandingItem[]; total_poisha: number }>("/admin/outstanding");
export const sendPaymentReminder = (applicantId: string) => post<{ sent: boolean }>(`/admin/outstanding/${applicantId}/remind`);

export const listLedger = (direction: LedgerDirection | "all" = "all", period: LedgerPeriod = "all", page = 1) =>
  get<Page<LedgerEntry>>("/admin/ledger", { direction, period, page });
export const ledgerSummary = (period: LedgerPeriod = "all") => get<LedgerSummary>("/admin/ledger/summary", { period });
export const addLedgerEntry = (entry: NewLedgerEntry) => post<{ id: string; ref: string }>("/admin/ledger", entry);
export const reverseLedgerEntry = (id: string, reason: string) => post<{ id: string; ref: string }>(`/admin/ledger/${id}/reverse`, { reason });
export const ledgerCsvUrl = (direction: LedgerDirection | "all" = "all", period: LedgerPeriod = "all") =>
  apiUrl("/admin/ledger.csv", { direction, period });

// Finance and super admin see every invoice; a section admin sees their module's.
export const listInvoices = (q = "", module: Module | "" = "", page = 1) => get<Page<Invoice>>("/admin/invoices", { q, module, page });
export const getInvoice = (no: string) => get<Invoice>("/admin/invoices/" + encodeURIComponent(no));
