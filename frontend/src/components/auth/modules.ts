import type { Module, PublicSettings } from "@/lib/api";
import type { Accent } from "../PageShell";

// How each module is shown to applicants (SEC in the reference).
export const MODULE_UI: Record<Module, { name: string; short: string; icon: string; prefix: string; accent: Accent | "brand" }> = {
  course: { name: "Courses", short: "Courses", icon: "📚", prefix: "CRS", accent: "brand" },
  study: { name: "Student Consultancy", short: "Student", icon: "🎓", prefix: "STU", accent: "#0EA5A4" },
  job: { name: "Job Processing", short: "Jobs", icon: "🛂", prefix: "JOB", accent: "#D97706" },
  visa: { name: "Immigration Processing", short: "Immigration", icon: "🌍", prefix: "VIS", accent: "#E11D48" },
};

export function accentColour(module: Module, settings: PublicSettings | null): string {
  const accent = MODULE_UI[module].accent;
  return accent === "brand" ? (settings?.brand_color ?? "#4F46E5") : accent;
}

// The module of the page being shown (pageSec() in the reference).
export function pageModule(pathname: string): Module | null {
  if (pathname.startsWith("/courses")) return "course";
  if (pathname.startsWith("/consultancy")) return "study";
  if (pathname.startsWith("/jobs")) return "job";
  if (pathname.startsWith("/immigration")) return "visa";
  const m = /^\/profile\/(course|study|job|visa)\b/.exec(pathname);
  return m ? (m[1] as Module) : null;
}
