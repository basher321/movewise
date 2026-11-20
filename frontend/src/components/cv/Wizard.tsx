"use client";

// AI CV Agent (B28): the 8-step wizard. Every click is saved at once (auto-save), so the person
// can leave and come back. Steps 1-4 are here; 5-8 in their own files.

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import {
  CV_CATEGORIES,
  getCv,
  getCvOptions,
  giveCvConsent,
  removeCvFile,
  saveCv,
  uploadCvFile,
  type CvDocKind,
  type CvOptions,
  type CvProject,
  type CvProjectChanges,
  type CvState,
  type Module,
} from "@/lib/api";
import { furthestStep, progress } from "@/lib/cv/wizard";
import { errorText } from "../auth/messages";
import StepDetails from "./StepDetails";
import StepExport from "./StepExport";
import { StepReview, StepTemplate } from "./StepWrite";
import { CATEGORY_LABELS, CV_FLAGS, CV_TEXT, CV_TYPE_CARDS, DOC_KIND_LABELS, STEP_TITLES } from "./strings";

export type StepProps = {
  module: Module;
  project: CvProject;
  save: (changes: CvProjectChanges) => Promise<CvProject | null>;
  state: CvState | null;
  setState: (s: CvState) => void;
  next: () => void;
  setError: (message: string) => void;
};

