"use client";

import { useCallback, useEffect, useState } from "react";
import {
  approveAdmin,
  deactivateAdmin,
  listAdmins,
  MODULES,
  reactivateAdmin,
  resetStaffPassword,
  setRole,
  setSections,
  type AdminRole,
  type AdminUser,
  type LicenceView,
  type Module,
} from "@/lib/api";
import { MODULE_LABELS, ROLE_NAMES } from "@/lib/admin/tabs";
import { errorText } from "../auth/messages";
import Modal from "../Modal";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

type Props = { admin: AdminUser; licence: LicenceView; toast: ShowToast; onSignedOut: () => void };

// The Team tab (showTeam() in the reference). Admins are deactivated, never deleted.
export default function TeamTab({ admin: me, licence, toast, onSignedOut }: Props) {
  const [list, setList] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState("");
  // B15: a temporary password, shown once after "Reset password".
  const [temporary, setTemporary] = useState<{ name: string; email: string; password: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setList(await listAdmins());
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [onSignedOut]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(work: () => Promise<unknown>, message: string) {
    try {
      await work();
      toast(message);
    } catch (err) {
      handleFailure(err, toast, onSignedOut);
    }
    await load();
  }

  if (error) return <div className="banner no">{error}</div>;
  if (!list) return null;

  // The first Super Admin cannot be changed from this screen.
  const first = list.filter((a) => a.role === "super_admin").sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
  const licensed = MODULES.filter((m) => licence.modules[m]);

  // Only licensed boxes are shown; assignments of unlicensed modules stay stored.
  function toggle(a: AdminUser, m: Module, on: boolean) {
    const next = MODULES.filter((x) => (x === m ? on : a.sections.includes(x)));
    void run(() => setSections(a.id, next), "Sections saved.");
  }

  return (
    <>
      <p style={{ marginBottom: 18, maxWidth: 640 }}>
        New admins sign up on the admin sign-in page and appear here as pending. Approve them, then tick which sections (Courses, Student
        Consultancy, Job Processing) each admin may manage. Accounts, Fees and Team stay Super Admin only. To add another Super Admin,
        approve the person, then choose Super Admin as their role.
      </p>
      <div className="card">
        {list.map((a) => {
          const locked = a.id === first?.id || a.id === me.id;
          const state = !a.active ? ["Deactivated", "bd"] : a.approved ? ["Approved", "bd ok"] : ["Pending", "bd no"];
          const canEdit = !locked && a.active && a.approved;
          return (
            <div
              key={a.id}
              style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", padding: "14px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}
            >
              <div>
                <b>{a.name}</b>
                <small style={{ display: "block", color: "var(--muted)" }}>{a.email}</small>
              </div>
              <div>
                {!canEdit ? (
                  <span className="bd">{ROLE_NAMES[a.role]}</span>
                ) : (
                  <select
                    aria-label={"Role of " + a.name}
                    value={a.role}
                    style={{ width: "auto", padding: "6px 10px", marginRight: 6 }}
                    onChange={(e) => {
                      const role = e.target.value as AdminRole;
                      // B14 (owner, 2026-11-02): more than one Super Admin is allowed.
                      if (role === "super_admin" && !confirm(`Make ${a.name} a Super Admin with full access to everything?`)) return;
                      void run(() => setRole(a.id, role), "Role saved.");
                    }}
                  >
                    <option value="admin">{ROLE_NAMES.admin}</option>
                    <option value="finance">{ROLE_NAMES.finance}</option>
                    <option value="super_admin">{ROLE_NAMES.super_admin}</option>
                  </select>
                )}
                <span className={state[1]}>{state[0]}</span>
                {a.id === me.id || !a.active ? null : (
                  <button
                    className="lk"
                    type="button"
                    style={{ marginLeft: 10 }}
                    onClick={() => {
                      if (!confirm("Set a new temporary password for " + a.name + "? Their current password stops working at once.")) return;
                      void run(async () => {
                        const r = await resetStaffPassword(a.id);
                        setTemporary({ name: a.name, email: a.email, password: r.temporary_password });
                      }, "Temporary password set.");
                    }}
                  >
                    Reset password
                  </button>
                )}
                {canEdit && a.role === "admin" ? (
                  <div style={{ marginTop: 8, fontSize: 13, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {licensed.map((m) => (
                      <label key={m}>
                        <input
                          type="checkbox"
                          checked={a.sections.includes(m)}
                          onChange={(e) => toggle(a, m, e.target.checked)}
                          style={{ width: "auto", marginRight: 4 }}
                        />
                        {MODULE_LABELS[m]}
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="cr" style={{ margin: 0 }}>
                {locked ? null : !a.active ? (
                  <button className="btn ghost sm" type="button" onClick={() => void run(() => reactivateAdmin(a.id), "Admin reactivated.")}>
                    Reactivate
                  </button>
                ) : (
                  <>
                    {a.approved ? null : (
                      <button className="btn sm" type="button" onClick={() => void run(() => approveAdmin(a.id), "Admin approved.")}>
                        Approve
                      </button>
                    )}
                    <button
                      className="btn ghost sm"
                      type="button"
                      onClick={() => {
                        if (!confirm(a.approved ? "Deactivate this admin account?" : "Reject this admin account?")) return;
                        void run(() => deactivateAdmin(a.id), a.approved ? "Admin deactivated." : "Admin rejected.");
                      }}
                    >
                      {a.approved ? "Deactivate" : "Reject"}
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {temporary ? (
        <Modal open title="New temporary password" onClose={() => setTemporary(null)}>
          <p>Give these to {temporary.name} (by phone or in person). Ask them to change the password with My account after signing in.</p>
          <div className="kv">
            <div>
              <span>Email</span>
              <b>{temporary.email}</b>
            </div>
            <div>
              <span>Temporary password</span>
              <b style={{ fontFamily: "monospace", fontSize: 18 }}>{temporary.password}</b>
            </div>
          </div>
          <p className="sub" style={{ marginTop: 12 }}>
            This password is shown only now.
          </p>
          <div className="cr" style={{ margin: 0 }}>
            <button className="btn" type="button" onClick={() => setTemporary(null)}>
              Done
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
