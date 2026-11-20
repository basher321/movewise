"use client";

// AI CV Agent (B28) Step 5: "Reading your documents…", then the details as editable cards (with
// the file each came from and "Please confirm" badges) and a short form for what is missing
// (at most 6 questions on a screen; dropdowns, month pickers and chips where possible).

import { useEffect, useRef, useState } from "react";
import {
  answerCv,
  getCv,
  mergeCvFiles,
  readCvFile,
  saveCvData,
  type CvData,
  type CvMissingField,
  type CvProject,
} from "@/lib/api";
import { chunk, unanswered } from "@/lib/cv/wizard";
import { errorText } from "../auth/messages";
import { SectionEditor, sectionNeedsConfirm, sectionSummary, type EditableSection } from "./editors";
import type { StepProps } from "./Wizard";

const OVERVIEW: [EditableSection, string][] = [
  ["personal", "Personal details"],
  ["experience", "Work experience"],
  ["education", "Education"],
  ["skills", "Skills"],
  ["languages", "Languages"],
  ["certifications", "Certifications and licences"],
  ["training", "Training"],
  ["achievements", "Achievements"],
  ["references", "References"],
];

function Question({ f, value, set }: { f: CvMissingField; value: unknown; set: (v: unknown) => void }) {
  const [typed, setTyped] = useState("");
  const label = (
    <span>
      {f.label}
      {f.required ? "" : " (optional)"}
    </span>
  );
  if (f.kind === "chips") {
    const chosen = Array.isArray(value) ? (value as string[]) : [];
    const toggle = (o: string) => set(chosen.includes(o) ? chosen.filter((x) => x !== o) : [...chosen, o]);
    const extra = chosen.filter((c) => !f.options.includes(c));
    return (
      <div className="fl" style={{ gridColumn: "1 / -1" }}>
        {label}
        <div className="tabs2" style={{ marginBottom: 8 }}>
          {[...f.options, ...extra].map((o) => (
            <button key={o} type="button" aria-pressed={chosen.includes(o)} onClick={() => toggle(o)}>
              {chosen.includes(o) ? "✓ " : ""}
              {o}
            </button>
          ))}
        </div>
        <div className="cr" style={{ marginTop: 0 }}>
          <input
            value={typed}
            placeholder="Add your own"
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && typed.trim()) {
                e.preventDefault();
                set([...chosen, typed.trim()]);
                setTyped("");
              }
            }}
          />
          <button
            className="btn ghost sm"
            type="button"
            onClick={() => {
              if (typed.trim()) set([...chosen, typed.trim()]);
              setTyped("");
            }}
          >
            Add
          </button>
        </div>
      </div>
    );
  }
  if (f.kind === "boolean") {
    return (
      <label style={{ display: "flex", gap: 8, alignItems: "center", alignSelf: "end", paddingBottom: 10 }}>
        <input type="checkbox" checked={value === true} onChange={(e) => set(e.target.checked)} />
        {f.label}
      </label>
    );
  }
  if (f.kind === "select") {
    return (
      <label className="fl">
        {label}
        <select value={String(value ?? "")} onChange={(e) => set(e.target.value)}>
          <option value="">Choose…</option>
          {f.options.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="fl">
      {label}
      <input
        type={f.kind === "month" ? "month" : f.kind === "email" ? "email" : f.kind === "tel" ? "tel" : f.kind === "url" ? "url" : "text"}
        value={String(value ?? "")}
        placeholder={f.hint}
        onChange={(e) => set(e.target.value)}
      />
    </label>
  );
}

export default function StepDetails({ module, project, state, setState, next, setError, onProject }: StepProps & { onProject: (p: CvProject) => void }) {
  const [reading, setReading] = useState<string>("");
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [screen, setScreen] = useState(0);
  const [editing, setEditing] = useState<EditableSection | null>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      const waiting = (project.files ?? []).filter((f) => !f.removed && f.extraction_status === "waiting");
      const failed: string[] = [];
      for (const [i, f] of waiting.entries()) {
        setReading(`Reading your documents… (${i + 1} of ${waiting.length}: ${f.file_name})`);
        try {
          const done = await readCvFile(module, project.id, f.id);
          if (done.extraction_status === "failed" || done.extraction_status === "unsupported") failed.push(f.file_name);
        } catch (err) {
          setError(errorText(err));
          failed.push(f.file_name);
        }
      }
      setReading(waiting.length ? "Putting your details together…" : "Getting your details…");
      try {
        setState(await mergeCvFiles(module, project.id));
        onProject(await getCv(module, project.id));
        if (failed.length) setError(`Could not read: ${failed.join(", ")}. Please answer the questions below instead.`);
      } catch (err) {
        setError(errorText(err));
      }
      setReading("");
    })();
  }, [module, project, setState, setError, onProject]);

  if (reading || !state) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "40px 20px" }} aria-live="polite">
        <div style={{ fontSize: 34 }}>🤖</div>
        <h3>{reading || "Reading your documents…"}</h3>
        <p className="sub">This can take up to a minute for each document.</p>
      </div>
    );
  }

  const screens = chunk(state.missing);
  const current = screens[Math.min(screen, Math.max(screens.length - 1, 0))] ?? [];
  const requiredLeft = state.missing.filter((f) => f.required);

  async function sendAnswers() {
    const empty = unanswered(current, answers);
    if (empty.length) return setError("Please answer: " + empty.map((f) => f.label).join(", ") + ".");
    const payload: Record<string, unknown> = {};
    for (const f of current) {
      const v = answers[f.key] ?? f.value;
      if (v !== undefined && v !== null && v !== "") payload[f.key] = v;
    }
    setBusy(true);
    try {
      setState(await answerCv(module, project.id, payload));
      setScreen(0);
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveSection(d: CvData) {
    setBusy(true);
    try {
      setState(await saveCvData(module, project.id, d));
      setEditing(null);
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Check your details</h2>
      <p className="sub" style={{ marginTop: 0 }}>
        This is what the agent found. Fix anything that is wrong. Items marked <span className="bd cf">Please confirm</span> need a quick check.
      </p>
      {state.confirm.length ? (
        <div className="banner in" style={{ marginBottom: 14 }}>
          {state.confirm.length} item(s) need your confirmation before the CV can be approved: {state.confirm.slice(0, 3).join("; ")}
          {state.confirm.length > 3 ? "…" : ""}
        </div>
      ) : null}

      {current.length ? (
        <div className="card" style={{ marginBottom: 18, borderColor: "var(--a)" }}>
          <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <h3 style={{ margin: 0 }}>A few questions</h3>
            <span className="sub" style={{ margin: 0 }}>
              {screens.length > 1 ? `Screen ${Math.min(screen, screens.length - 1) + 1} of ${screens.length}` : ""}
            </span>
          </div>
          <div className="fgrid" style={{ marginTop: 12 }}>
            {current.map((f) => (
              <Question key={f.key} f={f} value={answers[f.key] ?? f.value} set={(v) => setAnswers((a) => ({ ...a, [f.key]: v }))} />
            ))}
          </div>
          <div className="cr" style={{ marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" type="button" disabled={busy} onClick={() => void sendAnswers()}>
              Save answers
            </button>
            {screens.length > 1 ? (
              <button className="btn ghost" type="button" onClick={() => setScreen((s) => (s + 1) % screens.length)}>
                Other questions
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="banner" style={{ marginBottom: 14 }}>
          ✓ All essential details are there.
        </div>
      )}

      {OVERVIEW.map(([section, label]) => (
        <div className="cvsec" key={section}>
          <div className="top" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h4>
              {label}{" "}
              {sectionNeedsConfirm(section, state.data) ? (
                <span className="bd cf" style={{ marginLeft: 6 }}>
                  Please confirm
                </span>
              ) : null}
            </h4>
            {editing !== section ? (
              <button className="btn ghost sm" type="button" onClick={() => setEditing(section)}>
                Edit
              </button>
            ) : null}
          </div>
          {editing === section ? (
            <div style={{ marginTop: 10 }}>
              <SectionEditor key={state.version} section={section} state={state} busy={busy} onSave={saveSection} onCancel={() => setEditing(null)} />
            </div>
          ) : (
            <p className="sub" style={{ margin: "4px 0 0", overflowWrap: "anywhere" }}>
              {sectionSummary(section, state.data)}
            </p>
          )}
        </div>
      ))}

      <div className="cr" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn" type="button" disabled={requiredLeft.length > 0} onClick={next}>
          Next →
        </button>
      </div>
      {requiredLeft.length ? (
        <p className="sub" style={{ textAlign: "right" }}>
          Answer the questions above to continue.
        </p>
      ) : null}
    </div>
  );
}
