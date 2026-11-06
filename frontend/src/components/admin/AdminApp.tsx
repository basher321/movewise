"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import { useSettings } from "@/components/SettingsProvider";
import { allowedTabs, resolveTab, ROLE_NAMES, type TabId } from "@/lib/admin/tabs";
import { getSession, signOut, type AdminUser, type LicenceView } from "@/lib/api";
import ModuleLocked from "@/components/ModuleLocked";
import AdminAuth from "./AdminAuth";
import AuditTab from "./AuditTab";
import CatalogTab from "./CatalogTab";
import AccountsTab from "./AccountsTab";
import AgentsTab from "./AgentsTab";
import PartnersTab from "./PartnersTab";
import CasesTab from "./CasesTab";
import CoursesTab from "./CoursesTab";
import DocumentsTab from "./DocumentsTab";
import EnquiriesTab from "./EnquiriesTab";
import FeesTab from "./FeesTab";
import LicenceTab from "./LicenceTab";
import MyAccountDialog from "./MyAccountDialog";
import NotificationsTab from "./NotificationsTab";
import SettingsTab from "./SettingsTab";
import TeamTab from "./TeamTab";
import { useToast } from "./Toast";

// /admin: the sign-in card, or the admin panel frame with the tabs this person may open.
export default function AdminApp() {
  const { licence } = useSettings();
  // undefined while loading; null when nobody (or a deactivated admin) is signed in.
  const [admin, setAdmin] = useState<AdminUser | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    const session = await getSession();
    setAdmin(session.admin);
  }, []);
  // Stable, so the tabs do not reload when the panel renders again.
  const signedOut = useCallback(() => void refresh(), [refresh]);

  useEffect(() => {
    let live = true;
    void getSession().then((session) => {
      if (live) setAdmin(session.admin);
    });
    return () => {
      live = false;
    };
  }, []);

  if (admin === undefined || !licence) return null;
  if (!admin) return <AdminAuth onSignedIn={() => void refresh()} />;
  return <Panel admin={admin} licence={licence} onSignedOut={signedOut} onAccountSaved={signedOut} />;
}

// The admin panel frame; also used by /super-admin (B14).
export function Panel({
  admin,
  licence,
  onSignedOut,
  onAccountSaved,
  title = "Admin panel",
}: {
  admin: AdminUser;
  licence: LicenceView;
  onSignedOut: () => void;
  // Reloads the session, so a new name or email shows at once.
  onAccountSaved: () => void;
  // "Super Admin panel" on /super-admin (B14).
  title?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { toast, toastNode } = useToast();
  const [myAccount, setMyAccount] = useState(false);
  const tabs = allowedTabs(admin, licence);
  const requested = params.get("tab");
  const tab = resolveTab(requested, tabs);
  // The Courses tab of an unlicensed Training module shows the locked card instead of switching tabs.
  const courseLocked = requested === "course" && !licence.modules.course;

  // A tab that is not allowed (for example its module was unlicensed) switches to the first allowed tab.
  useEffect(() => {
    if (courseLocked) return;
    if (requested !== null && tab !== null && requested !== tab) router.replace(pathname + "?tab=" + tab, { scroll: false });
  }, [courseLocked, requested, tab, router, pathname]);

  const open = (id: TabId) => router.push(pathname + "?tab=" + id, { scroll: false });

  async function leave() {
    await signOut("admin");
    onSignedOut();
  }

  return (
    <section>
      <div className="wrap">
        <div className="top" style={{ alignItems: "center" }}>
          <h2 style={{ fontSize: 32 }}>{title}</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn ghost sm" type="button" onClick={() => setMyAccount(true)}>
              My account
            </button>
            <button className="btn ghost sm" type="button" onClick={() => void leave()}>
              Sign out
            </button>
          </div>
        </div>
        <p style={{ margin: "0 0 14px", color: "var(--muted)", fontSize: 14 }}>
          Signed in as <b>{admin.name}</b> · {ROLE_NAMES[admin.role]}
        </p>
        <div className="tabs2 tabs" role="tablist">
          {tabs.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={t.id === tab} onClick={() => open(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        {courseLocked ? (
          <ModuleLocked module="course" />
        ) : tab === "course" ? (
          <CoursesTab toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "study" || tab === "job" || tab === "visa" || tab === "remote" ? (
          <CasesTab key={tab} module={tab} admin={admin} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "agents" ? (
          <AgentsTab admin={admin} licence={licence} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "partners" ? (
          <PartnersTab admin={admin} licence={licence} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "acc" ? (
          <AccountsTab admin={admin} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "set" ? (
          <SettingsTab toast={toast} />
        ) : tab === "lic" ? (
          <LicenceTab admin={admin} toast={toast} />
        ) : tab === "enq" ? (
          <EnquiriesTab toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "docs" ? (
          <DocumentsTab toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "notifs" ? (
          <NotificationsTab admin={admin} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "team" ? (
          <TeamTab admin={admin} licence={licence} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "audit" ? (
          <AuditTab onSignedOut={onSignedOut} />
        ) : tab === "cat" ? (
          <CatalogTab licence={licence} toast={toast} onSignedOut={onSignedOut} />
        ) : tab === "fees" ? (
          <FeesTab licence={licence} toast={toast} onSignedOut={onSignedOut} />
        ) : (
          <EmptyState title="This section is built in a later step." />
        )}
      </div>
      {myAccount ? (
        <MyAccountDialog admin={admin} onClose={() => setMyAccount(false)} onSaved={onAccountSaved} toast={toast} />
      ) : null}
      {toastNode}
    </section>
  );
}
