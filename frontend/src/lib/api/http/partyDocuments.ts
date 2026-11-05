// Agreements and other documents of partner agents and partners (B21). Never deleted: an old
// document is archived. The server checks the real file type from the file's first bytes.

import { ApiError } from "../errors";
import type { DocumentOwnerKind, PartyDocument, PartyDocumentInput } from "../types";
import { get, post, request } from "./client";

export const MAX_PARTY_DOCUMENT_BYTES = 10 * 1024 * 1024;

const base = (kind: DocumentOwnerKind, ownerId: string) => `/admin/${kind}s/${ownerId}/documents`;

export const listPartyDocuments = (kind: DocumentOwnerKind, ownerId: string) => get<PartyDocument[]>(base(kind, ownerId));

export function uploadPartyDocument(kind: DocumentOwnerKind, ownerId: string, input: PartyDocumentInput): Promise<PartyDocument> {
  if (input.file.size < 1 || input.file.size > MAX_PARTY_DOCUMENT_BYTES) {
    return Promise.reject(new ApiError("VALIDATION", "The file must be from 1 byte to 10 MB."));
  }
  const form = new FormData();
  form.append("doc_type", input.doc_type);
  form.append("title", input.title);
  form.append("valid_until", input.valid_until ?? "");
  form.append("note", input.note);
  form.append("file", input.file, input.file.name);
  return request<PartyDocument>("POST", base(kind, ownerId), { form });
}

export const archivePartyDocument = (kind: DocumentOwnerKind, ownerId: string, docId: string) =>
  post<PartyDocument>(`${base(kind, ownerId)}/${docId}/archive`);
