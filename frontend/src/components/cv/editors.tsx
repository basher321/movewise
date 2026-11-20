"use client";

// AI CV Agent (B28): editors for each part of the CV data, used on Step 5 (check what was read)
// and Step 7 (Edit). Each item shows where it came from and a yellow "Please confirm" badge when
// the AI was unsure or two documents disagree.

import { useState, type ReactNode } from "react";
import type { CvData, CvItemBase, CvSensitive, CvState } from "@/lib/api";
import { linesOf, splitList } from "@/lib/cv/wizard";
import { SENSITIVE_LABELS } from "./strings";

type Save = (next: CvData) => Promise<void> | void;
export type EditableSection =
  | "personal" | "summary" | "experience" | "education" | "skills" | "languages" | "certifications" | "training"
  | "achievements" | "references";

const copy = (d: CvData): CvData => JSON.parse(JSON.stringify(d)) as CvData;
const newId = () => Math.random().toString(16).slice(2, 10);
const base = (): CvItemBase => ({ id: newId(), source_file: "your answer", confidence: "high", confirm: false, note: "" });

export function SourceLine({ item }: { item: CvItemBase }) {
  return (
    <>
      {item.source_file ? <span className="cvsrc">From: {item.source_file}</span> : null}
      {item.confirm ? (
        <span className="cvsrc" style={{ color: "#A16207" }}>
          <span className="bd cf" style={{ margin: "4px 6px 0 0" }}>
            Please confirm
          </span>
          {item.note}
        </span>
      ) : null}
    </>
  );
}

