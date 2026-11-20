"use client";

// AI CV Agent (B28) Steps 6 and 7: template and length, then writing and review. The preview is
// the real PDF drawn as pictures by the server, so it matches the download exactly.

import { useCallback, useEffect, useState } from "react";
import {
  approveCv,
  CV_TEMPLATES,
  cvPages,
  cvPreviewUrl,
  cvSectionAction,
  generateCv,
  getCvState,
  reviewCv,
  saveCvData,
  undoCv,
  type CvData,
  type CvIssue,
  type CvSection,
  type CvSectionAction,
  type CvState,
} from "@/lib/api";
import { errorText } from "../auth/messages";
import { SectionEditor, type EditableSection } from "./editors";
import { CV_TEXT, SECTION_LABELS, TEMPLATE_LABELS } from "./strings";
import type { StepProps } from "./Wizard";

function useCvState({ module, project, state, setState, setError }: StepProps): CvState | null {
  useEffect(() => {
    if (state) return;
    void getCvState(module, project.id)
      .then(setState)
      .catch((err) => setError(errorText(err)));
  }, [module, project.id, state, setState, setError]);
  return state;
}

function Working({ text }: { text: string }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: "40px 20px" }} aria-live="polite">
      <div style={{ fontSize: 34 }}>✍️</div>
      <h3>{text}</h3>
      <p className="sub">This usually takes less than a minute.</p>
    </div>
  );
}

// ---------------------------------------------------------------- Step 6

export function StepTemplate(props: StepProps) {
  const { module, project, save, setState, next, setError } = props;
  const state = useCvState(props);
  const [working, setWorking] = useState(false);
  if (!state) return null;
  const chosen = project.template ?? state.recommended_template;
  const hasData = state.version > 0;

  async function write() {
    setWorking(true);
    try {
      if (!project.template) await save({ template: chosen });
      setState(await generateCv(module, project.id));
      next();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setWorking(false);
    }
  }

  if (working) return <Working text="Writing your CV…" />;
  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Choose a template</h2>
      <p className="sub" style={{ marginTop: 0 }}>
        All templates are single-column and ATS-friendly. You can change the template later without losing anything.
        {state.rules.photo !== "never" ? " Photos are left out so that applicant tracking systems can read the CV." : ""}
      </p>
      <div className="cvcards" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(min(170px,100%),1fr))" }}>
        {CV_TEMPLATES.map((t) => (
          <button key={t} type="button" className="cvcard" aria-pressed={chosen === t} onClick={() => void save({ template: t })}>
            {hasData ? (
              // eslint-disable-next-line @next/next/no-img-element -- a picture made by the API on request
              <img className="cvthumb" src={cvPreviewUrl(module, project.id, 1, state.version, t, 40)} alt={`${TEMPLATE_LABELS[t].name} preview`} loading="lazy" />
            ) : null}
            <b>{TEMPLATE_LABELS[t].name}</b>
            <small>{TEMPLATE_LABELS[t].text}</small>
            {state.recommended_template === t ? (
              <span className="bd ok" style={{ marginTop: 8 }}>
                Recommended
              </span>
            ) : null}
          </button>
        ))}
      </div>
      <h3 style={{ margin: "22px 0 10px" }}>Length</h3>
      <div className="seg" role="tablist" style={{ maxWidth: 320 }}>
        {([1, 2] as const).map((n) => (
          <button key={n} type="button" role="tab" aria-selected={project.page_length === n} onClick={() => void save({ page_length: n })}>
            {n} page{n === 2 ? "s" : ""}
          </button>
        ))}
      </div>
      <p className="sub">
        {state.rules.country === "Other" ? "" : `${state.rules.country}: `}
        {state.rules.notes}
      </p>
      <div className="cr" style={{ justifyContent: "flex-end" }}>
        {state.written ? (
          <button className="btn ghost" type="button" onClick={next}>
            Keep my written CV →
          </button>
        ) : null}
        <button className="btn" type="button" onClick={() => void write()}>
          {state.written ? "Write it again" : "Write my CV"} ✨
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Step 7

const ORDER: CvSection[] = ["summary", "experience", "education", "skills", "languages", "certifications", "training", "achievements", "references"];
const AI_SECTIONS: CvSection[] = ["summary", "experience"];
const SHORTER: CvSection[] = ["skills", "achievements", "training", "certifications", "references"];

