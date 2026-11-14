// Settings, branding pictures, the licence and the Settings test buttons (B02, B08).

import type { AiProvider, LicenceView, PublicSettings, Settings, SettingsInput, TestResult } from "../types";
import { get, post, put, request } from "./client";

export const getPublicSettings = () => get<PublicSettings>("/settings/public");
export const getSettings = () => get<Settings>("/settings");
export const saveSettings = (settings: SettingsInput) => put<Settings>("/settings", settings);

export type BrandingKind = "logo" | "hero";

export function uploadBrandingImage(kind: BrandingKind, file: File): Promise<Settings> {
  const form = new FormData();
  form.append("file", file);
  return request<Settings>("PUT", "/settings/" + kind, { form });
}

export const clearBrandingImage = (kind: BrandingKind) => post<Settings>("/settings/" + kind + "/clear");

// Everyone: which modules are on. The super admin also gets the masked key (getFullLicence).
export const getLicence = () => get<LicenceView>("/licence");
export const getFullLicence = () => get<LicenceView>("/licence/full");
export const applyLicenceKey = (key: string) => put<LicenceView>("/licence", { key });

// The webmail link for the admin panel's Webmail button (super admin and admins).
export const getWebmailUrl = async () => (await get<{ url: string }>("/admin/webmail")).url;

export const sendTestEmail = (to: string) => post<TestResult>("/admin/settings/test-email", { to });
export const sendTestWhatsapp = (to: string) => post<TestResult>("/admin/settings/test-whatsapp", { to });
// B17: one short test prompt with the saved key and model of this provider.
export const testAiProvider = (provider: AiProvider) => post<TestResult>("/admin/settings/test-ai", { provider });
