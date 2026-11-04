"use client";

import type { CSSProperties, ReactNode } from "react";
import { useSettings } from "./SettingsProvider";

// Section accent colours from CLAUDE.md. "brand" uses the brand colour from Settings (Home, Courses, Profile).
export type Accent = "#4F46E5" | "#0EA5A4" | "#D97706" | "#E11D48" | "#7C3AED" | "#0891B2";

type PageShellProps = {
  accent: Accent | "brand";
  children: ReactNode;
};

export default function PageShell({ accent, children }: PageShellProps) {
  const { settings } = useSettings();
  const colour = accent === "brand" ? (settings?.brand_color ?? "#4F46E5") : accent;
  return <div style={{ "--a": colour } as CSSProperties}>{children}</div>;
}
