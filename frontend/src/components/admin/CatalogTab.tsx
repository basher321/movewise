"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  COUNTRY_FLAGS,
  EDUCATION_LEVELS,
  ENGLISH_LEVELS,
  listAdminCourseGroups,
  listAdminCourses,
  listAdminUniversities,
  listAdminVacancies,
  listAdminVisaPrograms,
  saveCourse,
  saveCourseGroup,
  saveUniversity,
  saveVacancy,
  saveVisaProgram,
  VISA_TYPE_LABELS,
  VISA_TYPES,
  type Course,
  type CourseGroup,
  type LicenceView,
  type Module,
  type University,
  type Vacancy,
  type VisaProgram,
  type VisaType,
} from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { errorText } from "../auth/messages";
import AdminTable from "./AdminTable";
import FormDialog, { type FieldSpec, type FormValues } from "./FormDialog";
import TabPage from "./TabPage";
import { handleFailure } from "./failure";
import type { ShowToast } from "./Toast";

type Part = "uni" | "job" | "visa" | "crs";

const PARTS: [Part, string, Module][] = [
  ["uni", "Universities", "study"],
  ["job", "Employers & vacancies", "job"],
  ["visa", "Visa programmes", "visa"],
  ["crs", "Courses", "course"],
];

// UF and JF in the reference (without the application fee, which is set in the Fees tab).
const UF: FieldSpec[] = [
  { k: "name", l: "University name", req: true, full: true },
  { k: "country", l: "Country", req: true },
  { k: "city", l: "City" },
  { k: "levels", l: "Levels (comma separated)", req: true, ph: "Bachelor, Master" },
  { k: "fields", l: "Fields (comma separated)", req: true, full: true, ph: "Computer Science, Business" },
  { k: "tuition", l: "Tuition per year (USD)", t: "number", req: true },
  { k: "gpa", l: "Minimum GPA (4.0)", t: "number", step: "0.01", req: true },
  { k: "ielts", l: "Minimum IELTS (0 if not needed)", t: "number", step: "0.5", req: true },
  { k: "intakes", l: "Intakes", ph: "September, January" },
  { k: "deadline", l: "Deadline (text)", ph: "1 March" },
  { k: "scholarships", l: "Scholarships", full: true },
  { k: "work", l: "Work rights", full: true },
  { k: "conditions", l: "Other conditions", full: true },
  { k: "link", l: "Official application link (shown to the applicant after paying)", full: true, ph: "https://…" },
  { k: "email", l: "Admissions email (for case emails, never shown on the website)", t: "email", full: true },
  { k: "hidden", l: "Hide from website", t: "check" },
];

const JF: FieldSpec[] = [
  { k: "title", l: "Job title", req: true },
  { k: "employer", l: "Employer", req: true },
  { k: "country", l: "Country", req: true },
  { k: "occupation", l: "Occupation", req: true, ph: "e.g. Construction, Healthcare" },
  { k: "exp", l: "Minimum experience (years)", t: "number", req: true },
  { k: "edu", l: "Minimum education", t: "select", o: EDUCATION_LEVELS.map((x, i) => [String(i), x]) },
  { k: "en", l: "Minimum English", t: "select", o: ENGLISH_LEVELS.map((x, i) => [String(i), x]) },
  { k: "salary", l: "Salary (USD/month)", t: "number", req: true },
  { k: "seats", l: "Seats", t: "number" },
  { k: "applyBy", l: "Apply by", t: "date" },
  { k: "contract", l: "Contract", ph: "e.g. 2-year contract" },
  { k: "benefits", l: "Benefits", full: true },
  { k: "conditions", l: "Other conditions", full: true },
  { k: "licence", l: "Employer licence / registration no." },
  { k: "email", l: "Employer HR email (never shown on the website)", t: "email" },
  { k: "verified", l: "Employer verified (only verified employers appear on the website)", t: "check" },
  { k: "closed", l: "Vacancy closed", t: "check" },
];

