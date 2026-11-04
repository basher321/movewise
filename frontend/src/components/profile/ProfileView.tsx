"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MODULES, type ApplicantAccount, type Module } from "@/lib/api";
import { MODULE_UI } from "../auth/modules";
import { useToast } from "../admin/Toast";
import ModuleGate from "../ModuleGate";
import PageShell from "../PageShell";
import { useSession } from "../SessionProvider";
import { useSettings } from "../SettingsProvider";
import ApplicationsProfile from "./ApplicationsProfile";
import ChangePasswordDialog from "./ChangePasswordDialog";
import CourseProfile from "./CourseProfile";
import EditDetailsDialog from "./EditDetailsDialog";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function memberSince(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Dhaka" });
}

// /profile and /profile/[module] (showProfile() in the reference). Without a module, the first
// signed-in licensed module is shown, else the first licensed one.
export default function ProfileView({ module }: { module?: Module }) {
  const router = useRouter();
  const { licence } = useSettings();
  const { session, openAuth, reload } = useSession();
  const [dialog, setDialog] = useState<"edit" | "password" | null>(null);
  const { toast, toastNode } = useToast();
  if (!licence || !session) return null;

  const licensed = MODULES.filter((m) => licence.modules[m]);
  const current = module ?? licensed.find((m) => session.applicants[m]) ?? licensed[0] ?? "course";
  const ui = MODULE_UI[current];
  const account: ApplicantAccount | undefined = session.applicants[current];

  const tabs = (
    // Four modules do not fit one row at 390px: the tabs wrap onto two rows on narrow screens.
    <div
      className="seg"
      role="tablist"
      style={{
        gridTemplateColumns: `repeat(auto-fit,minmax(min(${licensed.length > 3 ? 150 : 100}px,100%),1fr))`,
        maxWidth: licensed.length > 3 ? 800 : 600,
        margin: "0 0 24px",
        borderRadius: 22,
      }}
    >
      {licensed.map((m) => (
        <button key={m} type="button" role="tab" aria-selected={m === current} onClick={() => router.push("/profile/" + m)}>
          {MODULE_UI[m].icon} {MODULE_UI[m].name}
          {session.applicants[m] ? " ✓" : ""}
        </button>
      ))}
    </div>
  );

  return (
    <ModuleGate module={current} accent={ui.accent}>
      <PageShell accent={ui.accent}>
        <section>
          <div className="wrap">
            {tabs}
            {account ? (
              <div className="pf">
                <aside className="card">
                  <div className="av">{initials(account.name)}</div>
                  <h3>{account.name}</h3>
                  <p>
                    {ui.icon} {ui.name}
                  </p>
                  <p style={{ marginTop: 6 }}>
                    <b>Account ID: {account.id}</b>
                  </p>
                  <div className="kv">
                    {[
                      ["Username", account.username],
                      ["Email", account.email],
                      ["Phone", account.phone],
                      ["Country", account.country],
                      ["Education / work", account.education],
                      ["Member since", memberSince(account.created_at)],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <span>{label}</span>
                        <b>{value || "–"}</b>
                      </div>
                    ))}
                  </div>
                  <div className="cr">
                    <button className="btn ghost sm" type="button" onClick={() => setDialog("edit")}>
                      Edit details
                    </button>
                    <button className="btn ghost sm" type="button" onClick={() => setDialog("password")}>
                      Change password
                    </button>
                  </div>
                </aside>
                {current === "course" ? (
                  <CourseProfile key={account.id} account={account} toast={toast} />
                ) : (
                  <ApplicationsProfile key={current} module={current} account={account} toast={toast} />
                )}
              </div>
            ) : (
              <div className="cta" style={{ padding: "40px 0" }}>
                <h2>
                  {ui.icon} {ui.name} account
                </h2>
                <p>
                  Each section has its own account and ID ({ui.prefix}-XXXXXX). Sign in or create your {ui.name} account to continue.
                </p>
                <div className="acts" style={{ justifyContent: "center" }}>
                  <button className="btn" type="button" onClick={() => openAuth({ mode: "in", module: current })}>
                    Sign in
                  </button>
                  <button className="btn ghost" type="button" onClick={() => openAuth({ mode: "up", module: current })}>
                    Sign up
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>
        {account && dialog === "edit" ? (
          <EditDetailsDialog
            account={account}
            onClose={() => setDialog(null)}
            onSaved={async () => {
              await reload();
              setDialog(null);
            }}
          />
        ) : null}
        {account && dialog === "password" ? (
          <ChangePasswordDialog
            module={current}
            onClose={() => setDialog(null)}
            onChanged={() => {
              setDialog(null);
              toast("Password changed.");
            }}
          />
        ) : null}
        {toastNode}
      </PageShell>
    </ModuleGate>
  );
}
