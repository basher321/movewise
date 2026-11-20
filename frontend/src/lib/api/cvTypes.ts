// AI CV Agent (B28): the shapes the backend sends and accepts.

import type { Module } from "./types";

export const CV_TYPES = ["new", "update", "overseas", "immigration", "student", "graduate", "professional", "academic", "europass"] as const;
export type CvType = (typeof CV_TYPES)[number];
export const CV_CATEGORIES = [
  "skilled_worker",
  "it",
  "healthcare",
  "engineering",
  "construction",
  "hospitality",
  "agriculture",
  "manufacturing",
  "driving",
  "administration",
  "business",
  "finance",
  "education",
  "research",
  "student_admission",
  "general",
] as const;
export type CvCategory = (typeof CV_CATEGORIES)[number];
export const CV_DOC_KINDS = ["cv", "academic", "experience", "training", "licence", "language", "passport", "other"] as const;
export type CvDocKind = (typeof CV_DOC_KINDS)[number];
export const CV_TEMPLATES = ["modern", "corporate", "minimalist", "technical", "academic", "europass", "international"] as const;
export type CvTemplate = (typeof CV_TEMPLATES)[number];
export type CvStatus = "draft" | "approved" | "deleted";
export type CvExtraction = "waiting" | "reading" | "done" | "failed" | "unsupported";

export interface CvFile {
  id: string;
  file_name: string;
  doc_kind: CvDocKind;
  mime: string;
  size_bytes: number;
  extraction_status: CvExtraction;
  removed: boolean;
  delete_after: string;
  created_at: string;
}

export interface CvProject {
  id: string;
  module: Module;
  title: string;
  cv_type: CvType | null;
  cover_letter: boolean;
  country: string | null;
  category: CvCategory | null;
  job_advert_text: string;
  doc_kinds: CvDocKind[];
  consent: boolean;
  template: CvTemplate | null;
  page_length: 1 | 2;
  step: number;
  status: CvStatus;
  created_at: string;
  updated_at: string;
  files?: CvFile[];
}

export interface CvProjectChanges {
  title?: string;
  cv_type?: CvType | null;
  cover_letter?: boolean;
  country?: string | null;
  category?: CvCategory | null;
  job_advert_text?: string;
  doc_kinds?: CvDocKind[];
  template?: CvTemplate | null;
  page_length?: 1 | 2;
  step?: number;
}

export interface CvOptions {
  cv_types: CvType[];
  categories: CvCategory[];
  featured_countries: string[];
  countries: string[];
  doc_kinds: CvDocKind[];
  templates: CvTemplate[];
  max_files: number;
  max_file_mb: number;
  consent_text: string;
}

export interface CvItemBase {
  id: string;
  source_file: string;
  confidence: "high" | "medium" | "low";
  confirm: boolean;
  note: string;
}
export interface CvExperience extends CvItemBase {
  job_title: string;
  employer: string;
  location: string;
  start_date: string;
  end_date: string;
  current: boolean;
  bullets: string[];
}
export interface CvEducation extends CvItemBase {
  degree: string;
  field: string;
  institution: string;
  location: string;
  start_date: string;
  end_date: string;
  grade: string;
  details: string[];
}
export interface CvLanguage extends CvItemBase {
  language: string;
  level: string;
  test_score: string;
}
export interface CvCertification extends CvItemBase {
  name: string;
  issuer: string;
  date: string;
  expiry: string;
}
export interface CvTraining extends CvItemBase {
  name: string;
  provider: string;
  date: string;
  details: string;
}
export interface CvAchievement extends CvItemBase {
  text: string;
}
export interface CvReference extends CvItemBase {
  name: string;
  title: string;
  organisation: string;
  contact: string;
}
export type CvSensitive = "nationality" | "date_of_birth" | "gender" | "marital_status" | "religion";
export interface CvPersonal {
  full_name: string;
  email: string;
  phone: string;
  city: string;
  country: string;
  linkedin: string;
  website: string;
  nationality: string;
  date_of_birth: string;
  gender: string;
  marital_status: string;
  religion: string;
  show: CvSensitive[];
  sources: Record<string, string>;
  confirm_fields: string[];
}
export interface CvData {
  personal: CvPersonal;
  professional_summary: string;
  experience: CvExperience[];
  education: CvEducation[];
  skills: { technical: string[]; soft: string[] };
  languages: CvLanguage[];
  certifications: CvCertification[];
  training: CvTraining[];
  achievements: CvAchievement[];
  references: CvReference[];
  references_on_request: boolean;
  custom_sections: { id: string; title: string; items: string[] }[];
  hidden_sections: string[];
}

export type CvFieldKind = "text" | "email" | "tel" | "month" | "select" | "chips" | "boolean" | "url";
export interface CvMissingField {
  key: string;
  label: string;
  kind: CvFieldKind;
  section: string;
  required: boolean;
  options: string[];
  value: unknown;
  hint: string;
}

export interface CvState {
  project: CvProject;
  data: CvData;
  version: number;
  written: boolean;
  can_undo: boolean;
  missing: CvMissingField[];
  confirm: string[];
  ask_for: string[];
  rules: {
    country: string;
    document_name: string;
    spelling: "en-US" | "en-GB";
    notes: string;
    page_length_default: 1 | 2;
    photo: "never" | "optional" | "common";
    allows: CvSensitive[];
  };
  recommended_template: CvTemplate;
  template: CvTemplate;
  letter: { body: string; version: number } | null;
}

export interface CvIssue {
  severity: "blocking" | "warning";
  section: string;
  message: string;
  item_id: string;
}

export type CvSection =
  | "summary"
  | "experience"
  | "education"
  | "skills"
  | "languages"
  | "certifications"
  | "training"
  | "achievements"
  | "references"
  | "custom";
export type CvSectionAction = "regenerate" | "shorter" | "stronger" | "remove" | "restore";
