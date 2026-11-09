// Admin panel tabs: which tabs a person may open. Labels and icons from allowedTabs() in the reference.

import { IMPORT_KIND_MODULE, IMPORT_KINDS, MODULES, type AdminRole, type AdminUser, type ImportKind, type LicenceView, type Module } from "../api";

export type TabId = Module | "enq" | "docs" | "agents" | "partners" | "import" | "acc" | "cat" | "fees" | "notifs" | "team" | "audit" | "set" | "lic";

export interface Tab {
  id: TabId;
  label: string;
}

export const MODULE_LABELS: Record<Module, string> = {
  course: "📚 Courses",
  study: "🎓 Student Consultancy",
  job: "🛂 Job Processing",
  visa: "🌍 Immigration Processing",
  remote: "💻 Remote Jobs",
};

export const ROLE_NAMES: Record<AdminRole, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  finance: "Finance Officer",
};

export function isModuleTab(id: string): id is Module {
  return (MODULES as readonly string[]).includes(id);
}

// B23: the Excel upload types of the licensed modules this person works in.
export function allowedImportKinds(admin: AdminUser, licence: LicenceView): ImportKind[] {
  return IMPORT_KINDS.filter((kind) => {
    const section = IMPORT_KIND_MODULE[kind];
    return licence.modules[section] && (admin.role === "super_admin" || (admin.role === "admin" && admin.sections.includes(section)));
  });
}

export function allowedTabs(admin: AdminUser, licence: LicenceView): Tab[] {
  const r = admin.role;
  const tabs: Tab[] = [];
  for (const m of MODULES) {
    const can = licence.modules[m] && (r === "super_admin" || (r === "admin" && admin.sections.includes(m)));
    if (can) tabs.push({ id: m, label: MODULE_LABELS[m] });
  }
  if (r !== "finance") tabs.push({ id: "enq", label: "💬 Enquiries" }, { id: "docs", label: "📄 Documents" });
  // B16: partner agents of Student Consultancy, Job Processing and Immigration (B19). Finance sees commissions in Accounts.
  const agentSections = (["study", "job", "visa", "remote"] as const).filter((m) => licence.modules[m] && (r === "super_admin" || (r === "admin" && admin.sections.includes(m))));
  if (agentSections.length) tabs.push({ id: "agents", label: "🤝 Agents" });
  // B18: B2B partners and logos, in any licensed module this person works in.
  const partnerModules = MODULES.filter((m) => licence.modules[m] && (r === "super_admin" || (r === "admin" && admin.sections.includes(m))));
  if (partnerModules.length) tabs.push({ id: "partners", label: "🏢 Partners" });
  if (allowedImportKinds(admin, licence).length) tabs.push({ id: "import", label: "📥 Excel upload" });
  if (r === "super_admin" || r === "finance") tabs.push({ id: "acc", label: "💳 Accounts" });
  if (r === "super_admin") tabs.push({ id: "cat", label: "🗂 Catalog" }, { id: "fees", label: "Fees" });
  tabs.push({ id: "notifs", label: "🔔 Notifications" });
  if (r === "super_admin") {
    tabs.push({ id: "team", label: "👥 Team" }, { id: "audit", label: "🛡 Audit log" }, { id: "set", label: "⚙ Settings" }, { id: "lic", label: "🔑 Licence" });
  }
  return tabs;
}

// The tab to show for ?tab=<requested>. Settings and Licence are kept even when not allowed,
// so their screens can show FORBIDDEN; any other tab that is not allowed falls back to the first one.
export function resolveTab(requested: string | null, tabs: Tab[]): TabId | null {
  if (requested === "set" || requested === "lic") return requested;
  const hit = tabs.find((t) => t.id === requested);
  return hit ? hit.id : (tabs[0]?.id ?? null);
}
