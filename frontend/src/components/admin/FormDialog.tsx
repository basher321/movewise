"use client";

import { useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { isApiError } from "@/lib/api";
import Modal from "../Modal";
import { errorText } from "../auth/messages";

// formDlg() and fhtml() of the reference: a dialog with a .fgrid of fields, an error line, Save and Cancel.

export type FieldSpec = {
  k: string;
  l: string;
  t?: "text" | "number" | "date" | "email" | "area" | "check" | "select";
  o?: [string, string][]; // select options: value, label
  req?: boolean;
  full?: boolean;
  ph?: string;
  step?: string;
};

export type FormValues = Record<string, string | boolean>;

type Props = {
  title: string;
  fields: FieldSpec[];
  initial: FormValues;
  top?: ReactNode;
  wide?: boolean;
  saveLabel?: string;
  onClose: () => void;
  // Throws on a problem; an ApiError message is shown on the error line.
  onSave: (values: FormValues) => Promise<void>;
  onSignedOut: () => void;
};

const FULL: CSSProperties = { gridColumn: "1/-1" };

export default function FormDialog({ title, fields, initial, top, wide, saveLabel = "Save", onClose, onSave, onSignedOut }: Props) {
  const [values, setValues] = useState<FormValues>(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k: string, v: string | boolean) => setValues((old) => ({ ...old, [k]: v }));

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const missing = fields.find((f) => f.req && f.t !== "check" && !String(values[f.k] ?? "").trim());
    if (missing) return setError("Please fill in: " + missing.l + ".");
    setBusy(true);
    try {
      await onSave(values);
    } catch (err) {
      if (isApiError(err) && err.code === "UNAUTHENTICATED") return onSignedOut();
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <Modal open title={title} wide={wide} onClose={onClose}>
      {top}
      <form noValidate onSubmit={(e) => void save(e)}>
        <div className="fgrid">
          {fields.map((f) =>
            f.t === "check" ? (
              <label key={f.k} className="simf" style={FULL}>
                <input type="checkbox" checked={values[f.k] === true} onChange={(e) => set(f.k, e.target.checked)} /> {f.l}
              </label>
            ) : (
              <label key={f.k} className="fl" style={f.full ? FULL : undefined}>
                <span>
                  {f.l}
                  {f.req ? " *" : ""}
                </span>
                {f.t === "area" ? (
                  <textarea rows={3} style={{ minHeight: 0 }} value={String(values[f.k] ?? "")} onChange={(e) => set(f.k, e.target.value)} />
                ) : f.t === "select" ? (
                  <select value={String(values[f.k] ?? "")} onChange={(e) => set(f.k, e.target.value)}>
                    {(f.o ?? []).map(([v, label]) => (
                      <option key={v} value={v}>
                        {label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={f.t ?? "text"}
                    step={f.step}
                    placeholder={f.ph}
                    value={String(values[f.k] ?? "")}
                    onChange={(e) => set(f.k, e.target.value)}
                  />
                )}
              </label>
            ),
          )}
        </div>
        <p className="err" role="alert">
          {error}
        </p>
        <div className="cr" style={{ margin: 0 }}>
          <button className="btn" type="submit" disabled={busy}>
            {saveLabel}
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
