// B2B partners and their logos (B18). Each partner belongs to one module and is shown only there.
// Partners are switched off, never deleted.

import type { Module, Partner, PartnerFilters, PartnerInput, PublicPartner } from "../types";
import { get, post, put, request } from "./client";

export const listPublicPartners = (module: Module) => get<PublicPartner[]>("/partners", { module });
export const listPartners = (filters: PartnerFilters = {}) =>
  get<Partner[]>("/admin/partners", { module: filters.module, q: filters.q, active: filters.active });
export const createPartner = (input: PartnerInput) => post<Partner>("/admin/partners", input);
export const updatePartner = (id: string, input: PartnerInput) => put<Partner>("/admin/partners/" + id, input);

export function uploadPartnerLogo(id: string, file: File): Promise<Partner> {
  const form = new FormData();
  form.append("file", file);
  return request<Partner>("PUT", `/admin/partners/${id}/logo`, { form });
}

export const clearPartnerLogo = (id: string) => post<Partner>(`/admin/partners/${id}/logo/clear`);