// B19: visa programmes (Immigration Processing). The processing fee is set in the Fees tab.
const VF: FieldSpec[] = [
  { k: "title", l: "Programme name", req: true, full: true, ph: "e.g. Visitor Visa, Spouse Visa, Subclass 189 PR" },
  { k: "country", l: "Country", req: true },
  { k: "type", l: "Visa type", t: "select", o: VISA_TYPES.map((t): [string, string] => [t, VISA_TYPE_LABELS[t]]) },
  { k: "time", l: "Processing time", ph: "e.g. 4 to 8 weeks" },
  { k: "validity", l: "Validity / stay", ph: "e.g. Up to 6 months per visit" },
  { k: "govFee", l: "Government fee (text)", ph: "e.g. CAD 100" },
  { k: "description", l: "Short description", t: "area", full: true },
  { k: "eligibility", l: "Eligibility (one per line)", t: "area", full: true, req: true },
  { k: "docs", l: "Required documents (one per line)", t: "area", full: true, req: true },
  { k: "conditions", l: "Other conditions", full: true },
  { k: "link", l: "Official link (for staff, never shown on the website)", full: true, ph: "https://…" },
  { k: "email", l: "Embassy / visa office email (for case emails, never shown on the website)", t: "email", full: true },
  { k: "hidden", l: "Hide from website", t: "check" },
];

const GF: FieldSpec[] = [
  { k: "name", l: "Group name", req: true, full: true, ph: "e.g. Artificial Intelligence" },
  { k: "description", l: "Short description", full: true, ph: "e.g. Practical tracks for builders and analysts." },
  { k: "order", l: "Order on the page (1 = first)", t: "number" },
  { k: "hidden", l: "Hide this group from the website", t: "check" },
];

function courseFields(groups: CourseGroup[]): FieldSpec[] {
  return [
    { k: "group", l: "Course group", t: "select", o: groups.map((g) => [g.id, g.name + (g.active ? "" : " (hidden)")]), full: true },
    { k: "title", l: "Course title", req: true, full: true },
    { k: "icon", l: "Icon (one emoji)", ph: "🤖" },
    { k: "colour", l: "Colour", ph: "#4F46E5", req: true },
    { k: "price", l: "Price (৳)", t: "number", req: true },
    { k: "duration", l: "Duration", ph: "e.g. 12 weeks" },
    { k: "level", l: "Level", ph: "e.g. Beginner" },
    { k: "description", l: "Short description", t: "area", full: true },
    { k: "learn", l: "What you will learn (one per line)", t: "area", full: true, req: true },
    { k: "syllabus", l: "Syllabus modules (one per line)", t: "area", full: true, req: true },
    { k: "hidden", l: "Hide from website", t: "check" },
  ];
}

const flag = (country: string) => (COUNTRY_FLAGS[country] ?? "🌐") + " " + country;
const str = (v: string | boolean | undefined) => String(v ?? "").trim();
const list = (v: string | boolean | undefined) => str(v).split(",").map((s) => s.trim()).filter(Boolean);
const lines = (v: string | boolean | undefined) => str(v).split("\n").map((s) => s.trim()).filter(Boolean);
const badge = (text: string, cls: string) => <span className={cls}>{text}</span>;

// A whole number from a form box, or a friendly VALIDATION error.
function whole(v: string | boolean | undefined, label: string, min = 0): number {
  const text = str(v);
  if (!/^\d+$/.test(text) || Number(text) < min) throw new ApiError("VALIDATION", label + " must be a whole number" + (min > 0 ? " above 0." : "."));
  return Number(text);
}

function decimal(v: string | boolean | undefined, label: string): number {
  const text = str(v);
  if (!/^\d+(\.\d+)?$/.test(text)) throw new ApiError("VALIDATION", label + " must be a number.");
  return Number(text);
}

type Editing =
  | { part: "uni"; item: University | null }
  | { part: "job"; item: Vacancy | null }
  | { part: "visa"; item: VisaProgram | null }
  | { part: "grp"; item: CourseGroup | null }
  | { part: "crs"; item: Course | null };

