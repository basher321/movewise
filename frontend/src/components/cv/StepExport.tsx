"use client";

// AI CV Agent (B28) Step 8: download the approved CV as PDF and DOCX, and the cover letter
// (when chosen) in its own tab with Edit, Regenerate and the same downloads.

import { useEffect, useState } from "react";
import { cvExportUrl, getCvState, makeCoverLetter, saveCoverLetter } from "@/lib/api";
import { exportName } from "@/lib/cv/wizard";
import { errorText } from "../auth/messages";
import { CV_TEXT } from "./strings";
import type { StepProps } from "./Wizard";

export default function StepExport({ module, project, state, setState, setError, save }: StepProps) {
  const [tab, setTab] = useState<"cv" | "letter">("cv");
  const [letter, setLetter] = useState<{ version: number; body: string }>({ version: 0, body: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!state) {
      void getCvState(module, project.id)
        .then(setState)
        .catch((err) => setError(errorText(err)));
    }
  }, [module, project.id, state, setState, setError]);

  if (!state) return null;
  // The text box starts from the saved letter each time a new version arrives.
  const text = state.letter && letter.version === state.letter.version ? letter.body : (state.letter?.body ?? "");
  const setText = (body: string) => setLetter({ version: state.letter?.version ?? 0, body });
  const name = state.data.personal.full_name;
  const approved = project.status === "approved";

  async function writeLetter() {
    setBusy(true);
    try {
      if (!project.cover_letter) await save({ cover_letter: true });
      setState(await makeCoverLetter(module, project.id));
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function keepLetter() {
    setBusy(true);
    try {
      setState(await saveCoverLetter(module, project.id, text));
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>Download</h2>
      <div className="seg" role="tablist" style={{ maxWidth: 420 }}>
        <button type="button" role="tab" aria-selected={tab === "cv"} onClick={() => setTab("cv")}>
          {state.rules.document_name}
        </button>
        <button type="button" role="tab" aria-selected={tab === "letter"} onClick={() => setTab("letter")}>
          Cover letter
        </button>
      </div>

      {tab === "cv" ? (
        <div className="card">
          {approved ? (
            <>
              <p style={{ marginTop: 0 }}>
                ✓ Your {state.rules.document_name} is approved. Download it in both formats: PDF to send, DOCX to edit in Word.
              </p>
              <div className="cr" style={{ flexWrap: "wrap" }}>
                <a className="btn" href={cvExportUrl(module, project.id, "pdf")} download={exportName(name, project.country, "cv", "pdf")}>
                  ⬇ PDF
                </a>
                <a className="btn ghost" href={cvExportUrl(module, project.id, "docx")} download={exportName(name, project.country, "cv", "docx")}>
                  ⬇ DOCX
                </a>
              </div>
              <p className="sub" style={{ fontSize: 13 }}>
                {exportName(name, project.country, "cv", "pdf")}
              </p>
            </>
          ) : (
            <p style={{ margin: 0 }}>Approve your CV on the Review step first; then you can download it here.</p>
          )}
        </div>
      ) : (
        <div className="card">
          {state.letter ? (
            <>
              <textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} aria-label="Cover letter" maxLength={20000} />
              <div className="cr" style={{ flexWrap: "wrap", marginTop: 10 }}>
                <button className="btn sm" type="button" disabled={busy || text === state.letter.body} onClick={() => void keepLetter()}>
                  Save changes
                </button>
                <button className="btn ghost sm" type="button" disabled={busy} onClick={() => void writeLetter()}>
                  Regenerate ✨
                </button>
                <a className="btn ghost sm" href={cvExportUrl(module, project.id, "pdf", "letter")} download={exportName(name, project.country, "letter", "pdf")}>
                  ⬇ PDF
                </a>
                <a className="btn ghost sm" href={cvExportUrl(module, project.id, "docx", "letter")} download={exportName(name, project.country, "letter", "docx")}>
                  ⬇ DOCX
                </a>
              </div>
            </>
          ) : (
            <>
              <p style={{ marginTop: 0 }}>A one-page letter written from your CV details and the job advert, for {state.rules.country === "Other" ? "your country" : state.rules.country}.</p>
              <button className="btn" type="button" disabled={busy} onClick={() => void writeLetter()}>
                {busy ? "Writing…" : "Write my cover letter ✨"}
              </button>
            </>
          )}
        </div>
      )}
      <p className="sub" style={{ fontSize: 13 }}>
        {CV_TEXT.honest}
      </p>
    </div>
  );
}
