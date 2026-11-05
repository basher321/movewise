// Certificates, completion letters and client messages (spec B20).

import type { CertificateView, Channel, ClientMessage, GroupFilters, GroupPreview, Module } from "../types";
import { apiUrl, get, post } from "./client";

// ---------- course certificates (staff of Training) ----------

export const getEnrolmentCertificate = (enrolmentId: string) => get<CertificateView>(`/admin/enrolments/${enrolmentId}/certificate`);
export const enrolmentCertificatePdfUrl = (enrolmentId: string, download = false) =>
  apiUrl(`/admin/enrolments/${enrolmentId}/certificate.pdf`, { download: download || undefined });
export const sendEnrolmentCertificate = (enrolmentId: string, channels: Channel[]) =>
  post<{ queued: number }>(`/admin/enrolments/${enrolmentId}/certificate/send`, { channels });

// ---------- completion letters (staff of the section) ----------

export const getCaseLetter = (appId: string) => get<CertificateView | null>(`/admin/applications/${appId}/letter`);
export const caseLetterPdfUrl = (appId: string, download = false) =>
  apiUrl(`/admin/applications/${appId}/letter.pdf`, { download: download || undefined });
export const issueCaseLetter = (appId: string) => post<CertificateView>(`/admin/applications/${appId}/letter`);
export const sendCaseLetter = (appId: string, channels: Channel[]) =>
  post<{ queued: number }>(`/admin/applications/${appId}/letter/send`, { channels });

// ---------- the applicant's own ----------

export const myCertificatePdfUrl = (enrolmentId: string, download = false) =>
  apiUrl(`/me/course/enrolments/${enrolmentId}/certificate.pdf`, { download: download || undefined });
export const myLetterPdfUrl = (module: Module, appId: string, download = false) =>
  apiUrl(`/me/${module}/applications/${appId}/letter.pdf`, { download: download || undefined });

// ---------- messages to clients ----------

export const sendClientMessage = (accountId: string, message: ClientMessage) =>
  post<{ queued: number }>("/admin/messages", { account_id: accountId, ...message });
export const previewGroupMessage = (module: Module, filters: GroupFilters) =>
  post<GroupPreview>("/admin/messages/bulk/preview", { module, filters });
export const sendGroupMessage = (module: Module, filters: GroupFilters, message: ClientMessage, expectedRecipients: number) =>
  post<{ batch_id: string; queued: number }>("/admin/messages/bulk", {
    module,
    filters,
    ...message,
    expected_recipients: expectedRecipients,
  });
