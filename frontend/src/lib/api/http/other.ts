// Enrolments and certificates (B09), notifications (B08), enquiries (B09), the team (B03) and
// the audit list (B09).

import type {
  AdminRole,
  AdminUser,
  AuditPage,
  CertificateCheck,
  EnrolResult,
  Enrolment,
  EnrolmentStatus,
  Enquiry,
  EnquiryChanges,
  EnquiryForm,
  EnquiryStatus,
  Module,
  Notification,
  NotificationFilter,
  Page,
  PayInput,
  StaffMember,
} from "../types";
import { get, patch, post, put } from "./client";

// ---------- courses ----------

export const enrol = (courseSlug: string, input: PayInput) => post<EnrolResult>("/me/course/enrolments", { course_slug: courseSlug, ...input });
export const myEnrolments = () => get<Enrolment[]>("/me/course/enrolments");
export const listEnrolments = (q = "", status: EnrolmentStatus | "" = "", page = 1) =>
  get<Page<Enrolment>>("/admin/enrolments", { q, status, page });
export const approveCertificate = (id: string) => post<Enrolment>(`/admin/enrolments/${id}/approve-certificate`);
export const verifyCertificate = (certificateId: string) =>
  get<CertificateCheck>("/certificates/" + encodeURIComponent(certificateId.trim()));

// ---------- notifications ----------

export const listNotifications = (filter: NotificationFilter = {}) =>
  get<Page<Notification>>("/admin/notifications", { channel: filter.channel, status: filter.status, q: filter.q, page: filter.page ?? 1 });
export const resendNotification = (id: string) => post<Notification>(`/admin/notifications/${id}/resend`);

// ---------- enquiries ----------

export async function submitEnquiry(form: EnquiryForm): Promise<void> {
  await post("/enquiries", {
    name: form.name,
    contact: form.contact,
    interest: form.interest,
    preferred_date: form.preferred_date || null,
    message: form.message,
    website: form.website ?? "",
  });
}

export const listEnquiries = (status: EnquiryStatus | "" = "", q = "", page = 1) =>
  get<Page<Enquiry>>("/admin/enquiries", { status, q, page });
export const addEnquiry = (form: Pick<EnquiryForm, "name" | "contact" | "interest" | "message">) =>
  post<Enquiry>("/admin/enquiries", form);
export const updateEnquiry = (id: string, changes: EnquiryChanges) => patch<Enquiry>("/admin/enquiries/" + id, changes);
export const addEnquiryNote = (id: string, text: string) => post<Enquiry>(`/admin/enquiries/${id}/notes`, { text });

// ---------- team (super admin) ----------

export const listAdmins = () => get<AdminUser[]>("/admin/team");
export const approveAdmin = (id: string) => post<AdminUser>(`/admin/team/${id}/approve`);
export const deactivateAdmin = (id: string) => post<AdminUser>(`/admin/team/${id}/deactivate`);
// B15: a Super Admin gives another staff member a temporary password (shown once).
export const resetStaffPassword = (id: string) => post<{ temporary_password: string }>(`/admin/team/${id}/reset-password`);
export const reactivateAdmin = (id: string) => post<AdminUser>(`/admin/team/${id}/reactivate`);
export const setRole = (id: string, role: AdminRole) => put<AdminUser>(`/admin/team/${id}/role`, { role });
export const setSections = (id: string, sections: Module[]) => put<AdminUser>(`/admin/team/${id}/sections`, { sections });

// Who can be chosen in "Assigned to": approved, active and not finance (any admin may read it).
export async function listAssignableAdmins(module?: Module): Promise<StaffMember[]> {
  const staff = await get<{ id: string; name: string; role: AdminRole; sections: Module[] }[]>("/admin/staff");
  return staff
    .filter((a) => a.role === "super_admin" || !module || a.sections.includes(module))
    .map((a) => ({ id: a.id, name: a.name }));
}

// ---------- audit (super admin) ----------

export const AUDIT_ROWS_PER_PAGE = 50;
export const listAudit = (q = "", page = 1) => get<AuditPage>("/admin/audit", { q, page });
