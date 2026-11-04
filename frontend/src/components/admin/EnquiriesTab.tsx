"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  addEnquiry,
  addEnquiryNote,
  ENQUIRY_STATUSES,
  isApiError,
  listAssignableAdmins,
  listEnquiries,
  updateEnquiry,
  type Enquiry,
  type EnquiryChanges,
  type EnquiryStatus,
  type StaffMember,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import Modal from "../Modal";
import { useSettings } from "../SettingsProvider";
import { errorText } from "../auth/messages";
import { interestLabel, interestOptions } from "../contact/interests";
import AdminTable from "./AdminTable";
import { TextField } from "./Field";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

// ENS in the reference: label and badge class.
const STATUS: Record<EnquiryStatus, [string, string]> = {
  new: ["New", "bd in"],
  contacted: ["Contacted", "bd warn"],
  converted: ["Converted", "bd ok"],
  closed: ["Closed", "bd"],
};

type Props = { toast: ShowToast; onSignedOut: () => void };

// The Enquiries tab (aEnq() in the reference).
export default function EnquiriesTab({ toast, onSignedOut }: Props) {
  const [status, setStatus] = useState<EnquiryStatus | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [rows, setRows] = useState<Enquiry[] | null>(null);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [editing, setEditing] = useState<Enquiry | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, people] = await Promise.all([listEnquiries(status, search, page), listAssignableAdmins()]);
      setRows(list.items);
      setTotal(list.total);
      setPageSize(list.page_size);
      setStaff(people);
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [status, search, page, onSignedOut]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 200);
    return () => clearTimeout(timer);
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  return (
    <TabPage
      title="Enquiries"
      sub="Questions and consultation bookings from the Contact page, plus enquiries you add by hand."
      actions={
        <button className="btn sm" type="button" onClick={() => setAdding(true)}>
          + Add enquiry
        </button>
      }
    >
      <div className="flt">
        <select aria-label="Status" value={status} onChange={(e) => (setPage(1), setStatus(e.target.value as EnquiryStatus | ""))}>
          <option value="">All statuses</option>
          {ENQUIRY_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS[s][0]}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={search}
          onChange={(e) => (setPage(1), setSearch(e.target.value))}
          placeholder="Search name, contact or message"
          aria-label="Search enquiries"
        />
      </div>
      <div className="card">
        {rows === null ? null : (
          <AdminTable
            rows={rows}
            rowKey={(e) => e.id}
            empty="No enquiries yet."
            columns={[
              { head: "Received", cell: (e) => formatDateTime(e.created_at) },
              {
                head: "Name",
                cell: (e) => (
                  <>
                    <b>{e.name}</b>
                    <small>{e.contact}</small>
                  </>
                ),
              },
              {
                head: "Interest",
                cell: (e) => (
                  <>
                    {interestLabel(e.interest)}
                    {e.preferred_date ? <small>Preferred: {e.preferred_date}</small> : null}
                  </>
                ),
              },
              {
                head: "Message",
                cell: (e) => (
                  <>
                    <span style={{ fontSize: 14 }}>{e.message || "–"}</span>
                    {e.notes.map((n) => (
                      <small key={n.id}>
                        • {n.text} ({[n.by, formatDateTime(n.at)].filter(Boolean).join(", ")})
                      </small>
                    ))}
                  </>
                ),
              },
              {
                head: "Status",
                cell: (e) => (
                  <>
                    <span className={STATUS[e.status][1]}>{STATUS[e.status][0]}</span>
                    <small>{e.assigned_to?.name ?? "Unassigned"}</small>
                  </>
                ),
              },
              {
                head: "",
                right: true,
                cell: (e) => (
                  <button className="lk" type="button" onClick={() => setEditing(e)}>
                    Update
                  </button>
                ),
              },
            ]}
          />
        )}
        {total > pageSize ? (
          <div className="cr">
            <button className="btn ghost sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span style={{ color: "var(--muted)", fontSize: 14 }}>
              Page {page} of {Math.ceil(total / pageSize)} · {total} enquiries
            </span>
            <button className="btn ghost sm" type="button" disabled={page * pageSize >= total} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        ) : null}
      </div>
      {editing ? (
        <UpdateDialog
          enquiry={editing}
          staff={staff}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            toast("Saved.");
            void load();
          }}
          onFail={(err) => handleFailure(err, toast, onSignedOut)}
        />
      ) : null}
      {adding ? (
        <AddDialog
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            toast("Enquiry added.");
            void load();
          }}
          onFail={(err) => handleFailure(err, toast, onSignedOut)}
        />
      ) : null}
    </TabPage>
  );
}

type DialogProps = { onClose: () => void; onSaved: () => void; onFail: (err: unknown) => void };

function UpdateDialog({ enquiry, staff, onClose, onSaved, onFail }: DialogProps & { enquiry: Enquiry; staff: StaffMember[] }) {
  const [status, setStatus] = useState<EnquiryStatus>(enquiry.status);
  // A deactivated admin is not a choice; the assignment is only sent when it was changed here.
  const current = enquiry.assigned_to?.id ?? "";
  const [assigned, setAssigned] = useState(staff.some((s) => s.id === current) ? current : "");
  const [assignedChanged, setAssignedChanged] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const changes: EnquiryChanges = {};
      if (status !== enquiry.status) changes.status = status;
      if (assignedChanged) changes.assigned_to = assigned || null;
      if (Object.keys(changes).length) await updateEnquiry(enquiry.id, changes);
      if (note.trim()) await addEnquiryNote(enquiry.id, note.trim());
      onSaved();
    } catch (err) {
      onFail(err);
      setBusy(false);
    }
  }

  return (
    <Modal open title={"Enquiry · " + enquiry.name} onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <label className="fl">
            <span>Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as EnquiryStatus)}>
              {ENQUIRY_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS[s][0]}
                </option>
              ))}
            </select>
          </label>
          <label className="fl">
            <span>Assigned to</span>
            <select
              value={assigned}
              onChange={(e) => {
                setAssigned(e.target.value);
                setAssignedChanged(true);
              }}
            >
              <option value="">Nobody</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <TextField label="Add a note" value={note} onChange={setNote} area={3} full />
        </div>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
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

function AddDialog({ onClose, onSaved, onFail }: DialogProps) {
  const { licence } = useSettings();
  const options = interestOptions(licence);
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [interest, setInterest] = useState<string>(options[0].value);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!name.trim()) return setError("Please fill in: Name.");
    if (!contact.trim()) return setError("Please fill in: Phone or email.");
    setBusy(true);
    try {
      await addEnquiry({ name, contact, interest, message });
      onSaved();
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") onFail(err);
      else setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title="Add enquiry" onClose={onClose}>
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          <TextField label="Name" value={name} onChange={setName} required />
          <TextField label="Phone or email" value={contact} onChange={setContact} required />
          <label className="fl">
            <span>Interested in</span>
            <select value={interest} onChange={(e) => setInterest(e.target.value)}>
              {options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <TextField label="Message" value={message} onChange={setMessage} area={3} full />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
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