function Field({ label, children, full }: { label: string; children: ReactNode; full?: boolean }) {
  return (
    <label className="fl" style={full ? { gridColumn: "1 / -1" } : undefined}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Month({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // <input type="month"> keeps YYYY-MM; a year-only date stays as typed.
  return /^\d{4}$/.test(value) ? (
    <input value={value} inputMode="numeric" onChange={(e) => onChange(e.target.value)} placeholder="YYYY" />
  ) : (
    <input type="month" value={value} onChange={(e) => onChange(e.target.value)} />
  );
}

type ListKey = "experience" | "education" | "languages" | "certifications" | "training" | "achievements" | "references";

function ItemCard<K extends ListKey>({
  data,
  list,
  index,
  setData,
  children,
}: {
  data: CvData;
  list: K;
  index: number;
  setData: (d: CvData) => void;
  children: ReactNode;
}) {
  const item = data[list][index] as CvItemBase;
  return (
    <div className="card" style={{ padding: 16, marginBottom: 12, borderColor: item.confirm ? "#EAB308" : undefined }}>
      <div className="fgrid">{children}</div>
      <SourceLine item={item} />
      <div className="cr" style={{ marginTop: 10 }}>
        {item.confirm ? (
          <button
            className="btn sm"
            type="button"
            onClick={() => {
              const d = copy(data);
              const it = d[list][index] as CvItemBase;
              it.confirm = false;
              it.note = "";
              setData(d);
            }}
          >
            ✓ Confirm this is correct
          </button>
        ) : null}
        <button
          className="btn ghost sm"
          type="button"
          onClick={() => {
            const d = copy(data);
            (d[list] as CvItemBase[]).splice(index, 1);
            setData(d);
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

// One editable section. Changes stay local until "Save".
export function SectionEditor({
  section,
  state,
  onSave,
  onCancel,
  busy,
}: {
  section: EditableSection;
  state: CvState;
  onSave: Save;
  onCancel?: () => void;
  busy?: boolean;
}) {
  const [data, setData] = useState<CvData>(() => copy(state.data));
  const set = (fn: (d: CvData) => void) => {
    const d = copy(data);
    fn(d);
    setData(d);
  };

  let body: ReactNode = null;
  if (section === "personal") {
    const p = data.personal;
    const text = (key: "full_name" | "email" | "phone" | "city" | "country" | "linkedin" | "website", label: string, type = "text") => (
      <Field label={label}>
        <input
          type={type}
          value={p[key]}
          onChange={(e) =>
            set((d) => {
              d.personal[key] = e.target.value;
              d.personal.confirm_fields = d.personal.confirm_fields.filter((f) => f !== key);
            })
          }
        />
        {p.sources[key] ? <span className="cvsrc">From: {p.sources[key]}</span> : null}
        {p.confirm_fields.includes(key) ? <span className="bd cf">Please confirm</span> : null}
      </Field>
    );
    body = (
      <>
        <div className="fgrid">
          {text("full_name", "Full name")}
          {text("email", "Email", "email")}
          {text("phone", "Phone", "tel")}
          {text("city", "City")}
          {text("country", "Country")}
          {text("linkedin", "LinkedIn (optional)", "url")}
        </div>
        {state.rules.allows.length ? (
          <div style={{ marginTop: 12 }}>
            <p className="sub" style={{ margin: "0 0 8px" }}>
              Personal details {state.rules.country} employers may ask for. They are shown only if you turn them on.
            </p>
            <div className="fgrid">
              {state.rules.allows.map((f: CvSensitive) => (
                <Field label={SENSITIVE_LABELS[f]} key={f}>
                  <input
                    type={f === "date_of_birth" ? "month" : "text"}
                    value={p[f]}
                    onChange={(e) => set((d) => void (d.personal[f] = e.target.value))}
                  />
                  <span className="cvsrc">
                    <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={p.show.includes(f)}
                        onChange={(e) =>
                          set((d) => {
                            d.personal.show = e.target.checked ? [...d.personal.show, f] : d.personal.show.filter((x) => x !== f);
                          })
                        }
                      />
                      Show on my CV
                    </label>
                  </span>
                </Field>
              ))}
            </div>
          </div>
        ) : null}
      </>
    );
  } else if (section === "summary") {
    body = (
      <textarea
        rows={5}
        value={data.professional_summary}
        maxLength={1200}
        onChange={(e) => set((d) => void (d.professional_summary = e.target.value))}
        aria-label="Professional summary"
      />
    );
  } else if (section === "experience") {
    body = (
      <>
        {data.experience.map((x, i) => (
          <ItemCard key={x.id} data={data} list="experience" index={i} setData={setData}>
            <Field label="Job title">
              <input value={x.job_title} onChange={(e) => set((d) => void (d.experience[i].job_title = e.target.value))} />
            </Field>
            <Field label="Employer">
              <input value={x.employer} onChange={(e) => set((d) => void (d.experience[i].employer = e.target.value))} />
            </Field>
            <Field label="City, country">
              <input value={x.location} onChange={(e) => set((d) => void (d.experience[i].location = e.target.value))} />
            </Field>
            <Field label="Start">
              <Month value={x.start_date} onChange={(v) => set((d) => void (d.experience[i].start_date = v))} />
            </Field>
            <Field label="End">
              {x.current ? (
                <input value="Present" disabled />
              ) : (
                <Month value={x.end_date} onChange={(v) => set((d) => void (d.experience[i].end_date = v))} />
              )}
              <span className="cvsrc">
                <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={x.current}
                    onChange={(e) =>
                      set((d) => {
                        d.experience[i].current = e.target.checked;
                        if (e.target.checked) d.experience[i].end_date = "";
                      })
                    }
                  />
                  I still work here
                </label>
              </span>
            </Field>
            <Field label="Duties and results (one per line)" full>
              <textarea
                rows={4}
                value={x.bullets.join("\n")}
                onChange={(e) => set((d) => void (d.experience[i].bullets = e.target.value.split("\n")))}
              />
            </Field>
          </ItemCard>
        ))}
        <button
          className="btn ghost sm"
          type="button"
          onClick={() =>
            set((d) =>
              d.experience.unshift({ ...base(), job_title: "", employer: "", location: "", start_date: "", end_date: "", current: false, bullets: [] }),
            )
          }
        >
          + Add a job
        </button>
      </>
    );
  } else if (section === "education") {
    body = (
      <>
        {data.education.map((x, i) => (
          <ItemCard key={x.id} data={data} list="education" index={i} setData={setData}>
            <Field label="Qualification">
              <input value={x.degree} onChange={(e) => set((d) => void (d.education[i].degree = e.target.value))} />
            </Field>
            <Field label="Subject">
              <input value={x.field} onChange={(e) => set((d) => void (d.education[i].field = e.target.value))} />
            </Field>
            <Field label="Institution">
              <input value={x.institution} onChange={(e) => set((d) => void (d.education[i].institution = e.target.value))} />
            </Field>
            <Field label="Finished">
              <Month value={x.end_date} onChange={(v) => set((d) => void (d.education[i].end_date = v))} />
            </Field>
            <Field label="Result / grade">
              <input value={x.grade} onChange={(e) => set((d) => void (d.education[i].grade = e.target.value))} />
            </Field>
          </ItemCard>
        ))}
        <button
          className="btn ghost sm"
          type="button"
          onClick={() =>
            set((d) =>
              d.education.unshift({ ...base(), degree: "", field: "", institution: "", location: "", start_date: "", end_date: "", grade: "", details: [] }),
            )
          }
        >
          + Add a qualification
        </button>
      </>
    );
  } else if (section === "skills") {
    body = (
      <div className="fgrid">
        <Field label="Job skills (separate with commas)" full>
          <textarea
            rows={3}
            defaultValue={data.skills.technical.join(", ")}
            onChange={(e) => set((d) => void (d.skills.technical = splitList(e.target.value)))}
          />
        </Field>
        <Field label="Personal strengths (separate with commas)" full>
          <textarea
            rows={2}
            defaultValue={data.skills.soft.join(", ")}
            onChange={(e) => set((d) => void (d.skills.soft = splitList(e.target.value)))}
          />
        </Field>
      </div>
    );
  } else if (section === "languages") {
    body = (
      <>
        {data.languages.map((x, i) => (
          <ItemCard key={x.id} data={data} list="languages" index={i} setData={setData}>
            <Field label="Language">
              <input value={x.language} onChange={(e) => set((d) => void (d.languages[i].language = e.target.value))} />
            </Field>
            <Field label="Level">
              <input value={x.level} onChange={(e) => set((d) => void (d.languages[i].level = e.target.value))} />
            </Field>
            <Field label="Test score (optional)">
              <input value={x.test_score} onChange={(e) => set((d) => void (d.languages[i].test_score = e.target.value))} />
            </Field>
          </ItemCard>
        ))}
        <button
          className="btn ghost sm"
          type="button"
          onClick={() => set((d) => d.languages.push({ ...base(), language: "", level: "", test_score: "" }))}
        >
          + Add a language
        </button>
      </>
    );
  } else if (section === "certifications" || section === "training") {
    const list = data[section];
    body = (
      <>
        {list.map((x, i) => (
          <ItemCard key={x.id} data={data} list={section} index={i} setData={setData}>
            <Field label="Name">
              <input value={x.name} onChange={(e) => set((d) => void (d[section][i].name = e.target.value))} />
            </Field>
            <Field label={section === "training" ? "Provider" : "Issued by"}>
              <input
                value={"issuer" in x ? x.issuer : x.provider}
                onChange={(e) =>
                  set((d) => {
                    const it = d[section][i];
                    if ("issuer" in it) it.issuer = e.target.value;
                    else it.provider = e.target.value;
                  })
                }
              />
            </Field>
            <Field label="Date">
              <Month value={x.date} onChange={(v) => set((d) => void (d[section][i].date = v))} />
            </Field>
          </ItemCard>
        ))}
        <button
          className="btn ghost sm"
          type="button"
          onClick={() =>
            set((d) => {
              if (section === "training") d.training.push({ ...base(), name: "", provider: "", date: "", details: "" });
              else d.certifications.push({ ...base(), name: "", issuer: "", date: "", expiry: "" });
            })
          }
        >
          + Add
        </button>
      </>
    );
  } else if (section === "achievements") {
    body = (
      <Field label="Achievements (one per line)" full>
        <textarea
          rows={4}
          defaultValue={data.achievements.map((a) => a.text).join("\n")}
          onChange={(e) =>
            set((d) => {
              const old = d.achievements;
              d.achievements = linesOf(e.target.value).map((t, i) => ({ ...(old[i] ?? base()), text: t }));
            })
          }
        />
      </Field>
    );
  } else if (section === "references") {
    body = (
      <>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={data.references_on_request}
            onChange={(e) => set((d) => void (d.references_on_request = e.target.checked))}
          />
          Write &quot;References available on request&quot;
        </label>
        {!data.references_on_request
          ? data.references.map((x, i) => (
              <ItemCard key={x.id} data={data} list="references" index={i} setData={setData}>
                <Field label="Name">
                  <input value={x.name} onChange={(e) => set((d) => void (d.references[i].name = e.target.value))} />
                </Field>
                <Field label="Job title">
                  <input value={x.title} onChange={(e) => set((d) => void (d.references[i].title = e.target.value))} />
                </Field>
                <Field label="Organisation">
                  <input value={x.organisation} onChange={(e) => set((d) => void (d.references[i].organisation = e.target.value))} />
                </Field>
                <Field label="Email or phone">
                  <input value={x.contact} onChange={(e) => set((d) => void (d.references[i].contact = e.target.value))} />
                </Field>
              </ItemCard>
            ))
          : null}
        {!data.references_on_request ? (
          <button
            className="btn ghost sm"
            type="button"
            onClick={() => set((d) => d.references.push({ ...base(), name: "", title: "", organisation: "", contact: "" }))}
          >
            + Add a referee
          </button>
        ) : null}
      </>
    );
  }

  return (
    <div>
      {body}
      <div className="cr" style={{ marginTop: 12 }}>
        <button
          className="btn sm"
          type="button"
          disabled={busy}
          onClick={() => {
            const d = copy(data);
            d.experience.forEach((x) => (x.bullets = x.bullets.map((b) => b.trim()).filter(Boolean)));
            void onSave(d);
          }}
        >
          Save
        </button>
        {onCancel ? (
          <button className="btn ghost sm" type="button" onClick={onCancel}>
            Cancel
          </button>
        ) : null}
      </div>
    </div>
  );
}

// A short read-only line per section for the Step 5 overview.
export function sectionSummary(section: EditableSection, d: CvData): string {
  switch (section) {
    case "personal":
      return [d.personal.full_name, d.personal.email, d.personal.phone, [d.personal.city, d.personal.country].filter(Boolean).join(", ")]
        .filter(Boolean)
        .join(" · ") || "Not filled in yet";
    case "summary":
      return d.professional_summary || "Written by the AI in the next steps";
    case "experience":
      return d.experience.map((x) => [x.job_title, x.employer].filter(Boolean).join(" at ")).join(" · ") || "None yet";
    case "education":
      return d.education.map((x) => [x.degree, x.institution].filter(Boolean).join(", ")).join(" · ") || "None yet";
    case "skills":
      return [...d.skills.technical, ...d.skills.soft].join(", ") || "None yet";
    case "languages":
      return d.languages.map((l) => [l.language, l.level].filter(Boolean).join(" ")).join(" · ") || "None yet";
    case "certifications":
      return d.certifications.map((c) => c.name).join(" · ") || "None";
    case "training":
      return d.training.map((c) => c.name).join(" · ") || "None";
    case "achievements":
      return d.achievements.map((a) => a.text).join(" · ") || "None";
    case "references":
      return d.references_on_request ? "Available on request" : d.references.map((r) => r.name).join(" · ") || "None";
  }
}

export function sectionNeedsConfirm(section: EditableSection, d: CvData): boolean {
  if (section === "personal") return d.personal.confirm_fields.length > 0;
  if (section === "summary" || section === "skills") return false;
  return (d[section] as CvItemBase[]).some((i) => i.confirm);
}
