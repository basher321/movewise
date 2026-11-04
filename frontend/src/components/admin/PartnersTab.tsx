"use client";

import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import {
  ApiError,
  clearPartnerLogo,
  createPartner,
  isApiError,
  listPartners,
  PARTNER_TYPES,
  updatePartner,
  uploadPartnerLogo,
  type AdminUser,
  type LicenceView,
  type Module,
  type Partner,
  type PartnerInput,
  type PartnerType,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import Modal from "../Modal";
import { PARTNER_TYPE_LABELS } from "../PartnerStrip";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import FormDialog, { type FormValues } from "./FormDialog";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

export const PARTNER_MODULE_NAMES: Record<Module, string> = {
  course: "Training",
  study: "Student Consultancy",
  job: "Job Processing",
  visa: "Immigration Processing",
};
const LOGO_MAX_BYTES = 2 * 1024 * 1024;

// Licensed modules this person manages partners in (all licensed ones for the super admin).
export function partnerModules(admin: AdminUser, licence: LicenceView | null): Module[] {
  return (["course", "study", "job", "visa"] as const).filter(
    (m) => licence?.modules[m] && (admin.role === "super_admin" || (admin.role === "admin" && admin.sections.includes(m))),
  );
}

type Props = { admin: AdminUser; licence: LicenceView | null; toast: ShowToast; onSignedOut: () => void };

// The Partners tab (B18): B2B partner organisations and their logos, each in one module only.
export default function PartnersTab({ admin, licence, toast, onSignedOut }: Props) {
  const modules = partnerModules(admin, licence);
  const [module, setModule] = useState<Module | "">("");
  const [q, setQ] = useState("");
  const [active, setActive] = useState<"true" | "false" | "">("true");
  const [rows, setRows] = useState<Partner[] | null>(null);
  const [editing, setEditing] = useState<Partner | "new" | null>(null);
  const [logoFor, setLogoFor] = useState<Partner | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setRows(await listPartners({ module, q, active }));
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [module, q, active, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  return (
    <TabPage
      title="Partners"
      sub="Organisations you work with as a B2B partner. Tick “Show on website” to show the logo on that module's page only; contact details and agreements stay internal."
      actions={
        <button className="btn sm" type="button" onClick={() => setEditing("new")}>
          + Add partner
        </button>
      }
    >
      <div className="flt">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, country or contact" aria-label="Search partners" />
        {modules.length > 1 ? (
          <select aria-label="Module" value={module} onChange={(e) => setModule(e.target.value as Module | "")}>
            <option value="">All modules</option>
            {modules.map((m) => (
              <option key={m} value={m}>
                {PARTNER_MODULE_NAMES[m]}
              </option>
            ))}
          </select>
        ) : null}
        <select aria-label="Active" value={active} onChange={(e) => setActive(e.target.value as "true" | "false" | "")}>
          <option value="true">Active partners</option>
          <option value="false">Switched off</option>
          <option value="">All partners</option>
        </select>
      </div>
      <div className="card">
        {rows === null ? null : (
          <AdminTable
            rows={rows}
            rowKey={(p) => p.id}
            empty="No partners yet. Add the first organisation you work with."
            columns={[
              {
                head: "Logo",
                cell: (p) =>
                  p.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- the partner logo, served by the backend
                    <img src={p.logo_url} alt={p.name + " logo"} style={{ height: 36, maxWidth: 90, objectFit: "contain", background: "#fff", borderRadius: 8, padding: 3, border: "1px solid var(--line)" }} />
                  ) : (
                    <span style={{ color: "var(--muted)" }}>–</span>
                  ),
              },
              {
                head: "Partner",
                cell: (p) => (
                  <>
                    <b>{p.name}</b>
                    <small>{[PARTNER_TYPE_LABELS[p.partner_type], p.country].filter(Boolean).join(" · ")}</small>
                    {p.contact_name || p.contact_email ? <small>{[p.contact_name, p.contact_email, p.contact_phone].filter(Boolean).join(" · ")}</small> : null}
                  </>
                ),
              },
              { head: "Module", cell: (p) => PARTNER_MODULE_NAMES[p.module] },
              {
                head: "Website",
                cell: (p) => (
                  <>
                    <span className={p.show_on_site && p.active ? "bd ok" : "bd"}>{p.show_on_site && p.active ? "Shown" : "Hidden"}</span>
                    {p.agreement_until ? <small>Agreement until {formatDate(p.agreement_until)}</small> : null}
                  </>
                ),
              },
              { head: "Status", cell: (p) => <span className={p.active ? "bd ok" : "bd"}>{p.active ? "Active" : "Switched off"}</span> },
              {
                head: "",
                right: true,
                cell: (p) => (
                  <span className="cr" style={{ margin: 0, justifyContent: "flex-end" }}>
                    <button className="lk" type="button" onClick={() => setLogoFor(p)}>
                      Logo
                    </button>
                    <button className="lk" type="button" onClick={() => setEditing(p)}>
                      Edit
                    </button>
                  </span>
                ),
              },
            ]}
          />
        )}
      </div>
      {editing ? (
        <PartnerDialog
          partner={editing === "new" ? null : editing}
          modules={modules}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSaved={(message) => {
            setEditing(null);
            toast(message);
            void load();
          }}
        />
      ) : null}
      {logoFor ? (
        <LogoDialog
          partner={logoFor}
          onClose={() => setLogoFor(null)}
          onSignedOut={onSignedOut}
          onSaved={(p, message) => {
            setLogoFor(p);
            toast(message);
            void load();
          }}
        />
      ) : null}
    </TabPage>
  );
}

type DialogProps = { partner: Partner | null; modules: Module[]; onClose: () => void; onSaved: (message: string) => void; onSignedOut: () => void };

function PartnerDialog({ partner, modules, onClose, onSaved, onSignedOut }: DialogProps) {
  const initial: FormValues = {
    module: partner?.module ?? modules[0] ?? "study",
    partner_type: partner?.partner_type ?? "university",
    name: partner?.name ?? "",
    country: partner?.country ?? "",
    website: partner?.website ?? "",
    description: partner?.description ?? "",
    contact_name: partner?.contact_name ?? "",
    contact_email: partner?.contact_email ?? "",
    contact_phone: partner?.contact_phone ?? "",
    agreement_ref: partner?.agreement_ref ?? "",
    agreement_until: partner?.agreement_until ?? "",
    sort_order: String(partner?.sort_order ?? 0),
    show_on_site: partner?.show_on_site ?? true,
    active: partner?.active ?? true,
  };

  async function save(v: FormValues) {
    const order = String(v.sort_order).trim() || "0";
    if (!/^-?\d{1,5}$/.test(order)) throw new ApiError("VALIDATION", "Order must be a whole number, for example 0 or 10.");
    const website = String(v.website).trim();
    if (website && !website.startsWith("https://")) throw new ApiError("VALIDATION", "Website must start with https://, or leave it empty.");
    const input: PartnerInput = {
      module: String(v.module) as Module,
      partner_type: String(v.partner_type) as PartnerType,
      name: String(v.name).trim(),
      country: String(v.country).trim(),
      website,
      description: String(v.description).trim(),
      contact_name: String(v.contact_name).trim(),
      contact_email: String(v.contact_email).trim(),
      contact_phone: String(v.contact_phone).trim(),
      agreement_ref: String(v.agreement_ref).trim(),
      agreement_until: String(v.agreement_until) || null,
      show_on_site: v.show_on_site === true,
      sort_order: Number(order),
      active: v.active === true,
    };
    if (partner) await updatePartner(partner.id, input);
    else await createPartner(input);
    onSaved(partner ? "Partner saved." : "Partner added. Add its logo with “Logo”.");
  }

  const moduleOptions = (partner && !modules.includes(partner.module) ? [...modules, partner.module] : modules).map(
    (m): [string, string] => [m, PARTNER_MODULE_NAMES[m]],
  );

  return (
    <FormDialog
      title={partner ? "Edit partner" : "Add partner"}
      wide
      fields={[
        { k: "name", l: "Organisation name", req: true },
        { k: "partner_type", l: "Type", t: "select", o: PARTNER_TYPES.map((t): [string, string] => [t, PARTNER_TYPE_LABELS[t]]) },
        { k: "module", l: "Shown in module (only this one)", t: "select", o: moduleOptions },
        { k: "country", l: "Country" },
        { k: "website", l: "Website", ph: "https://…" },
        { k: "sort_order", l: "Order on the website (lower first)" },
        { k: "description", l: "Short description (public, max 300)", t: "area", full: true },
        { k: "contact_name", l: "Contact person (internal)" },
        { k: "contact_email", l: "Contact email (internal)", t: "email" },
        { k: "contact_phone", l: "Contact phone (internal)" },
        { k: "agreement_ref", l: "Agreement reference (internal)" },
        { k: "agreement_until", l: "Agreement valid until", t: "date" },
        { k: "show_on_site", l: "Show on website (logo, name, type and country)", t: "check" },
        { k: "active", l: "Active", t: "check" },
      ]}
      initial={initial}
      onClose={onClose}
      onSignedOut={onSignedOut}
      onSave={save}
    />
  );
}

type LogoProps = { partner: Partner; onClose: () => void; onSaved: (p: Partner, message: string) => void; onSignedOut: () => void };

function LogoDialog({ partner, onClose, onSaved, onSignedOut }: LogoProps) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<Partner>, message: string) {
    setBusy(true);
    setError("");
    try {
      onSaved(await action(), message);
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return setError("Please choose a PNG, JPEG or WebP picture.");
    if (file.size > LOGO_MAX_BYTES) return setError("The logo must be 2 MB or smaller.");
    void run(() => uploadPartnerLogo(partner.id, file), "Logo saved.");
  }

  return (
    <Modal open title={"Logo of " + partner.name} onClose={onClose}>
      <div className="plogo" style={{ maxWidth: 260 }}>
        {partner.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- the partner logo, served by the backend
          <img src={partner.logo_url} alt={partner.name + " logo"} />
        ) : (
          <span style={{ color: "#55607A", fontSize: 14 }}>No logo yet</span>
        )}
      </div>
      <p style={{ color: "var(--muted)", fontSize: 14, margin: "0 0 14px" }}>PNG, JPEG or WebP, at most 2 MB. A wide logo on a transparent or white background looks best.</p>
      <p className="err" role="alert">
        {error}
      </p>
      <div className="cr" style={{ margin: 0 }}>
        <label className="btn sm" style={{ opacity: busy ? 0.55 : 1 }}>
          {partner.logo_url ? "Change logo" : "Upload logo"}
          <input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={busy} onChange={pick} />
        </label>
        {partner.logo_url ? (
          <button className="btn ghost sm" type="button" disabled={busy} onClick={() => void run(() => clearPartnerLogo(partner.id), "Logo removed.")}>
            Remove logo
          </button>
        ) : null}
        <button className="btn ghost sm" type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </Modal>
  );
}