function hasContent(d: CvData, s: CvSection): boolean {
  if (s === "summary") return !!d.professional_summary;
  if (s === "skills") return d.skills.technical.length + d.skills.soft.length > 0;
  if (s === "references") return true;
  if (s === "custom") return d.custom_sections.length > 0;
  return (d[s] as unknown[]).length > 0;
}

export function StepReview(props: StepProps) {
  const { module, project, save, setState, next, setError } = props;
  const state = useCvState(props);
  const [editing, setEditing] = useState<EditableSection | null>(null);
  const [busy, setBusy] = useState("");
  const [pages, setPages] = useState(1);
  const [issues, setIssues] = useState<CvIssue[] | null>(null);

  const check = useCallback(
    async (spelling: boolean) => {
      try {
        const r = await reviewCv(module, project.id, spelling);
        setIssues(r.issues);
      } catch (err) {
        setError(errorText(err));
      }
    },
    [module, project.id, setError],
  );

  const version = state?.version ?? 0;
  const template = project.template ?? state?.template;
  useEffect(() => {
    if (!version) return;
    void cvPages(module, project.id)
      .then((r) => setPages(r.pages))
      .catch(() => setPages(1));
    void reviewCv(module, project.id, false)
      .then((r) => setIssues(r.issues))
      .catch((err) => setError(errorText(err)));
  }, [module, project.id, version, template, project.page_length, setError]);

  if (!state) return null;
  if (!state.written) {
    return (
      <div className="card">
        <p>Your CV has not been written yet.</p>
        <button className="btn" type="button" onClick={() => void generateCv(module, project.id).then(setState, (e) => setError(errorText(e)))}>
          Write my CV ✨
        </button>
      </div>
    );
  }

  async function run(label: string, fn: () => Promise<CvState>) {
    setBusy(label);
    try {
      setState(await fn());
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
    }
  }

  const act = (section: CvSection, action: CvSectionAction) =>
    void run(`${action} ${section}`, () => cvSectionAction(module, project.id, section, action));
  const blocking = (issues ?? []).filter((i) => i.severity === "blocking");
  const warnings = (issues ?? []).filter((i) => i.severity === "warning");

  return (
    <div className="cvsplit">
      <div>
        <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <h2 style={{ margin: 0 }}>Review your {state.rules.document_name}</h2>
          <div className="cr" style={{ marginTop: 0 }}>
            <button className="btn ghost sm" type="button" disabled={!state.can_undo || !!busy} onClick={() => void run("undo", () => undoCv(module, project.id))}>
              ↶ Undo
            </button>
            <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => void run("write", () => generateCv(module, project.id))}>
              Write again ✨
            </button>
          </div>
        </div>
        {busy ? (
          <p className="sub" aria-live="polite">
            Working… ({busy})
          </p>
        ) : null}
        {state.ask_for.length ? (
          <div className="banner in" style={{ margin: "12px 0" }}>
            <b>Make it stronger:</b> the agent never invents results. If you know these, add them with Edit:
            <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
              {state.ask_for.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {ORDER.filter((s) => hasContent(state.data, s) || state.data.hidden_sections.includes(s)).map((s) => {
          const hidden = state.data.hidden_sections.includes(s);
          return (
            <div className="cvsec" key={s} style={hidden ? { opacity: 0.6 } : undefined}>
              <h4>
                {SECTION_LABELS[s]} {hidden ? <span className="bd">Removed</span> : null}
              </h4>
              {editing === s ? (
                <div style={{ marginTop: 10 }}>
                  <SectionEditor
                    key={state.version}
                    section={s as EditableSection}
                    state={state}
                    busy={!!busy}
                    onCancel={() => setEditing(null)}
                    onSave={async (d) => {
                      await run("save", () => saveCvData(module, project.id, d));
                      setEditing(null);
                    }}
                  />
                </div>
              ) : (
                <div className="cr">
                  {!hidden ? (
                    <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => setEditing(s as EditableSection)}>
                      Edit
                    </button>
                  ) : null}
                  {!hidden && AI_SECTIONS.includes(s) ? (
                    <>
                      <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => act(s, "regenerate")}>
                        Regenerate
                      </button>
                      <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => act(s, "stronger")}>
                        Make stronger
                      </button>
                    </>
                  ) : null}
                  {!hidden && (AI_SECTIONS.includes(s) || SHORTER.includes(s)) ? (
                    <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => act(s, "shorter")}>
                      Make shorter
                    </button>
                  ) : null}
                  <button className="btn ghost sm" type="button" disabled={!!busy} onClick={() => act(s, hidden ? "restore" : "remove")}>
                    {hidden ? "Put back" : "Remove"}
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {editing === null ? (
          <div className="cvsec">
            <h4>Personal details</h4>
            <div className="cr">
              <button className="btn ghost sm" type="button" onClick={() => setEditing("personal")}>
                Edit
              </button>
            </div>
          </div>
        ) : editing === "personal" ? (
          <div className="cvsec">
            <SectionEditor
              key={state.version}
              section="personal"
              state={state}
              busy={!!busy}
              onCancel={() => setEditing(null)}
              onSave={async (d) => {
                await run("save", () => saveCvData(module, project.id, d));
                setEditing(null);
              }}
            />
          </div>
        ) : null}

        <div className="card" style={{ marginTop: 18 }}>
          <div className="top" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <h3 style={{ margin: 0 }}>Quality check</h3>
            <button className="btn ghost sm" type="button" onClick={() => void check(true)}>
              Check spelling with AI
            </button>
          </div>
          {issues === null ? (
            <p className="sub">Checking…</p>
          ) : !issues.length ? (
            <p className="sub">✓ No problems found.</p>
          ) : (
            <ul style={{ margin: "10px 0 0", padding: 0, listStyle: "none" }}>
              {[...blocking, ...warnings].map((i, n) => (
                <li key={n} style={{ padding: "6px 0", borderTop: "1px solid var(--line)", fontSize: 14 }}>
                  <span className={"bd " + (i.severity === "blocking" ? "no" : "warn")} style={{ marginBottom: 2 }}>
                    {i.severity === "blocking" ? "Must fix" : "Tip"}
                  </span>{" "}
                  {i.message}
                </li>
              ))}
            </ul>
          )}
          <button
            className="btn"
            type="button"
            style={{ marginTop: 14 }}
            disabled={issues === null || blocking.length > 0 || !!busy}
            onClick={() => {
              setBusy("approve");
              void approveCv(module, project.id)
                .then((s) => {
                  setState(s);
                  setError("");
                  next();
                })
                .catch((err) => setError(errorText(err)))
                .finally(() => setBusy(""));
            }}
          >
            ✓ Approve CV
          </button>
          {blocking.length ? <p className="sub">Fix the &quot;Must fix&quot; items to approve.</p> : null}
        </div>
        <p className="sub" style={{ fontSize: 13 }}>
          {CV_TEXT.honest}
        </p>
      </div>

      <div className="cvsticky">
        <div className="cr" style={{ marginTop: 0, marginBottom: 10, flexWrap: "wrap" }}>
          <select
            aria-label="Template"
            value={project.template ?? state.template}
            onChange={(e) => void save({ template: e.target.value as (typeof CV_TEMPLATES)[number] })}
            style={{ maxWidth: 240 }}
          >
            {CV_TEMPLATES.map((t) => (
              <option key={t} value={t}>
                {TEMPLATE_LABELS[t].name}
              </option>
            ))}
          </select>
          <div className="seg" role="tablist" style={{ margin: 0, minWidth: 180 }}>
            {([1, 2] as const).map((n) => (
              <button key={n} type="button" role="tab" aria-selected={project.page_length === n} onClick={() => void save({ page_length: n })}>
                {n} page{n === 2 ? "s" : ""}
              </button>
            ))}
          </div>
        </div>
        {Array.from({ length: pages }, (_, i) => (
          // eslint-disable-next-line @next/next/no-img-element -- the PDF page drawn by the API
          <img
            key={`${i}-${state.version}-${project.template}-${project.page_length}`}
            className="cvpage"
            src={cvPreviewUrl(module, project.id, i + 1, state.version + (project.template ? CV_TEMPLATES.indexOf(project.template) * 1000 : 0), project.template ?? undefined, 90)}
            alt={`Page ${i + 1} of your CV`}
          />
        ))}
        <p className="sub" style={{ textAlign: "center" }}>
          {pages} of {project.page_length} page{project.page_length === 2 ? "s" : ""} · A4
        </p>
      </div>
    </div>
  );
}
