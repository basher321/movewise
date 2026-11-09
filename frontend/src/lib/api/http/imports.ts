// Excel upload of listings (B23). The server checks the licence, the section and every row; a
// locked module comes back here as MODULE_NOT_LICENSED (403).

import { ApiError } from "../errors";
import type { ImportKind, ImportReport } from "../types";
import { apiUrl, request } from "./client";

export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;

function send(kind: ImportKind, step: "preview" | "commit", file: File): Promise<ImportReport> {
  if (file.size < 1 || file.size > MAX_IMPORT_BYTES) {
    return Promise.reject(new ApiError("VALIDATION", "The file must be from 1 byte to 5 MB."));
  }
  const form = new FormData();
  form.append("file", file, file.name);
  return request<ImportReport>("POST", `/admin/import/${kind}/${step}`, { form });
}

export const previewImport = (kind: ImportKind, file: File) => send(kind, "preview", file);

export const commitImport = (kind: ImportKind, file: File) => send(kind, "commit", file);

// The browser saves the template itself, as with the other file links.
export function downloadImportTemplate(kind: ImportKind): void {
  const link = document.createElement("a");
  link.href = apiUrl(`/admin/import/${kind}/template`);
  link.download = `${kind}-template.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
