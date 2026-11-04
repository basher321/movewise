"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  cancelCommission,
  COMMISSION_STATUSES,
  listCommissions,
  payCommission,
  setCommission,
  type AdminUser,
  type AgentCommission,
  type AgentSection,
  type CommissionStatus,
  type PartnerAgent,
} from "@/lib/api";
import { poishaToText, takaToPoisha } from "@/lib/admin/amounts";
import { formatDate, formatMoney } from "@/lib/format";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import FormDialog from "./FormDialog";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

export const SECTION_NAMES: Record<AgentSection, string> = { study: "Student Consultancy", job: "Job Processing", visa: "Immigration Processing" };

const STATUS: Record<CommissionStatus, [string, string]> = {
  due: ["Due", "bd warn"],
  paid: ["Paid", "bd ok"],
  cancelled: ["Cancelled", "bd"],
};

type Props = {
  admin: AdminUser;
  sections: AgentSection[];
  agents?: PartnerAgent[];
  toast: ShowToast;
  onSignedOut: () => void;
  onChanged?: () => void;
};

type Dialog = { kind: "edit" | "pay" | "cancel"; row: AgentCommission } | null;

// Commissions owed to partner agents (B16). Super admin edits and cancels; super admin and finance mark paid.
export default function CommissionsPanel({ admin, sections, agents, toast, onSignedOut, onChanged }: Props) {
  const [status, setStatus] = useState<CommissionStatus | "">("due");
  const [module, setModule] = useState<AgentSection | "">("");
  const [agentId, setAgentId] = useState("");
  const [rows, setRows] = useState<AgentCommission[] | null>(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const isSuper = admin.role === "super_admin";
  const canPay = isSuper || admin.role === "finance";

  const load = useCallback(async () => {
    try {
      setRows(await listCommissions({ status, module, agent_id: agentId }));
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [status, module, agentId, onSignedOut]);

  useEffect(() => {
    void load();
  }, [load]);

  function done(message: string) {
    setDialog(null);
    toast(message);
    void load();
    onChanged?.();
  }

  const total = (rows ?? []).reduce((sum, r) => sum + (r.status === "cancelled" ? 0 : r.amount_poisha), 0);

  return (
    <>
      <div className="flt">
        <select aria-label="Commission status" value={status} onChange={(e) => setStatus(e.target.value as CommissionStatus | "")}>
          <option value="">All statuses</option>
          {COMMISSION_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS[s][0]}
            </option>
          ))}
        </select>
        {sections.length > 1 ? (
          <select aria-label="Section" value={module} onChange={(e) => setModule(e.target.value as AgentSection | "")}>
            <option value="">All sections</option>
            {sections.map((s) => (
              <option key={s} value={s}>
                {SECTION_NAMES[s]}
              </option>
            ))}
          </select>
        ) : null}
        {agents && agents.length ? (
          <select aria-label="Agent" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            <option value="">All agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      {error ? <div className="banner no">{error}</div> : null}
      <div className="card">
        {rows === null ? null : (
          <>
            <AdminTable
              rows={rows}
              rowKey={(r) => r.id}
              empty="No commissions here yet. Link an agent to a case to create one."
              columns={[
                {
                  head: "Case",
                  cell: (r) => (
                    <>
                      <b>{r.application_ref}</b>
                      <small>{SECTION_NAMES[r.module]}</small>
                    </>
                  ),
                },
                { head: "Applicant", cell: (r) => r.applicant_name },
                { head: "Agent", cell: (r) => r.agent_name },
                { head: "Amount", right: true, cell: (r) => <b>{formatMoney(r.amount_poisha)}</b> },
                {
                  head: "Status",
                  cell: (r) => (
                    <>
                      <span className={STATUS[r.status][1]}>{STATUS[r.status][0]}</span>
                      {r.paid_at ? <small>{formatDate(r.paid_at)}{r.pay_reference ? " · " + r.pay_reference : ""}</small> : null}
                      {r.note ? <small>{r.note}</small> : null}
                    </>
                  ),
                },
                {
                  head: "",
                  right: true,
                  cell: (r) =>
                    r.status !== "due" ? null : (
                      <span className="cr" style={{ margin: 0, justifyContent: "flex-end" }}>
                        {canPay ? (
                          <button className="lk" type="button" onClick={() => setDialog({ kind: "pay", row: r })}>
                            Mark paid
                          </button>
                        ) : null}
                        {isSuper ? (
                          <>
                            <button className="lk" type="button" onClick={() => setDialog({ kind: "edit", row: r })}>
                              Edit amount
                            </button>
                            <button className="lk r" type="button" onClick={() => setDialog({ kind: "cancel", row: r })}>
                              Cancel
                            </button>
                          </>
                        ) : null}
                      </span>
                    ),
                },
              ]}
            />
            {rows.length ? (
              <p style={{ margin: "14px 0 0", fontSize: 15 }}>
                Total shown (not cancelled): <b>{formatMoney(total)}</b>
              </p>
            ) : null}
          </>
        )}
      </div>
      {dialog?.kind === "edit" ? (
        <FormDialog
          title={"Commission for " + dialog.row.application_ref}
          fields={[
            { k: "amount", l: "Amount (taka)", req: true, ph: "e.g. 5000" },
            { k: "note", l: "Note", full: true },
          ]}
          initial={{ amount: poishaToText(dialog.row.amount_poisha), note: dialog.row.note }}
          onClose={() => setDialog(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const poisha = takaToPoisha(String(v.amount));
            if (poisha === null) throw new ApiError("VALIDATION", "Please enter the amount in taka, for example 5000 or 5000.50.");
            await setCommission(dialog.row.id, poisha, String(v.note));
            done("Commission updated.");
          }}
        />
      ) : null}
      {dialog?.kind === "pay" ? (
        <FormDialog
          title={"Pay " + formatMoney(dialog.row.amount_poisha) + " to " + dialog.row.agent_name}
          top={<p style={{ color: "var(--muted)", margin: "0 0 14px" }}>Record a payment you made outside the software (bank, bKash or cash). A paid commission cannot change any more.</p>}
          fields={[{ k: "ref", l: "Payment reference", full: true, ph: "e.g. bank transfer number" }]}
          initial={{ ref: "" }}
          saveLabel="Mark paid"
          onClose={() => setDialog(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            await payCommission(dialog.row.id, String(v.ref));
            done("Commission marked paid.");
          }}
        />
      ) : null}
      {dialog?.kind === "cancel" ? (
        <FormDialog
          title={"Cancel the commission for " + dialog.row.application_ref + "?"}
          fields={[{ k: "note", l: "Reason", full: true }]}
          initial={{ note: "" }}
          saveLabel="Cancel commission"
          onClose={() => setDialog(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            await cancelCommission(dialog.row.id, String(v.note));
            done("Commission cancelled.");
          }}
        />
      ) : null}
    </>
  );
}

