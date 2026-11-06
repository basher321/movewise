"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useSettings } from "@/components/SettingsProvider";
import { MODULE_LABELS } from "@/lib/admin/tabs";
import {
  applyLicenceKey,
  getFullLicence,
  isApiError,
  listCourseGroups,
  listUniversities,
  listVacancies,
  listVisaPrograms,
  listRemoteJobs,
  MODULES,
  type AdminUser,
  type LicenceView,
  type Module,
} from "@/lib/api";
import { TextField } from "./Field";
import TabPage from "./TabPage";
import type { ShowToast } from "./Toast";

const LOCK_TESTS: { module: Module; label: string; call: () => Promise<unknown[]> }[] = [
  { module: "course", label: "GET /api/courses", call: listCourseGroups },
  { module: "study", label: "GET /api/universities", call: listUniversities },
  { module: "job", label: "GET /api/vacancies", call: listVacancies },
  { module: "visa", label: "GET /api/visa-programs", call: listVisaPrograms },
  { module: "remote", label: "GET /api/remote-jobs", call: listRemoteJobs },
];

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Dhaka" });
}

// Licence tab (aLic() in the reference). Super admin only: anyone else sees FORBIDDEN.
export default function LicenceTab({ admin, toast }: { admin: AdminUser; toast: ShowToast }) {
  const { reload } = useSettings();
  const [view, setView] = useState<LicenceView | null>(null);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [output, setOutput] = useState("Results appear here.");
  const isSuper = admin.role === "super_admin";

  useEffect(() => {
    if (!isSuper) return;
    let live = true;
    void getFullLicence()
      .then((l) => {
        if (live) setView(l);
      })
      .catch((err: unknown) => {
        if (live) setError(isApiError(err) ? err.message : "The licence could not be loaded.");
      });
    return () => {
      live = false;
    };
  }, [isSuper]);

  if (!isSuper) return <div className="banner no">403 FORBIDDEN - You do not have access to this.</div>;
  if (!view) return error ? <div className="banner no">{error}</div> : null;

  async function apply(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await applyLicenceKey(key.trim());
      setView(await getFullLicence());
      setKey("");
      setError("");
      await reload();
      toast("Licence applied.");
    } catch (err) {
      setError(isApiError(err) && err.code === "VALIDATION" ? "This key is not valid." : isApiError(err) ? err.message : "The key could not be applied.");
    }
  }

  async function test(call: () => Promise<unknown[]>) {
    try {
      const rows = await call();
      setOutput("200 OK\n" + rows.length + " records returned.");
    } catch (err) {
      setOutput(isApiError(err) ? err.status + " " + err.code + "\n" + err.message : "Request failed.");
    }
  }

  return (
    <TabPage title="Licence & modules" sub="Modules not in your licence are hidden from menus AND refused by the data layer.">
      <div className="modg">
        <div className="modc on">
          <b>⚙ Core</b>
          <br />
          <span style={{ fontSize: 14 }}>✓ Always included</span>
          <p>Accounts &amp; roles, settings, payments &amp; ledger, invoices, refunds, documents, notifications, enquiries, audit log</p>
        </div>
        {MODULES.map((m) => (
          <div key={m} className={"modc " + (view.modules[m] ? "on" : "off")}>
            <b>{MODULE_LABELS[m]}</b>
            <br />
            <span style={{ fontSize: 14 }}>{view.modules[m] ? "✓ Licensed" : "🔒 Not licensed"}</span>
          </div>
        ))}
      </div>
      <div className="acc2">
        <div className="card">
          <h3>Current licence</h3>
          <div className="kv">
            <div>
              <span>Key</span>
              <b>{view.key ?? "–"}</b>
            </div>
            <div>
              <span>Licensed to</span>
              <b>{view.holder ?? "–"}</b>
            </div>
            <div>
              <span>Expires</span>
              <b>{view.key ? (view.expires_at ? shortDate(view.expires_at) : "Never") : "–"}</b>
            </div>
            <div>
              <span>Status</span>
              <b>{view.active ? "Active" : view.key ? "Expired" : "No licence yet"}</b>
            </div>
          </div>
          <form noValidate style={{ marginTop: 18 }} onSubmit={apply}>
            <div className="fgrid">
              <TextField
                label="New licence key"
                required
                full
                area={4}
                placeholder="Paste the key you received (it starts with MW1.)"
                value={key}
                onChange={setKey}
              />
            </div>
            <p className="err" role="alert">
              {error}
            </p>
            <button className="btn" type="submit">
              Apply key
            </button>
          </form>
        </div>
        <div className="card">
          <h3>Test the data-layer lock</h3>
          <p style={{ fontSize: 14 }}>These buttons ask for data directly, bypassing the menu. A locked module must answer 403.</p>
          {LOCK_TESTS.map((t) => (
            <div className="xrow" key={t.module}>
              <small>{t.label}</small>
              <button type="button" className="btn ghost sm" onClick={() => void test(t.call)}>
                Call
              </button>
            </div>
          ))}
          <pre className="out" aria-live="polite">
            {output}
          </pre>
        </div>
      </div>
    </TabPage>
  );
}
