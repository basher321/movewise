"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createAgent,
  listAgents,
  updateAgent,
  type AdminUser,
  type AgentSection,
  type CommissionType,
  type LicenceView,
  type PartnerAgent,
  type PartnerAgentInput,
} from "@/lib/api";
import { bpToText, percentToBp, poishaToText, takaToPoisha } from "@/lib/admin/amounts";
import { formatMoney } from "@/lib/format";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import CommissionsPanel, { SECTION_NAMES } from "./CommissionsPanel";
import FormDialog, { type FieldSpec, type FormValues } from "./FormDialog";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

type Props = { admin: AdminUser; licence: LicenceView | null; toast: ShowToast; onSignedOut: () => void };
type View = "agents" | "commissions";

// Licensed study/job/visa sections this person works in (all licensed ones for the super admin).
export function agentSections(admin: AdminUser, licence: LicenceView | null): AgentSection[] {
  return (["study", "job", "visa"] as const).filter(
    (m) => licence?.modules[m] && (admin.role === "super_admin" || (admin.role === "admin" && admin.sections.includes(m))),
  );
}

export function termsText(a: Pick<PartnerAgent, "commission_type" | "commission_poisha" | "commission_percent_bp">): string {
  return a.commission_type === "fixed" ? formatMoney(a.commission_poisha) + " per case" : bpToText(a.commission_percent_bp) + " % of the fee paid";
}

// The Agents tab (B16): partner agents who refer applicants, and the commission owed to them.
export default function AgentsTab({ admin, licence, toast, onSignedOut }: Props) {
  const sections = agentSections(admin, licence);
  const isSuper = admin.role === "super_admin";
  const [view, setView] = useState<View>("agents");
  const [q, setQ] = useState("");
  const [section, setSection] = useState<AgentSection | "">("");
  const [active, setActive] = useState<"true" | "false" | "">("true");
  const [rows, setRows] = useState<PartnerAgent[] | null>(null);
  const [all, setAll] = useState<PartnerAgent[]>([]);
  const [editing, setEditing] = useState<PartnerAgent | "new" | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, everyone] = await Promise.all([listAgents({ q, section, active }), listAgents()]);
      setRows(list);
      setAll(everyone);
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [q, section, active, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  const switcher = (
    <>
      <button className={view === "agents" ? "btn sm" : "btn ghost sm"} type="button" aria-pressed={view === "agents"} onClick={() => setView("agents")}>
        Agents
      </button>
      <button className={view === "commissions" ? "btn sm" : "btn ghost sm"} type="button" aria-pressed={view === "commissions"} onClick={() => setView("commissions")}>
        Commissions
      </button>
      {isSuper && view === "agents" ? (
        <button className="btn sm" type="button" onClick={() => setEditing("new")}>
          + Add agent
        </button>
      ) : null}
    </>
  );

  return (
    <TabPage
      title={view === "agents" ? "Partner agents" : "Agent commissions"}
      sub={
        view === "agents"
          ? "Agents and firms who refer students and workers to you. Link each case to its agent in the case view; the commission is created from the agent's terms."
          : "What you owe each agent. Pay outside the software, then mark the commission paid here."
      }
      actions={switcher}
    >
      {view === "commissions" ? (
        <CommissionsPanel admin={admin} sections={sections} agents={all} toast={toast} onSignedOut={onSignedOut} onChanged={() => void load()} />
      ) : (
        <>
          <div className="flt">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, firm, email, phone or country" aria-label="Search agents" />
            {sections.length > 1 ? (
              <select aria-label="Section" value={section} onChange={(e) => setSection(e.target.value as AgentSection | "")}>
                <option value="">All sections</option>
                {sections.map((s) => (
                  <option key={s} value={s}>
                    {SECTION_NAMES[s]}
                  </option>
                ))}
              </select>
            ) : null}
            <select aria-label="Active" value={active} onChange={(e) => setActive(e.target.value as "true" | "false" | "")}>
              <option value="true">Active agents</option>
              <option value="false">Switched off</option>
              <option value="">All agents</option>
            </select>
          </div>
          <div className="card">
            {rows === null ? null : (
              <AdminTable
                rows={rows}
                rowKey={(a) => a.id}
                empty={isSuper ? "No agents yet. Add your first partner agent." : "No agents in your sections yet."}
                columns={[
                  {
                    head: "Agent",
                    cell: (a) => (
                      <>
                        <b>{a.name}</b>
                        {a.firm ? <small>{a.firm}</small> : null}
                        {a.country ? <small>{a.country}</small> : null}
                      </>
                    ),
                  },
                  {
                    head: "Contact",
                    cell: (a) => (
                      <>
                        {a.phone ? <small>{a.phone}</small> : null}
                        {a.email ? <small>{a.email}</small> : null}
                        {!a.phone && !a.email ? "–" : null}
                      </>
                    ),
                  },
                  { head: "Sections", cell: (a) => a.sections.map((s) => SECTION_NAMES[s]).join(", ") },
                  { head: "Terms", cell: (a) => termsText(a) },
                  { head: "Cases", right: true, cell: (a) => a.referred },
                  { head: "Due", right: true, cell: (a) => formatMoney(a.due_poisha) },
                  { head: "Paid", right: true, cell: (a) => formatMoney(a.paid_poisha) },
                  { head: "Status", cell: (a) => <span className={a.active ? "bd ok" : "bd"}>{a.active ? "Active" : "Switched off"}</span> },
                  {
                    head: "",
                    right: true,
                    cell: (a) =>
                      isSuper ? (
                        <button className="lk" type="button" onClick={() => setEditing(a)}>
                          Edit
                        </button>
                      ) : null,
                  },
                ]}
              />
            )}
          </div>
        </>
      )}
      {editing ? (
        <AgentDialog
          agent={editing === "new" ? null : editing}
          sections={sections}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSaved={(message) => {
            setEditing(null);
            toast(message);
            void load();
          }}
        />
      ) : null}
    </TabPage>
  );
}

