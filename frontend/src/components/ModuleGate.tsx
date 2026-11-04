"use client";

import type { ReactNode } from "react";
import type { Module } from "@/lib/api";
import ModuleLocked from "./ModuleLocked";
import PageShell, { type Accent } from "./PageShell";
import { useSettings } from "./SettingsProvider";

type ModuleGateProps = {
  module: Module;
  accent: Accent | "brand";
  children: ReactNode;
};

// Wraps every page of a module: the page when the module is licensed, otherwise the locked card.
// While the licence loads the page is rendered but not shown, so Next.js can prerender the
// segment; the same wrapper stays once licensed, so the page is not mounted twice.
// The api layer still refuses an unlicensed module (MODULE_NOT_LICENSED).
export default function ModuleGate({ module, accent, children }: ModuleGateProps) {
  const { licence } = useSettings();
  if (licence && !licence.modules[module]) {
    return (
      <PageShell accent={accent}>
        <ModuleLocked module={module} />
      </PageShell>
    );
  }
  return <div style={{ display: licence ? "contents" : "none" }}>{children}</div>;
}
