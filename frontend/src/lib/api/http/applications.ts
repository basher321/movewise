// Applications (B05), documents (B06) and paying the application fee (B07).

import { ApiError } from "../errors";
import type {
  AppDocument,
  AppModule,
  AppStatus,
  Answers,
  ApplicantRow,
  CaseChanges,
  CaseFilters,
  CaseRow,
  DocFilter,
  DocumentRow,
  Module,
  MyApplication,
  MyApplicationSummary,
  Page,
  PayInput,
  PayStart,
} from "../types";
import { get, patch, post, request } from "./client";

// ---------- the applicant's own applications ----------

export const startApplication = (module: AppModule, itemSlug: string, answers: Answers) =>
  post<MyApplication>(`/me/${module}/applications`, { item_slug: itemSlug, answers });

export const myApplications = (module: AppModule) => get<MyApplicationSummary[]>(`/me/${module}/applications`);

export const getMyApplication = (module: AppModule, id: string) => get<MyApplication>(`/me/${module}/applications/${id}`);

export const withdrawApplication = (module: AppModule, id: string) =>
  post<MyApplication>(`/me/${module}/applications/${id}/withdraw`);

export const payApplicationFee = (module: AppModule, id: string, input: PayInput) =>
  post<PayStart>(`/me/${module}/applications/${id}/pay`, input);

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;

// The file goes as multipart. The server checks the real type from the file's first bytes.
export function uploadDocument(module: AppModule, appId: string, type: string, file: File): Promise<AppDocument> {
  if (file.size > MAX_UPLOAD_BYTES) {
    return Promise.reject(new ApiError("VALIDATION", "The file must be from 1 byte to 2 MB."));
  }
  const form = new FormData();
  form.append("type", type);
  form.append("file", file, file.name);
  return request<AppDocument>("POST", `/me/${module}/applications/${appId}/documents`, { form });
}

// ---------- staff: case handling (section of the module) ----------

export const listApplications = (module: AppModule, filters: CaseFilters = {}) =>
  get<Page<CaseRow>>("/admin/applications", {
    module,
    q: filters.q,
    status: filters.status,
    assigned: filters.assigned,
    page: filters.page ?? 1,
  });

export const getApplication = (id: string) => get<CaseRow>("/admin/applications/" + id);

export const changeStage = (id: string, stage: number, note: string, notify: boolean) =>
  post<CaseRow>(`/admin/applications/${id}/stage`, { stage, note, notify });

export const changeStatus = (id: string, status: AppStatus, reason: string) =>
  post<CaseRow>(`/admin/applications/${id}/status`, { status, reason });

export const updateCase = (id: string, changes: CaseChanges) => patch<CaseRow>("/admin/applications/" + id, changes);

export const addInternalNote = (id: string, note: string) => post<CaseRow>(`/admin/applications/${id}/notes`, { note });

export const sendCaseEmail = (id: string, to: "applicant" | "provider", subject: string, body: string) =>
  post<CaseRow>(`/admin/applications/${id}/email`, { to, subject, body });

export const listApplicantAccounts = (module: Module) => get<ApplicantRow[]>("/admin/accounts", { module });

// A person who forgot their password: staff set a temporary one and tell it to them (shown once).
export const resetApplicantPassword = (accountId: string) =>
  post<{ temporary_password: string; username: string }>(`/admin/accounts/${accountId}/reset-password`);

// ---------- staff: documents ----------

export const listDocuments = (filter: DocFilter = "pending", q = "", page = 1) =>
  get<Page<DocumentRow>>("/admin/documents", { filter, q, page });

export const verifyDocument = (id: string, expiry?: string) =>
  post<AppDocument>(`/admin/documents/${id}/verify`, { expiry: expiry || null });

export const rejectDocument = (id: string, reason: string) => post<AppDocument>(`/admin/documents/${id}/reject`, { reason });