export default function Wizard({ module, id, onExit }: { module: Module; id: string; onExit: () => void }) {
  const [project, setProject] = useState<CvProject | null>(null);
  const [state, setState] = useState<CvState | null>(null);
  const [options, setOptions] = useState<CvOptions | null>(null);
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const top = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    void Promise.all([getCv(module, id), getCvOptions()])
      .then(([p, o]) => {
        if (!live) return;
        setProject(p);
        setOptions(o);
        setStep(Math.min(p.step, furthestStep(p)));
      })
      .catch((err) => live && setError(errorText(err)));
    return () => {
      live = false;
    };
  }, [module, id]);

  const save = useCallback(
    async (changes: CvProjectChanges): Promise<CvProject | null> => {
      try {
        const p = await saveCv(module, id, changes);
        setProject(p);
        setSaved(true);
        setError("");
        window.setTimeout(() => setSaved(false), 1500);
        return p;
      } catch (err) {
        setError(errorText(err));
        return null;
      }
    },
    [module, id],
  );

  function go(n: number) {
    if (!project) return;
    const target = Math.max(1, Math.min(n, 8));
    setStep(target);
    setError("");
    if (target > project.step) void save({ step: target });
    top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (!project || !options) {
    return <p className="err">{error}</p>;
  }
  const furthest = Math.max(furthestStep(project), step);
  const props: StepProps = { module, project, save, state, setState, next: () => go(step + 1), setError };
  const canNext =
    (step === 1 && !!project.cv_type) || (step === 2 && !!project.country) || (step === 3 && !!project.category) || step === 4;

  return (
    <div ref={top}>
      <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <button className="btn ghost sm" type="button" onClick={onExit}>
          ← {CV_TEXT.myCvs}
        </button>
        <span className="sub" style={{ margin: 0 }} aria-live="polite">
          Step {step} of 8 · {STEP_TITLES[step - 1]}
          {saved ? " · " + CV_TEXT.saved + " ✓" : ""}
        </span>
      </div>
      <div className="bar" style={{ marginTop: 12 }} aria-hidden>
        <i style={{ width: progress(step) + "%" }}></i>
      </div>
      <div className="cvsteps">
        {STEP_TITLES.map((t, i) => (
          <button
            key={t}
            type="button"
            className={i + 1 === step ? "on" : i + 1 < step ? "done" : ""}
            disabled={i + 1 > furthest}
            onClick={() => go(i + 1)}
          >
            {i + 1}. {t}
          </button>
        ))}
      </div>

      {step === 1 ? <StepType {...props} /> : null}
      {step === 2 ? <StepCountry {...props} options={options} /> : null}
      {step === 3 ? <StepCategory {...props} /> : null}
      {step === 4 ? <StepUpload {...props} options={options} onProject={setProject} /> : null}
      {step === 5 ? <StepDetails {...props} onProject={setProject} /> : null}
      {step === 6 ? <StepTemplate {...props} /> : null}
      {step === 7 ? <StepReview {...props} /> : null}
      {step === 8 ? <StepExport {...props} /> : null}

      <p className="err" role="alert" style={{ marginTop: 14 }}>
        {error}
      </p>
      {step <= 4 ? (
        <div className="cr" style={{ justifyContent: "space-between", marginTop: 10 }}>
          <button className="btn ghost" type="button" disabled={step === 1} onClick={() => go(step - 1)}>
            ← {CV_TEXT.back}
          </button>
          <button className="btn" type="button" disabled={!canNext} onClick={() => go(step + 1)}>
            {CV_TEXT.next} →
          </button>
        </div>
      ) : (
        <div className="cr" style={{ marginTop: 10 }}>
          <button className="btn ghost" type="button" onClick={() => go(step - 1)}>
            ← {CV_TEXT.back}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Step 1

function StepType({ project, save }: StepProps) {
  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>What kind of CV do you need?</h2>
      <div className="cvcards">
        {CV_TYPE_CARDS.map((c) => (
          <button key={c.type} type="button" className="cvcard" aria-pressed={project.cv_type === c.type} onClick={() => void save({ cv_type: c.type })}>
            <i>{c.icon}</i>
            <b>{c.title}</b>
            <small>{c.subtitle}</small>
          </button>
        ))}
      </div>
      <label className="card" style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 16, padding: 16, cursor: "pointer" }}>
        <input type="checkbox" checked={project.cover_letter} onChange={(e) => void save({ cover_letter: e.target.checked })} />
        <span>
          <b>{CV_TEXT.coverToggle}</b>
          <small style={{ display: "block", color: "var(--muted)" }}>A one-page letter written for your country and job advert.</small>
        </span>
      </label>
    </div>
  );
}

// ---------------------------------------------------------------- Step 2

function StepCountry({ project, save, options }: StepProps & { options: CvOptions }) {
  const [search, setSearch] = useState("");
  const q = search.trim().toLowerCase();
  const others = options.countries.filter((c) => !options.featured_countries.includes(c));
  const found = q ? options.countries.filter((c) => c.toLowerCase().includes(q)).slice(0, 24) : [];
  const isOther = !!project.country && !options.featured_countries.includes(project.country);
  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>Which country is the CV for?</h2>
      <div className="cvcards" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(min(150px,100%),1fr))" }}>
        {options.featured_countries.map((c) => (
          <button key={c} type="button" className="cvcard" aria-pressed={project.country === c} onClick={() => void save({ country: c })}>
            <i>{CV_FLAGS[c] ?? "🌍"}</i>
            <b>{c}</b>
          </button>
        ))}
        <button type="button" className="cvcard" aria-pressed={isOther} onClick={() => document.getElementById("cv-country-search")?.focus()}>
          <i>🌍</i>
          <b>{isOther ? project.country : "Other"}</b>
          <small>{isOther ? "Chosen" : `${others.length} more countries`}</small>
        </button>
      </div>
      <label className="fl" style={{ marginTop: 16, maxWidth: 420 }}>
        <span>Search all countries</span>
        <input id="cv-country-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Type a country name" />
      </label>
      {found.length ? (
        <div className="tabs2" style={{ marginTop: 10 }}>
          {found.map((c) => (
            <button key={c} type="button" aria-pressed={project.country === c} onClick={() => void save({ country: c }).then(() => setSearch(""))}>
              {c}
            </button>
          ))}
        </div>
      ) : q ? (
        <p className="sub">No country found.</p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- Step 3

function StepCategory({ project, save }: StepProps) {
  const [advert, setAdvert] = useState(project.job_advert_text);
  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>Which kind of job or application?</h2>
      <div className="tabs2">
        {CV_CATEGORIES.map((c) => (
          <button key={c} type="button" aria-pressed={project.category === c} onClick={() => void save({ category: c })}>
            {CATEGORY_LABELS[c]}
          </button>
        ))}
      </div>
      <label className="fl" style={{ marginTop: 10 }}>
        <span>Paste a job advert or link (optional)</span>
        <textarea
          rows={5}
          value={advert}
          maxLength={20000}
          onChange={(e) => setAdvert(e.target.value)}
          onBlur={() => advert !== project.job_advert_text && void save({ job_advert_text: advert })}
          placeholder="The agent uses only the keywords that really match your experience."
        />
      </label>
    </div>
  );
}

// ---------------------------------------------------------------- Step 4

type Uploading = { key: string; name: string; fraction: number; error: string; preview: string };

function StepUpload({ module, project, save, options, onProject, setError }: StepProps & { options: CvOptions; onProject: (p: CvProject) => void }) {
  const [busy, setBusy] = useState(false);
  const [uploads, setUploads] = useState<Uploading[]>([]);
  const [over, setOver] = useState(false);
  const [kind, setKind] = useState<CvDocKind>(project.doc_kinds[0] ?? "cv");
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const input = useRef<HTMLInputElement>(null);
  const files = (project.files ?? []).filter((f) => !f.removed);

  useEffect(() => () => Object.values(previews).forEach((u) => URL.revokeObjectURL(u)), [previews]);

  async function refresh() {
    onProject(await getCv(module, project.id));
  }

  function toggleKind(k: CvDocKind) {
    const next = project.doc_kinds.includes(k) ? project.doc_kinds.filter((x) => x !== k) : [...project.doc_kinds, k];
    void save({ doc_kinds: next });
    if (!project.doc_kinds.includes(k)) setKind(k);
  }

  async function consent(on: boolean) {
    if (!on || project.consent) return;
    try {
      onProject(await giveCvConsent(module, project.id));
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function send(list: FileList | File[]) {
    if (!project.consent) return setError("Please tick the consent box first.");
    const room = options.max_files - files.length;
    const chosen = Array.from(list).slice(0, Math.max(room, 0));
    if (!chosen.length) return setError(`You can upload up to ${options.max_files} files.`);
    setBusy(true);
    for (const file of chosen) {
      const key = file.name + file.size + Math.random();
      const preview = file.type.startsWith("image/") ? URL.createObjectURL(file) : "";
      setUploads((u) => [...u, { key, name: file.name, fraction: 0, error: "", preview }]);
      try {
        const p = await uploadCvFile(module, project.id, file, kind, (f) =>
          setUploads((u) => u.map((x) => (x.key === key ? { ...x, fraction: f } : x))),
        );
        const added = (p.files ?? []).find((f) => f.file_name === file.name && !files.some((o) => o.id === f.id));
        if (added && preview) setPreviews((pv) => ({ ...pv, [added.id]: preview }));
        onProject(p);
        setUploads((u) => u.filter((x) => x.key !== key));
      } catch (err) {
        setUploads((u) => u.map((x) => (x.key === key ? { ...x, error: errorText(err) } : x)));
      }
    }
    setBusy(false);
  }

  function drop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setOver(false);
    if (e.dataTransfer.files.length) void send(e.dataTransfer.files);
  }

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Upload your documents</h2>
      <p className="sub" style={{ marginTop: 0 }}>
        Tick what you have. No documents? Just press Next: the agent will ask you a few short questions instead.
      </p>
      <div className="tabs2">
        {options.doc_kinds
          .filter((k) => k !== "other")
          .map((k) => (
            <button key={k} type="button" aria-pressed={project.doc_kinds.includes(k)} onClick={() => toggleKind(k)}>
              {project.doc_kinds.includes(k) ? "✓ " : ""}
              {DOC_KIND_LABELS[k]}
            </button>
          ))}
      </div>
      <label className="card" style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: 16, cursor: "pointer", marginBottom: 14 }}>
        <input type="checkbox" checked={project.consent} disabled={project.consent} onChange={(e) => void consent(e.target.checked)} />
        <span>
          <b>{options.consent_text}</b>
          <small style={{ display: "block", color: "var(--muted)" }}>
            Files are stored encrypted and deleted automatically after 30 days. You can remove them at any time.
            {project.doc_kinds.includes("passport") ? " From a passport only your name and nationality are read; the number is never kept." : ""}
          </small>
        </span>
      </label>
      <label className="fl" style={{ maxWidth: 360 }}>
        <span>The next files are</span>
        <select value={kind} onChange={(e) => setKind(e.target.value as CvDocKind)}>
          {options.doc_kinds.map((k) => (
            <option key={k} value={k}>
              {DOC_KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </label>
      <div
        className={"cvdrop" + (over ? " over" : "")}
        role="button"
        tabIndex={0}
        aria-disabled={!project.consent || busy}
        style={{ opacity: project.consent ? 1 : 0.55, marginTop: 10 }}
        onClick={() => project.consent && input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && project.consent && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
      >
        <b>📄 Drag files here or tap to choose</b>
        <small style={{ display: "block", color: "var(--muted)", marginTop: 6 }}>
          PDF, DOC, DOCX, JPG or PNG · up to {options.max_files} files · {options.max_file_mb} MB each
        </small>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          onChange={(e) => {
            if (e.target.files) void send(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      <div style={{ marginTop: 12 }}>
        {uploads.map((u) => (
          <div className="cvfile" key={u.key}>
            {/* eslint-disable-next-line @next/next/no-img-element -- a local preview of the chosen file */}
            <span className="th">{u.preview ? <img src={u.preview} alt="" /> : "…"}</span>
            <div>
              <b>{u.name}</b>
              {u.error ? (
                <span className="err" style={{ display: "block", margin: 0 }}>
                  {u.error}
                </span>
              ) : (
                <div className="bar" style={{ marginTop: 6 }}>
                  <i style={{ width: Math.round(u.fraction * 100) + "%" }}></i>
                </div>
              )}
            </div>
          </div>
        ))}
        {files.map((f) => (
          <div className="cvfile" key={f.id}>
            <span className="th">
              {/* eslint-disable-next-line @next/next/no-img-element -- a local preview of the uploaded file */}
              {previews[f.id] ? <img src={previews[f.id]} alt="" /> : f.mime.includes("pdf") ? "PDF" : f.mime.includes("word") ? "DOC" : "IMG"}
            </span>
            <div>
              <b>{f.file_name}</b>
              <small style={{ color: "var(--muted)" }}>
                {DOC_KIND_LABELS[f.doc_kind]} · {Math.max(1, Math.round(f.size_bytes / 1024))} KB
                {f.extraction_status === "unsupported" && f.mime === "application/msword"
                  ? " · old .doc format: please upload it as PDF or DOCX"
                  : ""}
              </small>
            </div>
            <button
              className="btn ghost sm"
              type="button"
              onClick={() =>
                void removeCvFile(module, project.id, f.id)
                  .then(onProject)
                  .catch((err) => setError(errorText(err)))
              }
            >
              Remove
            </button>
          </div>
        ))}
        {!files.length && !uploads.length ? null : (
          <button className="btn ghost sm" type="button" style={{ marginTop: 8 }} onClick={() => void refresh()}>
            Refresh list
          </button>
        )}
      </div>
    </div>
  );
}