type DialogProps = {
  agent: PartnerAgent | null;
  sections: AgentSection[];
  onClose: () => void;
  onSaved: (message: string) => void;
  onSignedOut: () => void;
};

function AgentDialog({ agent, sections, onClose, onSaved, onSignedOut }: DialogProps) {
  const fields: FieldSpec[] = [
    { k: "name", l: "Name", req: true },
    { k: "firm", l: "Firm or company" },
    { k: "phone", l: "Phone" },
    { k: "email", l: "Email", t: "email" },
    { k: "country", l: "Country" },
    { k: "address", l: "Address" },
    ...sections.map((s): FieldSpec => ({ k: "sec_" + s, l: "Works in " + SECTION_NAMES[s], t: "check" })),
    {
      k: "commission_type",
      l: "Commission",
      t: "select",
      o: [
        ["fixed", "Fixed amount per case"],
        ["percent", "Percent of the application fee paid"],
      ],
    },
    { k: "amount", l: "Fixed amount (taka)", ph: "e.g. 5000" },
    { k: "percent", l: "Percent (%)", ph: "e.g. 10" },
    { k: "notes", l: "Notes (only staff see these)", t: "area", full: true },
    { k: "active", l: "Active (can be linked to new cases)", t: "check" },
  ];
  const initial: FormValues = {
    name: agent?.name ?? "",
    firm: agent?.firm ?? "",
    phone: agent?.phone ?? "",
    email: agent?.email ?? "",
    country: agent?.country ?? "",
    address: agent?.address ?? "",
    commission_type: agent?.commission_type ?? "fixed",
    amount: agent ? poishaToText(agent.commission_poisha) : "0",
    percent: agent ? bpToText(agent.commission_percent_bp) : "0",
    notes: agent?.notes ?? "",
    active: agent?.active ?? true,
  };
  for (const s of sections) initial["sec_" + s] = agent ? agent.sections.includes(s) : sections.length === 1;

  async function save(v: FormValues) {
    const chosen = sections.filter((s) => v["sec_" + s] === true);
    // Sections outside this person's view (unlicensed now) are kept as they were.
    const kept = (agent?.sections ?? []).filter((s) => !sections.includes(s));
    if (!chosen.length && !kept.length) throw new ApiError("VALIDATION", "Please tick at least one section.");
    const type = String(v.commission_type) as CommissionType;
    const poisha = takaToPoisha(String(v.amount || "0"));
    if (poisha === null) throw new ApiError("VALIDATION", "Please enter the fixed amount in taka, for example 5000.");
    const bp = percentToBp(String(v.percent || "0"));
    if (bp === null) throw new ApiError("VALIDATION", "Please enter a percent between 0 and 100, for example 10 or 12.5.");
    const input: PartnerAgentInput = {
      name: String(v.name).trim(),
      firm: String(v.firm).trim(),
      phone: String(v.phone).trim(),
      email: String(v.email).trim(),
      country: String(v.country).trim(),
      address: String(v.address).trim(),
      sections: [...kept, ...chosen],
      commission_type: type,
      commission_poisha: poisha,
      commission_percent_bp: bp,
      notes: String(v.notes),
      active: v.active === true,
    };
    if (agent) await updateAgent(agent.id, input);
    else await createAgent(input);
    onSaved(agent ? "Agent saved." : "Agent added.");
  }

  return (
    <FormDialog
      title={agent ? "Edit agent" : "Add agent"}
      wide
      fields={fields}
      initial={initial}
      onClose={onClose}
      onSignedOut={onSignedOut}
      onSave={save}
    />
  );
}
