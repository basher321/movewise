"use client";

import { useEffect, useState, type FormEvent } from "react";
import { isApiError, listAgents, setApplicationAgent, type AgentSection, type CaseRow, type PartnerAgent } from "@/lib/api";
import Modal from "../Modal";
import { errorText } from "../auth/messages";
import { termsText } from "./AgentsTab";

type Props = {
  row: CaseRow;
  module: AgentSection;
  onClose: () => void;
  onDone: () => void;
  onSignedOut: () => void;
};

// B16: which partner agent referred this case, or "Direct". Changing it cancels the old due commission.
export default function CaseAgentDialog({ row, module, onClose, onDone, onSignedOut }: Props) {
  const [agents, setAgents] = useState<PartnerAgent[] | null>(null);
  const [choice, setChoice] = useState(row.agent?.id ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    listAgents({ section: module, active: "true" })
      .then((list) => live && setAgents(list))
      .catch((err: unknown) => {
        if (!live) return;
        if (isApiError(err) && err.code === "UNAUTHENTICATED") onSignedOut();
        else setError(errorText(err));
      });
    return () => {
      live = false;
    };
  }, [module, onSignedOut]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (choice === (row.agent?.id ?? "")) return onClose();
    setBusy(true);
    try {
      await setApplicationAgent(row.id, choice || null);
      onDone();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  const chosen = agents?.find((a) => a.id === choice);
  return (
    <Modal open title={"Agent for " + row.ref} onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <label className="fl">
          <span>Referred by</span>
          <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={agents === null}>
            <option value="">Direct (no agent)</option>
            {row.agent && !agents?.some((a) => a.id === row.agent?.id) ? <option value={row.agent.id}>{row.agent.name}</option> : null}
            {(agents ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.firm ? " · " + a.firm : ""}
              </option>
            ))}
          </select>
        </label>
        <p style={{ color: "var(--muted)", fontSize: 14, margin: "10px 0 0" }}>
          {chosen ? "Commission: " + termsText(chosen) + ". " : ""}
          Changing the agent cancels the old commission if it is not paid yet.
        </p>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy || agents === null}>
            Save
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