type Props = { licence: LicenceView; toast: ShowToast; onSignedOut: () => void };

// The Catalog tab (aCat() in the reference): what applicants see on the website and in the agents' matching.
export default function CatalogTab({ licence, toast, onSignedOut }: Props) {
  const parts = PARTS.filter(([, , m]) => licence.modules[m]);
  const [part, setPart] = useState<Part | null>(parts[0]?.[0] ?? null);
  const shown = parts.some(([p]) => p === part) ? part : (parts[0]?.[0] ?? null);
  const [unis, setUnis] = useState<University[] | null>(null);
  const [jobs, setJobs] = useState<Vacancy[] | null>(null);
  const [visas, setVisas] = useState<VisaProgram[] | null>(null);
  const [groups, setGroups] = useState<CourseGroup[] | null>(null);
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      if (shown === "uni") setUnis(await listAdminUniversities());
      if (shown === "job") setJobs(await listAdminVacancies());
      if (shown === "visa") setVisas(await listAdminVisaPrograms());
      if (shown === "crs") {
        const [g, c] = await Promise.all([listAdminCourseGroups(), listAdminCourses()]);
        setGroups(g);
        setCourses(c);
      }
      setError("");
    } catch (err) {
      handleFailure(err, () => setError(errorText(err)), onSignedOut);
    }
  }, [shown, onSignedOut]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <div className="banner no">{error}</div>;

  function saved(message: string) {
    setEditing(null);
    toast(message);
    void load();
  }

  const actions =
    shown === "uni" || shown === "job" || shown === "visa" ? (
      <button className="btn sm" type="button" onClick={() => setEditing({ part: shown, item: null })}>
        + Add {shown === "uni" ? "university" : shown === "visa" ? "visa programme" : "vacancy"}
      </button>
    ) : shown === "crs" ? (
      <>
        <button className="btn ghost sm" type="button" onClick={() => setEditing({ part: "grp", item: null })}>
          + Add group
        </button>{" "}
        <button className="btn sm" type="button" disabled={!groups?.length} onClick={() => setEditing({ part: "crs", item: null })}>
          + Add course
        </button>
      </>
    ) : null;

  return (
    <TabPage title="Catalog" sub="What applicants see on the website and in the AI agents' matching. Nothing is deleted: hide or close it instead." actions={actions}>
      <div
        className="seg"
        style={{ maxWidth: parts.length * 190, gridTemplateColumns: "repeat(auto-fit,minmax(min(170px,100%),1fr))", marginBottom: 20, borderRadius: 22 }}
      >
        {parts.map(([p, label]) => (
          <button key={p} type="button" role="tab" aria-selected={shown === p} onClick={() => setPart(p)}>
            {label}
          </button>
        ))}
      </div>
      {shown === "crs" && groups ? (
        <div className="card" style={{ marginBottom: 18 }}>
          <h3>Course groups</h3>
          <p className="sub" style={{ marginTop: 0 }}>
            The headings on the Courses page, in this order. Add a group first, then its courses.
          </p>
          <AdminTable
            rows={groups}
            rowKey={(g) => g.id}
            empty="No groups yet. Add the first one with “+ Add group”."
            columns={[
              {
                head: "Group",
                cell: (g) => (
                  <>
                    <b>{g.name}</b>
                    <small>{g.description}</small>
                  </>
                ),
              },
              { head: "Order", cell: (g) => g.sort_order },
              { head: "Courses", cell: (g) => g.course_count ?? 0 },
              { head: "Website", cell: (g) => (g.active ? badge("Shown", "bd ok") : badge("Hidden", "bd")) },
              { head: "", right: true, cell: (g) => <EditButton onClick={() => setEditing({ part: "grp", item: g })} /> },
            ]}
          />
        </div>
      ) : null}
      <div className="card">
        {shown === "uni" && unis ? (
          <AdminTable
            rows={unis}
            rowKey={(u) => u.id}
            empty="No universities yet. Add the first one with “+ Add university”."
            columns={[
              {
                head: "University",
                cell: (u) => (
                  <>
                    <b>{u.name}</b>
                    <small>
                      {flag(u.country)}
                      {u.city ? " · " + u.city : ""}
                    </small>
                  </>
                ),
              },
              {
                head: "Needs",
                cell: (u) => (
                  <>
                    GPA {u.min_gpa} · IELTS {u.min_ielts}
                    <small>{u.levels.join(", ")}</small>
                  </>
                ),
              },
              { head: "Tuition", cell: (u) => "$" + u.tuition_usd.toLocaleString("en-US") },
              { head: "Applied", cell: (u) => u.applied_count ?? 0 },
              { head: "Website", cell: (u) => (u.published ? badge("Published", "bd ok") : badge("Hidden", "bd")) },
              { head: "", right: true, cell: (u) => <EditButton onClick={() => setEditing({ part: "uni", item: u })} /> },
            ]}
          />
        ) : null}
        {shown === "job" && jobs ? (
          <AdminTable
            rows={jobs}
            rowKey={(j) => j.id}
            empty="No vacancies yet. Add the first one with “+ Add vacancy”."
            columns={[
              {
                head: "Job",
                cell: (j) => (
                  <>
                    <b>{j.title}</b>
                    <small>
                      {j.employer} · {flag(j.country)}
                    </small>
                  </>
                ),
              },
              {
                head: "Needs",
                cell: (j) => (
                  <>
                    {j.min_experience}+ yrs · {EDUCATION_LEVELS[j.min_education]}
                    <small>{ENGLISH_LEVELS[j.min_english]} English</small>
                  </>
                ),
              },
              { head: "Salary", cell: (j) => "$" + j.salary_usd.toLocaleString("en-US") },
              { head: "Applied / seats", cell: (j) => (j.applied_count ?? 0) + " / " + (j.seats ?? "–") },
              {
                head: "Website",
                cell: (j) =>
                  j.closed ? (
                    badge("Closed", "bd")
                  ) : !j.employer_verified ? (
                    badge("Employer not verified", "bd warn")
                  ) : (
                    <>
                      {badge("Live", "bd ok")}
                      {j.past_apply_by ? <small>Past apply-by date</small> : null}
                    </>
                  ),
              },
              { head: "", right: true, cell: (j) => <EditButton onClick={() => setEditing({ part: "job", item: j })} /> },
            ]}
          />
        ) : null}
        {shown === "visa" && visas ? (
          <AdminTable
            rows={visas}
            rowKey={(p) => p.id}
            empty="No visa programmes yet. Add the first one with “+ Add visa programme”."
            columns={[
              {
                head: "Programme",
                cell: (p) => (
                  <>
                    <b>{p.title}</b>
                    <small>{flag(p.country)}</small>
                  </>
                ),
              },
              {
                head: "Type",
                cell: (p) => (
                  <>
                    {p.visa_type_label}
                    <small>{p.processing_time}</small>
                  </>
                ),
              },
              { head: "Fee", cell: (p) => formatMoney(p.fee_poisha) },
              { head: "Applied", cell: (p) => p.applied_count ?? 0 },
              { head: "Website", cell: (p) => (p.published ? badge("Published", "bd ok") : badge("Hidden", "bd")) },
              { head: "", right: true, cell: (p) => <EditButton onClick={() => setEditing({ part: "visa", item: p })} /> },
            ]}
          />
        ) : null}
        {shown === "crs" && courses ? (
          <AdminTable
            rows={courses}
            rowKey={(c) => c.id}
            empty={groups?.length ? "No courses yet. Add one with “+ Add course”." : "Add a course group first."}
            columns={[
              {
                head: "Course",
                cell: (c) => (
                  <>
                    <b>
                      {c.icon} {c.title}
                    </b>
                    <small>{c.group_name}</small>
                  </>
                ),
              },
              {
                head: "Duration",
                cell: (c) => (
                  <>
                    {c.duration || "–"}
                    <small>{c.level}</small>
                  </>
                ),
              },
              { head: "Price", cell: (c) => formatMoney(c.price_poisha) },
              { head: "Website", cell: (c) => (c.published ? badge("Published", "bd ok") : badge("Hidden", "bd")) },
              { head: "", right: true, cell: (c) => <EditButton onClick={() => setEditing({ part: "crs", item: c })} /> },
            ]}
          />
        ) : null}
      </div>
      {editing?.part === "uni" ? (
        <FormDialog
          title={editing.item ? "Edit university" : "Add university"}
          fields={UF}
          wide
          initial={universityValues(editing.item)}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const u = editing.item;
            await saveUniversity(u?.id ?? null, {
              name: str(v.name),
              country: str(v.country),
              city: str(v.city),
              levels: list(v.levels),
              fields: list(v.fields),
              tuition_usd: whole(v.tuition, "Tuition"),
              min_gpa: decimal(v.gpa, "Minimum GPA"),
              min_ielts: decimal(v.ielts, "Minimum IELTS"),
              intakes: str(v.intakes),
              deadline_text: str(v.deadline),
              fee_override_poisha: u?.fee_override_poisha ?? null,
              scholarships: str(v.scholarships),
              work_rights: str(v.work),
              conditions: str(v.conditions),
              apply_link: str(v.link),
              admissions_email: str(v.email),
              published: v.hidden !== true,
            });
            saved(u ? "University saved." : "University added.");
          }}
        />
      ) : null}
      {editing?.part === "job" ? (
        <FormDialog
          title={editing.item ? "Edit vacancy" : "Add vacancy"}
          fields={JF}
          wide
          initial={vacancyValues(editing.item)}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const j = editing.item;
            await saveVacancy(j?.id ?? null, {
              title: str(v.title),
              employer: str(v.employer),
              country: str(v.country),
              occupation: str(v.occupation),
              min_experience: whole(v.exp, "Minimum experience"),
              min_education: Number(v.edu),
              min_english: Number(v.en),
              salary_usd: whole(v.salary, "Salary", 1),
              seats: str(v.seats) === "" ? null : whole(v.seats, "Seats", 1),
              apply_by: str(v.applyBy) || null,
              fee_override_poisha: j?.fee_override_poisha ?? null,
              contract: str(v.contract),
              benefits: str(v.benefits),
              conditions: str(v.conditions),
              employer_licence: str(v.licence),
              employer_email: str(v.email),
              employer_verified: v.verified === true,
              closed: v.closed === true,
            });
            saved(j ? "Vacancy saved." : "Vacancy added.");
          }}
        />
      ) : null}
      {editing?.part === "visa" ? (
        <FormDialog
          title={editing.item ? "Edit visa programme" : "Add visa programme"}
          fields={VF}
          wide
          initial={visaValues(editing.item)}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const p = editing.item;
            await saveVisaProgram(p?.id ?? null, {
              title: str(v.title),
              country: str(v.country),
              visa_type: str(v.type) as VisaType,
              processing_time: str(v.time),
              validity: str(v.validity),
              government_fee: str(v.govFee),
              description: str(v.description),
              eligibility: lines(v.eligibility),
              required_documents: lines(v.docs),
              conditions: str(v.conditions),
              official_link: str(v.link),
              embassy_email: str(v.email),
              fee_override_poisha: p?.fee_override_poisha ?? null,
              published: v.hidden !== true,
            });
            saved(p ? "Visa programme saved." : "Visa programme added.");
          }}
        />
      ) : null}
      {editing?.part === "grp" ? (
        <FormDialog
          title={editing.item ? "Edit course group" : "Add course group"}
          fields={GF}
          initial={
            editing.item
              ? { name: editing.item.name, description: editing.item.description, order: String(editing.item.sort_order), hidden: !editing.item.active }
              : { order: String((groups?.length ?? 0) + 1), hidden: false }
          }
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const g = editing.item;
            await saveCourseGroup(g?.id ?? null, {
              name: str(v.name),
              description: str(v.description),
              sort_order: str(v.order) === "" ? 0 : whole(v.order, "Order"),
              active: v.hidden !== true,
            });
            saved(g ? "Group saved." : "Group added.");
          }}
        />
      ) : null}
      {editing?.part === "crs" && groups ? (
        <FormDialog
          title={editing.item ? "Edit course" : "Add course"}
          fields={courseFields(groups)}
          wide
          initial={courseValues(editing.item, groups)}
          onClose={() => setEditing(null)}
          onSignedOut={onSignedOut}
          onSave={async (v) => {
            const c = editing.item;
            // Whole taka only, converted with whole numbers (never a float for money).
            const taka = whole(v.price, "Price", 1);
            await saveCourse(c?.id ?? null, {
              group_id: str(v.group),
              title: str(v.title),
              icon: str(v.icon),
              colour: str(v.colour),
              price_poisha: taka * 100,
              duration: str(v.duration),
              level: str(v.level),
              description: str(v.description),
              learn_points: lines(v.learn),
              syllabus: lines(v.syllabus),
              published: v.hidden !== true,
            });
            saved(c ? "Course saved." : "Course added.");
          }}
        />
      ) : null}
    </TabPage>
  );
}

function EditButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="lk" type="button" onClick={onClick}>
      Edit
    </button>
  );
}

function universityValues(u: University | null): FormValues {
  if (!u) return { levels: "Bachelor, Master", ielts: "0" };
  return {
    name: u.name,
    country: u.country,
    city: u.city,
    levels: u.levels.join(", "),
    fields: u.fields.join(", "),
    tuition: String(u.tuition_usd),
    gpa: String(u.min_gpa),
    ielts: String(u.min_ielts),
    intakes: u.intakes,
    deadline: u.deadline_text,
    scholarships: u.scholarships,
    work: u.work_rights,
    conditions: u.conditions,
    link: u.apply_link ?? "",
    email: u.admissions_email ?? "",
    hidden: u.published === false,
  };
}

// A new vacancy starts as in the reference: employer not verified until checked, education 1,
// English 0, experience 0, 1 seat.
function vacancyValues(j: Vacancy | null): FormValues {
  if (!j) return { exp: "0", edu: "1", en: "0", seats: "1", verified: false, closed: false };
  return {
    title: j.title,
    employer: j.employer,
    country: j.country,
    occupation: j.occupation,
    exp: String(j.min_experience),
    edu: String(j.min_education),
    en: String(j.min_english),
    salary: String(j.salary_usd),
    seats: j.seats ? String(j.seats) : "",
    applyBy: j.apply_by ?? "",
    contract: j.contract,
    benefits: j.benefits,
    conditions: j.conditions,
    licence: j.employer_licence ?? "",
    email: j.employer_email ?? "",
    verified: j.employer_verified,
    closed: j.closed === true,
  };
}

function visaValues(p: VisaProgram | null): FormValues {
  if (!p) return { type: "visit", hidden: false };
  return {
    title: p.title,
    country: p.country,
    type: p.visa_type,
    time: p.processing_time,
    validity: p.validity,
    govFee: p.government_fee,
    description: p.description,
    eligibility: p.eligibility.join("\n"),
    docs: p.required_documents.join("\n"),
    conditions: p.conditions,
    link: p.official_link ?? "",
    email: p.embassy_email ?? "",
    hidden: p.published === false,
  };
}

function courseValues(c: Course | null, groups: CourseGroup[]): FormValues {
  if (!c) return { group: groups[0]?.id ?? "", colour: "#4F46E5", hidden: false };
  return {
    group: c.group_id,
    title: c.title,
    icon: c.icon,
    colour: c.colour,
    price: String(c.price_poisha / 100),
    duration: c.duration,
    level: c.level,
    description: c.description,
    learn: c.learn_points.join("\n"),
    syllabus: c.syllabus.join("\n"),
    hidden: c.published === false,
  };
}
