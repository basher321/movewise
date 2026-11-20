// AI CV Agent (B28): projects, uploads, reading, writing, review and export.
// Every call goes to /api/me/{module}/cv/... for the signed-in applicant of that service.

import type {
  CvData,
  CvDocKind,
  CvFile,
  CvIssue,
  CvOptions,
  CvProject,
  CvProjectChanges,
  CvSection,
  CvSectionAction,
  CvState,
  CvTemplate,
  CvType,
} from "../cvTypes";
import { ApiError, NETWORK_MESSAGE, type ErrorCode } from "../errors";
import type { Module } from "../types";
import { apiUrl, get, patch, post, put } from "./client";

const base = (module: Module, id: string) => `/me/${module}/cv/projects/${encodeURIComponent(id)}`;

export const getCvOptions = () => get<CvOptions>("/cv/options");
export const listCvs = (module: Module) => get<{ items: CvProject[] }>(`/me/${module}/cv/projects`);
export const createCv = (module: Module, cvType: CvType | null, coverLetter: boolean) =>
  post<CvProject>(`/me/${module}/cv/projects`, { cv_type: cvType, cover_letter: coverLetter });
export const getCv = (module: Module, id: string) => get<CvProject>(base(module, id));
export const saveCv = (module: Module, id: string, changes: CvProjectChanges) => patch<CvProject>(base(module, id), changes);
export const duplicateCv = (module: Module, id: string) => post<CvProject>(base(module, id) + "/duplicate");
export const deleteCv = (module: Module, id: string) => post<{ id: string; status: string }>(base(module, id) + "/delete");
export const giveCvConsent = (module: Module, id: string) => post<CvProject>(base(module, id) + "/consent", { agree: true });
export const removeCvFile = (module: Module, id: string, fileId: string) =>
  post<CvProject>(base(module, id) + `/files/${encodeURIComponent(fileId)}/remove`);

export const MAX_CV_FILE_BYTES = 10 * 1024 * 1024;

// Upload with progress (fetch cannot report upload progress). The server checks the real type.
export function uploadCvFile(
  module: Module,
  id: string,
  file: File,
  kind: CvDocKind,
  onProgress: (fraction: number) => void,
): Promise<CvProject> {
  if (file.size < 1 || file.size > MAX_CV_FILE_BYTES) {
    return Promise.reject(new ApiError("VALIDATION", "Each file must be from 1 byte to 10 MB."));
  }
  const form = new FormData();
  form.append("doc_kind", kind);
  form.append("file", file, file.name);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(base(module, id) + "/files"));
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError("NETWORK", NETWORK_MESSAGE));
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // not JSON (for example a proxy error page)
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as CvProject);
      const d = (data ?? {}) as { code?: ErrorCode; message?: string };
      const code: ErrorCode = d.code ?? (xhr.status === 413 ? "VALIDATION" : "INTERNAL");
      const message = d.message ?? (xhr.status === 413 ? "The file must be 10 MB or smaller." : "The file could not be uploaded.");
      reject(new ApiError(code, message, undefined, xhr.status));
    };
    xhr.send(form);
  });
}

export const getCvState = (module: Module, id: string) => get<CvState>(base(module, id) + "/state");
export const readCvFile = (module: Module, id: string, fileId: string) =>
  post<CvFile>(base(module, id) + `/files/${encodeURIComponent(fileId)}/extract`);
export const mergeCvFiles = (module: Module, id: string) => post<CvState>(base(module, id) + "/merge");
export const answerCv = (module: Module, id: string, answers: Record<string, unknown>) =>
  post<CvState>(base(module, id) + "/answers", { answers });
export const saveCvData = (module: Module, id: string, cv: CvData, reason: "edited" | "removed" = "edited") =>
  put<CvState>(base(module, id) + "/data", { cv, reason });
export const undoCv = (module: Module, id: string) => post<CvState>(base(module, id) + "/undo");
export const generateCv = (module: Module, id: string) => post<CvState>(base(module, id) + "/generate");
export const cvSectionAction = (module: Module, id: string, section: CvSection, action: CvSectionAction, itemId?: string) =>
  post<CvState>(base(module, id) + "/section", { section, action, item_id: itemId ?? null });
export const cvPages = (module: Module, id: string, template?: CvTemplate) =>
  get<{ pages: number }>(base(module, id) + "/pages", { template });
export const reviewCv = (module: Module, id: string, spelling: boolean) =>
  post<{ issues: CvIssue[]; blocking: number }>(base(module, id) + "/review", { spelling });
export const approveCv = (module: Module, id: string) => post<CvState>(base(module, id) + "/approve");
export const makeCoverLetter = (module: Module, id: string) => post<CvState>(base(module, id) + "/letter");
export const saveCoverLetter = (module: Module, id: string, body: string) => put<CvState>(base(module, id) + "/letter", { body });

// Links the browser opens directly (the sign-in cookie goes with them).
export const cvPreviewUrl = (module: Module, id: string, page: number, version: number, template?: CvTemplate, dpi?: number) =>
  apiUrl(base(module, id) + "/preview", { page, template, dpi, v: version });
export const cvExportUrl = (module: Module, id: string, format: "pdf" | "docx", doc: "cv" | "letter" = "cv") =>
  apiUrl(base(module, id) + "/export", { format, doc });
