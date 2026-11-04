// Catalog (B04): public lists use slugs; admin lists and saves use ids. There is no delete:
// items are hidden (published off) or closed.

import type {
  AgentInputs,
  AppModule,
  CatalogOptions,
  Course,
  CourseGroup,
  CourseGroupInput,
  CourseInput,
  FeeChanges,
  FeesView,
  MatchJobInput,
  MatchResult,
  MatchStudyInput,
  MatchVisaInput,
  PublicCourseGroup,
  University,
  UniversityInput,
  Vacancy,
  VacancyInput,
  VisaProgram,
  VisaProgramInput,
} from "../types";
import { get, post, put } from "./client";

// ---------- public ----------

export const listCourseGroups = () => get<PublicCourseGroup[]>("/courses");
export const getCourse = (slug: string) => get<Course>("/courses/" + encodeURIComponent(slug));
export const listUniversities = () => get<University[]>("/universities");
export const getUniversity = (slug: string) => get<University>("/universities/" + encodeURIComponent(slug));
export const listVacancies = () => get<Vacancy[]>("/vacancies");
export const getVacancy = (slug: string) => get<Vacancy>("/vacancies/" + encodeURIComponent(slug));
export const listVisaPrograms = () => get<VisaProgram[]>("/visa-programs");
export const getVisaProgram = (slug: string) => get<VisaProgram>("/visa-programs/" + encodeURIComponent(slug));
export const getCatalogOptions = () => get<CatalogOptions>("/catalog/options");

export const matchUniversities = (input: MatchStudyInput) => post<MatchResult<University>[]>("/match/study", input);
export const matchVacancies = (input: MatchJobInput) => post<MatchResult<Vacancy>[]>("/match/job", input);
export const matchVisaPrograms = (input: MatchVisaInput) => post<MatchResult<VisaProgram>[]>("/match/visa", input);

export async function askAgent(module: AppModule, question: string, inputs: AgentInputs | null): Promise<string> {
  return (await post<{ answer: string }>(`/agent/${module}/ask`, { question, inputs })).answer;
}

// The last agent inputs, remembered in this browser only (a convenience, not business data).
const AGENT_KEY = "agency.agent.";

export async function rememberAgentInputs(module: AppModule, inputs: AgentInputs): Promise<void> {
  try {
    window.localStorage.setItem(AGENT_KEY + module, JSON.stringify(inputs));
  } catch {
    // Storage full or blocked: the inputs are simply not remembered.
  }
}

export async function lastAgentInputs(module: AppModule): Promise<AgentInputs | null> {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(AGENT_KEY + module) ?? "null");
    if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
    const ok = Object.values(value).every(
      (x) => x === null || typeof x === "string" || typeof x === "boolean" || (typeof x === "number" && Number.isFinite(x)),
    );
    return ok ? (value as AgentInputs) : null;
  } catch {
    return null;
  }
}

// ---------- admin (super admin, module licensed) ----------

export const listAdminCourseGroups = () => get<CourseGroup[]>("/admin/course-groups");
export const saveCourseGroup = (id: string | null, group: CourseGroupInput) =>
  id ? put<CourseGroup>("/admin/course-groups/" + id, group) : post<CourseGroup>("/admin/course-groups", group);

export const listAdminCourses = () => get<Course[]>("/admin/courses");
export const saveCourse = (id: string | null, course: CourseInput) =>
  id ? put<Course>("/admin/courses/" + id, course) : post<Course>("/admin/courses", course);

export const listAdminUniversities = () => get<University[]>("/admin/universities");
export const saveUniversity = (id: string | null, university: UniversityInput) =>
  id ? put<University>("/admin/universities/" + id, university) : post<University>("/admin/universities", university);

export const listAdminVacancies = () => get<Vacancy[]>("/admin/vacancies");
export const saveVacancy = (id: string | null, vacancy: VacancyInput) =>
  id ? put<Vacancy>("/admin/vacancies/" + id, vacancy) : post<Vacancy>("/admin/vacancies", vacancy);

export const listAdminVisaPrograms = () => get<VisaProgram[]>("/admin/visa-programs");
export const saveVisaProgram = (id: string | null, program: VisaProgramInput) =>
  id ? put<VisaProgram>("/admin/visa-programs/" + id, program) : post<VisaProgram>("/admin/visa-programs", program);

export const getFees = () => get<FeesView>("/admin/fees");
export const saveFees = (changes: FeeChanges) =>
  put<FeesView>("/admin/fees", { study: changes.study ?? {}, job: changes.job ?? {}, visa: changes.visa ?? {} });
export const resetFees = (scope: AppModule | "all") => post<FeesView>("/admin/fees/reset", { scope });
