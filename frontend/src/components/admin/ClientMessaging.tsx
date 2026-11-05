"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  APP_STATUSES,
  ENROLMENT_STATUSES,
  isApiError,
  MODULE_NAMES,
  previewGroupMessage,
  sendClientMessage,
  sendGroupMessage,
  stagesOf,
  type AppStatus,
  type Channel,
  type EnrolmentStatus,
  type GroupFilters,
  type GroupPreview,
  type Module,
} from "@/lib/api";
import Modal from "../Modal";
import { errorText } from "../auth/messages";
import { TextField } from "./Field";

// B20: messages to clients by email, WhatsApp or both, and sending certificates and letters.

const STATUS_NAMES: Record<AppStatus, string> = {
  active: "Active",
  on_hold: "On hold",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  completed: "Completed",
};
const ENROLMENT_NAMES: Record<EnrolmentStatus, string> = {
  awaiting_payment: "Awaiting payment",
  active: "Active",
  completed: "Completed",
  cancelled: "Cancelled",
};

type ChannelProps = { value: Channel[]; onChange: (next: Channel[]) => void; email?: string | null; phone?: string | null };

// Email and WhatsApp checkboxes. With an address given, a channel the client cannot receive is off.
export function ChannelPicker({ value, onChange, email, phone }: ChannelProps) {
  const known = email !== undefined || phone !== undefined;
  const rows: [Channel, string, boolean][] = [
    ["email", "Email" + (known ? (email ? " (" + email + ")" : " (no email on file)") : ""), !known || !!email],
    ["whatsapp", "WhatsApp" + (known ? (phone ? " (" + phone + ")" : " (no phone on file)") : ""), !known || !!phone],
  ];
  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0, gridColumn: "1/-1" }}>
      <legend style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>Send by</legend>
      {rows.map(([channel, label, possible]) => (
        <label key={channel} className="simf" style={{ display: "flex", gap: 8, alignItems: "center", margin: "0 0 6px", opacity: possible ? 1 : 0.55 }}>
          <input
            type="checkbox"
            disabled={!possible}
            checked={possible && value.includes(channel)}
            onChange={(e) => onChange(e.target.checked ? [...value.filter((c) => c !== channel), channel] : value.filter((c) => c !== channel))}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}

function initialChannels(email?: string | null, phone?: string | null): Channel[] {
  const known = email !== undefined || phone !== undefined;
  return (["email", "whatsapp"] as Channel[]).filter((c) => !known || (c === "email" ? !!email : !!phone));
}

type Person = { accountId: string; name: string; email?: string | null; phone?: string | null };
type MessageProps = Person & { subject?: string; body?: string; onClose: () => void; onDone: (queued: number) => void; onSignedOut: () => void };

// "Send message" to one client of any module.
export function MessageDialog({ accountId, name, email, phone, subject: s0 = "", body: b0, onClose, onDone, onSignedOut }: MessageProps) {
  const [channels, setChannels] = useState<Channel[]>(initialChannels(email, phone));
  const [subject, setSubject] = useState(s0);
  const [body, setBody] = useState(b0 ?? "Dear " + name + ",\n\n\n");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!channels.length) return setError("Please choose email, WhatsApp or both.");
    if (!subject.trim() || !body.trim()) return setError("Please write the subject and the message.");
    setBusy(true);
    try {
      onDone((await sendClientMessage(accountId, { channels, subject: subject.trim(), body: body.trim() })).queued);
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title={"Message " + name} onClose={onClose}>
      <form noValidate onSubmit={(e) => void send(e)}>
        <div className="fgrid">
          <ChannelPicker value={channels} onChange={setChannels} email={email} phone={phone} />
          <TextField label="Subject" value={subject} onChange={setSubject} required full />
          <TextField label="Message" value={body} onChange={setBody} area={8} required full />
        </div>
        <p className="sub" style={{ fontSize: 13, margin: "6px 0 0" }}>
          WhatsApp sends the subject and the message together (up to 1,000 characters).
        </p>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Send
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

type SendDocProps = {
  title: string; // "Send certificate CERT-..." / "Send completion letter LTR-..."
  email?: string | null;
  phone?: string | null;
  send: (channels: Channel[]) => Promise<{ queued: number }>;
  onClose: () => void;
  onDone: (queued: number) => void;
  onSignedOut: () => void;
};

// Sends a certificate or letter: the email carries the PDF, WhatsApp a secure download link.
export function SendDocumentDialog({ title, email, phone, send, onClose, onDone, onSignedOut }: SendDocProps) {
  const [channels, setChannels] = useState<Channel[]>(initialChannels(email, phone));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    if (!channels.length) return setError("Please choose email, WhatsApp or both.");
    setBusy(true);
    try {
      onDone((await send(channels)).queued);
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title={title} onClose={onClose}>
      <form noValidate onSubmit={(e) => void submit(e)}>
        <p className="sub">The email has the PDF attached. WhatsApp gets a secure download link that works for 30 days.</p>
        <div className="fgrid">
          <ChannelPicker value={channels} onChange={setChannels} email={email} phone={phone} />
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            Send
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}

type GroupProps = { module: Module; onClose: () => void; onDone: (recipients: number, queued: number) => void; onSignedOut: () => void };

// "Message a group" of one module, with a live count of who will get it.
export function GroupMessageDialog({ module, onClose, onDone, onSignedOut }: GroupProps) {
  const course = module === "course";
  const [who, setWho] = useState<"all" | "with" | "without">("all");
  const [status, setStatus] = useState<AppStatus | "">("");
  const [stage, setStage] = useState<string>("");
  const [enrolment, setEnrolment] = useState<EnrolmentStatus | "">("");
  const [channels, setChannels] = useState<Channel[]>(["email", "whatsapp"]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<GroupPreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const filters: GroupFilters = {};
  if (who === "without") filters.has_application = false;
  if (who === "with") {
    filters.has_application = true;
    if (course && enrolment) filters.enrolment_status = enrolment;
    if (!course && status) filters.status = status;
    if (!course && stage !== "") filters.stage = Number(stage);
  }
  const key = JSON.stringify(filters);

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      previewGroupMessage(module, JSON.parse(key) as GroupFilters)
        .then((p) => live && setPreview(p))
        .catch((err: unknown) => {
          if (!live) return;
          if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
          setError(errorText(err));
        });
    }, 0);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [module, key, onSignedOut]);

  async function send(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || !preview) return;
    if (!channels.length) return setError("Please choose email, WhatsApp or both.");
    if (!subject.trim() || !body.trim()) return setError("Please write the subject and the message.");
    if (!preview.recipients) return setError("No client matches these choices.");
    if (!confirm("Send this message to " + preview.recipients + " client" + (preview.recipients === 1 ? "" : "s") + "?")) return;
    setBusy(true);
    try {
      const result = await sendGroupMessage(module, filters, { channels, subject: subject.trim(), body: body.trim() }, preview.recipients);
      onDone(preview.recipients, result.queued);
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  const label = course ? "an enrolment" : "an application";
  return (
    <Modal open title={"Message a group · " + MODULE_NAMES[module]} onClose={onClose}>
      <form noValidate onSubmit={(e) => void send(e)}>
        <div className="fgrid">
          <label className="fl">
            <span>Who</span>
            <select value={who} onChange={(e) => setWho(e.target.value as typeof who)}>
              <option value="all">Every {MODULE_NAMES[module]} client</option>
              <option value="with">Clients with {label}</option>
              <option value="without">Clients without {label}</option>
            </select>
          </label>
          {who === "with" && course ? (
            <label className="fl">
              <span>Enrolment status</span>
              <select value={enrolment} onChange={(e) => setEnrolment(e.target.value as EnrolmentStatus | "")}>
                <option value="">Any</option>
                {ENROLMENT_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {ENROLMENT_NAMES[s]}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {who === "with" && !course ? (
            <>
              <label className="fl">
                <span>Application status</span>
                <select value={status} onChange={(e) => setStatus(e.target.value as AppStatus | "")}>
                  <option value="">Any</option>
                  {APP_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {STATUS_NAMES[s]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fl">
                <span>Stage</span>
                <select value={stage} onChange={(e) => setStage(e.target.value)}>
                  <option value="">Any</option>
                  {stagesOf(module).map((s, i) => (
                    <option key={s} value={i}>
                      {i + 1}. {s}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : null}
          <ChannelPicker value={channels} onChange={setChannels} />
          <TextField label="Subject" value={subject} onChange={setSubject} required full />
          <TextField label="Message" value={body} onChange={setBody} area={7} required full />
        </div>
        <p className="sub" role="status" style={{ margin: "8px 0 0" }}>
          {preview
            ? preview.recipients +
              " client" +
              (preview.recipients === 1 ? "" : "s") +
              " · " +
              preview.with_email +
              " with email · " +
              preview.with_whatsapp +
              " with WhatsApp"
            : "Counting…"}
        </p>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy || !preview?.recipients}>
            {preview ? "Send to " + preview.recipients + " client" + (preview.recipients === 1 ? "" : "s") : "Send"}
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
