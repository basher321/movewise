// AI CV Agent (B28): small rules of the wizard, kept apart from the screens so they can be tested.

import type { CvMissingField, CvProject } from "@/lib/api";

export const STEP_COUNT = 8;
export const FIELDS_PER_SCREEN = 6;

export function chunk<T>(items: T[], size: number = FIELDS_PER_SCREEN): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export function progress(step: number): number {
  return Math.round((Math.min(Math.max(step, 1), STEP_COUNT) / STEP_COUNT) * 100);
}

// The furthest step the person may open: they cannot skip ahead of what is filled in.
export function furthestStep(p: CvProject): number {
  if (!p.cv_type) return 1;
  if (!p.country) return 2;
  if (!p.category) return 3;
  return Math.max(4, Math.min(p.step, STEP_COUNT));
}

// Required answers still empty on this screen.
export function unanswered(fields: CvMissingField[], answers: Record<string, unknown>): CvMissingField[] {
  return fields.filter((f) => {
    if (!f.required) return false;
    const v = answers[f.key] ?? f.value;
    if (Array.isArray(v)) return v.length === 0;
    return v === undefined || v === null || String(v).trim() === "";
  });
}

// The same name the server gives the download: Firstname_Lastname_CV_Country.pdf
export function exportName(fullName: string, country: string | null, kind: "cv" | "letter", ext: "pdf" | "docx"): string {
  const ascii = (s: string) =>
    s
      .normalize("NFKD")
      .replace(/[^\x00-\x7F]/g, "")
      .replace(/[^A-Za-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  const parts = fullName.split(/\s+/).filter((p) => ascii(p));
  const picked = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  const name = picked.map(ascii).join("_") || "My";
  return `${name}_${kind === "cv" ? "CV" : "Cover_Letter"}_${ascii(country ?? "International") || "International"}.${ext}`;
}

// "Software developer, Python; SQL" -> ["Software developer", "Python", "SQL"]
export function splitList(text: string): string[] {
  return [...new Set(text.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean))];
}

export function linesOf(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.replace(/^[•\-*]\s*/, "").trim())
    .filter(Boolean);
}

export function cvTitle(p: CvProject, typeTitle: string | undefined): string {
  if (p.title) return p.title;
  return [typeTitle ?? "CV", p.country ? "for " + p.country : ""].filter(Boolean).join(" ");
}
