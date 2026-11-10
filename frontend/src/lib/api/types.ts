// Data types and fixed value lists, matching the FastAPI backend (spec B10).
// Pages import these only through src/lib/api/index.ts.

// ---------- Fixed value lists ----------

export const MODULES = ["course", "study", "job", "visa", "remote"] as const;
export type Module = (typeof MODULES)[number];

// Modules that have applications (courses use enrolments instead).
export const APP_MODULES = ["study", "job", "visa", "remote"] as const;
export type AppModule = (typeof APP_MODULES)[number];

export const MODULE_NAMES: Record<Module, string> = {
  course: "Training",
  study: "Student Consultancy",
  job: "Job Processing",
  visa: "Immigration Processing",
  remote: "Remote Jobs",
};

export const ADMIN_ROLES = ["super_admin", "admin", "finance"] as const;
export type AdminRole = (typeof ADMIN_ROLES)[number];

export const APP_STATUSES = ["active", "on_hold", "rejected", "withdrawn", "completed"] as const;
export type AppStatus = (typeof APP_STATUSES)[number];

export const STUDY_STAGES = [
  "Application started",
  "Documents submitted",
  "University review",
  "Offer letter received",
  "Tuition deposit & confirmation",
  "Visa application",
  "Visa interview / biometrics",
  "Visa decision",
  "Ready to fly ✈",
] as const;
export type StudyStage = (typeof STUDY_STAGES)[number];

// Copied from the reference JT list (it has 8 stages, index 0-7).
export const JOB_STAGES = [
  "Application started",
  "Profile screening",
  "Employer interview",
  "Job offer & contract",
  "Medical & police clearance",
  "Work permit & visa",
  "Flight booked",
  "Ready to fly ✈",
] as const;
export type JobStage = (typeof JOB_STAGES)[number];

// B19: Immigration Processing (8 stages, index 0-7), same as the backend.
export const VISA_STAGES = [
  "Application started",
  "Eligibility review",
  "Documents checked",
  "File prepared",
  "Visa application lodged",
  "Biometrics / interview",
  "Visa decision",
  "Ready to travel ✈",
] as const;
export type VisaStage = (typeof VISA_STAGES)[number];

// Remote Jobs (6 stages, index 0-5), same as the backend: no visa, medical or flight steps.
export const REMOTE_STAGES = [
  "Application started",
  "Profile screening",
  "Skills test / interview",
  "Job offer & contract",
  "Onboarding",
  "Started work ✓",
] as const;
export type RemoteStage = (typeof REMOTE_STAGES)[number];

// The stage names of a module (ST and JT in the reference). Use these instead of a fixed number.
export function stagesOf(module: AppModule): readonly string[] {
  if (module === "visa") return VISA_STAGES;
  if (module === "remote") return REMOTE_STAGES;
  return module === "study" ? STUDY_STAGES : JOB_STAGES;
}

export function stageCount(module: AppModule): number {
  return stagesOf(module).length;
}

// Required documents per module, copied from the reference DOCS lists.
export const DOCUMENT_TYPES: Record<AppModule, readonly string[]> = {
  study: [
    "Academic transcripts and certificates",
    "Valid passport",
    "IELTS (or equivalent) score report",
    "Statement of purpose",
    "Two recommendation letters",
    "CV",
    "Proof of funds",
  ],
  job: [
    "Valid passport (18+ months)",
    "Education and experience certificates",
    "Updated CV",
    "Medical report",
    "Police clearance",
    "Passport-size photographs",
  ],
  visa: [
    "Valid passport (all pages)",
    "Passport-size photographs",
    "Bank statement and proof of funds",
    "Employment or business documents",
    "Invitation, sponsor or family documents",
    "Previous visas and travel history",
    "Other supporting documents",
  ],
  remote: ["Updated CV", "Education and experience certificates", "National ID or passport", "Portfolio or work samples"],
};

// B19: visa programme types (CHECK list in visa_programs.visa_type).
export const VISA_TYPES = [
  "visit",
  "tourist",
  "business",
  "family",
  "spouse",
  "work",
  "student",
  "permanent_residence",
  "citizenship",
  "transit",
  "medical",
  "other",
] as const;
export type VisaType = (typeof VISA_TYPES)[number];

export const VISA_TYPE_LABELS: Record<VisaType, string> = {
  visit: "Visit visa",
  tourist: "Tourist visa",
  business: "Business visa",
  family: "Family visa",
  spouse: "Spouse / partner visa",
  work: "Work visa",
  student: "Student visa",
  permanent_residence: "Permanent residence",
  citizenship: "Citizenship",
  transit: "Transit visa",
  medical: "Medical visa",
  other: "Other",
};

// Country flags shown next to a country name (FLG in the reference).
export const COUNTRY_FLAGS: Record<string, string> = {
  Canada: "🇨🇦",
  UK: "🇬🇧",
  Australia: "🇦🇺",
  Germany: "🇩🇪",
  Malaysia: "🇲🇾",
  Japan: "🇯🇵",
  USA: "🇺🇸",
  UAE: "🇦🇪",
};

// Nagad is paid inside SSLCommerz.
export const PAYMENT_METHODS = ["sslcommerz", "bkash", "manual"] as const;
export type PaymentMethod = (typeof PAYMENT_METHODS)[number];

export const PAYMENT_STATUSES = [
  "initiated",
  "pending_verify",
  "paid",
  "failed",
  "cancelled",
  "abandoned",
  "rejected",
  "refunded",
  "duplicate",
] as const;
export type PaymentStatus = (typeof PAYMENT_STATUSES)[number];

export const DOC_STATUSES = ["pending", "verified", "rejected", "replaced"] as const;
export type DocStatus = (typeof DOC_STATUSES)[number];

// "expiring" and "expired" are computed from a verified document's expiry, never stored.
export const SHOWN_DOC_STATUSES = ["pending", "verified", "rejected", "replaced", "expiring", "expired"] as const;
export type ShownDocStatus = (typeof SHOWN_DOC_STATUSES)[number];

export const REFUND_STATUSES = ["requested", "approved", "declined"] as const;
export type RefundStatus = (typeof REFUND_STATUSES)[number];

export const ENQUIRY_STATUSES = ["new", "contacted", "converted", "closed"] as const;
export type EnquiryStatus = (typeof ENQUIRY_STATUSES)[number];

export const CHANNELS = ["email", "whatsapp"] as const;
export type Channel = (typeof CHANNELS)[number];

export const NOTIFY_STATUSES = ["queued", "sending", "sent", "failed"] as const;
export type NotifyStatus = (typeof NOTIFY_STATUSES)[number];

export const INTERVIEW_RESULTS = ["pending", "passed", "failed"] as const;
export type InterviewResult = (typeof INTERVIEW_RESULTS)[number];

export const PAYMENT_REF_TYPES = ["enrolment", "application"] as const;
export type PaymentRefType = (typeof PAYMENT_REF_TYPES)[number];

export const LEDGER_DIRECTIONS = ["in", "out"] as const;
export type LedgerDirection = (typeof LEDGER_DIRECTIONS)[number];

// Vacancy.min_education and min_english are indexes into these lists (from the reference).
export const EDUCATION_LEVELS = ["Below SSC", "SSC / HSC", "Diploma", "Bachelor or higher"] as const;
export const ENGLISH_LEVELS = ["Basic", "Good", "Fluent"] as const;
export const PASSPORT_OPTIONS = ["Valid 18+ months", "Valid under 18 months", "No passport yet"] as const;
// Remote Jobs: common remote skills, the same list as the backend (catalog.REMOTE_SKILLS).
export const REMOTE_SKILLS = [
  "Software development",
  "Web development",
  "Mobile app development",
  "UI / UX design",
  "Graphic design",
  "Video editing",
  "Digital marketing",
  "Search engine optimisation (SEO)",
  "Social media management",
  "Content writing",
  "Translation",
  "Data entry",
  "Data analysis",
  "Accounting & bookkeeping",
  "Customer support",
  "Virtual assistant",
  "IT support",
  "Online tutoring",
  "Sales & lead generation",
  "Project management",
] as const;

// Finished journeys of a university, vacancy or visa programme: Completed (success) or Rejected.
// Withdrawn, open and Self Apply cases are not counted. null while none has finished.
export interface SuccessRate {
  percent: number;
  completed: number;
  finished: number;
}

export const ENROLMENT_STATUSES = ["awaiting_payment", "active", "completed", "cancelled"] as const;
export type EnrolmentStatus = (typeof ENROLMENT_STATUSES)[number];

// ---------- Paging ----------

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------- Settings and licence ----------

export interface Stat {
  number: string;
  label: string;
}

// A secret is never sent to the browser: only whether it is saved.
export interface SecretStatus {
  saved: boolean;
  unreadable?: boolean;
}

export interface PublicGateway {
  enabled: boolean;
  sandbox: boolean;
}

export interface ManualGateway {
  enabled: boolean;
  instructions: string;
}

export interface PublicSettings {
  name: string;
  tagline: string;
  brand_color: string;
  logo_url: string | null;
  hero_url: string | null;
  hero_title: string;
  hero_text: string;
  stats: Stat[];
  about_title: string;
  about_text: string;
  address: string;
  phone: string;
  email: string;
  hours: string;
  facebook: string;
  website: string;
  invoice_prefix: string;
  invoice_footer: string;
  vat_bin: string;
  default_fee_poisha: { study: number; job: number; visa: number; remote: number };
  gateways: { sslcommerz: PublicGateway; bkash: PublicGateway; nagad: PublicGateway; manual: ManualGateway };
  mail: { sender_name: string; sender_email: string };
  whatsapp: { number: string };
}

export const SMTP_SECURITY = ["starttls", "ssl", "none"] as const;
export type SmtpSecurity = (typeof SMTP_SECURITY)[number];

// B17: AI providers for the Student Consultancy and Job Processing advisors, in failover order.
export const AI_PROVIDERS = ["claude", "openai", "gemini", "groq"] as const;
export type AiProvider = (typeof AI_PROVIDERS)[number];

export interface AiSettings {
  order: AiProvider[];
  providers: Record<AiProvider, { enabled: boolean; model: string; key: SecretStatus }>;
}

// A key left "" keeps the saved key.
export interface AiSettingsInput {
  order: AiProvider[];
  providers: Record<AiProvider, { enabled: boolean; model: string; key: string }>;
}

// What the super admin sees: secret fields only as SecretStatus.
export interface Settings extends Omit<PublicSettings, "gateways" | "mail" | "whatsapp"> {
  gateways: {
    sslcommerz: PublicGateway & { store_id: SecretStatus; store_password: SecretStatus };
    bkash: PublicGateway & { app_key: SecretStatus; app_secret: SecretStatus; username: SecretStatus; password: SecretStatus };
    nagad: PublicGateway & { merchant_id: SecretStatus; private_key: SecretStatus };
    manual: ManualGateway;
  };
  mail: {
    sender_name: string;
    sender_email: string;
    smtp_host: string;
    smtp_port: number;
    smtp_security: SmtpSecurity;
    smtp_username: string;
    smtp_password: SecretStatus;
  };
  whatsapp: {
    number: string;
    token: SecretStatus;
    phone_number_id: string;
    template_name: string;
    template_language: string;
    api_version: string;
  };
  ai: AiSettings;
}

// What saveSettings sends. A secret left "" keeps the saved value.
export interface SettingsInput extends Omit<PublicSettings, "gateways" | "mail" | "whatsapp" | "logo_url" | "hero_url"> {
  gateways: {
    sslcommerz: PublicGateway & { store_id: string; store_password: string };
    bkash: PublicGateway & { app_key: string; app_secret: string; username: string; password: string };
    nagad: PublicGateway & { merchant_id: string; private_key: string };
    manual: ManualGateway;
  };
  mail: {
    sender_name: string;
    sender_email: string;
    smtp_host: string;
    smtp_port: number;
    smtp_security: SmtpSecurity;
    smtp_username: string;
    smtp_password: string;
  };
  whatsapp: {
    number: string;
    token: string;
    phone_number_id: string;
    template_name: string;
    template_language: string;
    api_version: string;
  };
  // B17: optional; without it the saved AI settings stay as they are.
  ai?: AiSettingsInput;
}

export interface LicenceView {
  holder: string | null;
  modules: Record<Module, boolean>;
  expires_at: string | null;
  active: boolean;
  // Super admin only: the key with its middle hidden.
  key?: string | null;
}

export interface TestResult {
  ok: boolean;
  error?: string;
}

// ---------- People ----------

export interface SetupStatus {
  // Production only: the Super Admin sign-up needs the setup code (B14).
  needs_setup: boolean;
  super_admin_exists: boolean;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: AdminRole;
  approved: boolean;
  active: boolean;
  sections: Module[];
  created_at: string;
}

export interface StaffMember {
  id: string;
  name: string;
}

// id is the public id (CRS-, STU-, JOB- or VIS- and 6 characters). Accounts made before usernames
// have no username and sign in with their email; email is optional for new accounts.
export interface ApplicantAccount {
  id: string;
  module: Module;
  username: string | null;
  name: string;
  email: string | null;
  phone: string;
  country: string;
  education: string;
  email_verified: boolean;
  created_at: string;
}

export interface Session {
  admin: AdminUser | null;
  applicants: Partial<Record<Module, ApplicantAccount>>;
}

export type SignOutTarget = "admin" | Module | "all";

export interface ProfileInput {
  name: string;
  phone: string;
  country: string;
  education: string;
  // Optional; left out = unchanged, "" = remove.
  email?: string;
}

// ---------- Catalog ----------

export interface Course {
  id: string;
  slug: string;
  group_id: string;
  group_name: string;
  title: string;
  icon: string;
  colour: string;
  price_poisha: number;
  duration: string;
  level: string;
  description: string;
  learn_points: string[];
  syllabus: string[];
  // Admin lists only.
  published?: boolean;
  applied_count?: number;
  updated_at?: string;
}

export interface CourseGroup {
  id: string;
  name: string;
  description: string;
  sort_order: number;
  active: boolean;
  course_count?: number;
}

export interface PublicCourseGroup extends CourseGroup {
  courses: Course[];
}

export type CourseGroupInput = Omit<CourseGroup, "id" | "course_count">;

export interface CourseInput {
  group_id: string;
  title: string;
  icon: string;
  colour: string;
  price_poisha: number;
  duration: string;
  level: string;
  description: string;
  learn_points: string[];
  syllabus: string[];
  published: boolean;
}

export interface University {
  id: string;
  slug: string;
  name: string;
  country: string;
  city: string;
  levels: string[];
  fields: string[];
  tuition_usd: number;
  min_gpa: number;
  min_ielts: number;
  intakes: string;
  deadline_text: string;
  scholarships: string;
  work_rights: string;
  conditions: string;
  fee_poisha: number;
  // Self Apply: its own fee set by staff; null while Self Apply is not offered.
  self_apply_fee_poisha: number | null;
  success_rate: SuccessRate | null;
  // Admin lists only (never on the public site).
  apply_link?: string;
  admissions_email?: string;
  fee_override_poisha?: number | null;
  published?: boolean;
  applied_count?: number;
  updated_at?: string;
}

export interface UniversityInput {
  name: string;
  country: string;
  city: string;
  levels: string[];
  fields: string[];
  tuition_usd: number;
  min_gpa: number;
  min_ielts: number;
  intakes: string;
  deadline_text: string;
  scholarships: string;
  work_rights: string;
  conditions: string;
  apply_link: string;
  admissions_email: string;
  fee_override_poisha: number | null;
  self_apply_fee_poisha: number | null;
  published: boolean;
}

export interface Vacancy {
  id: string;
  slug: string;
  title: string;
  employer: string;
  country: string;
  occupation: string;
  min_experience: number;
  min_education: number;
  min_english: number;
  salary_usd: number;
  seats: number | null;
  apply_by: string | null;
  contract: string;
  benefits: string;
  conditions: string;
  employer_verified: boolean;
  // A Remote Jobs role (work from home); false for Job Processing vacancies.
  remote: boolean;
  fee_poisha: number;
  success_rate: SuccessRate | null;
  // Admin lists only.
  employer_licence?: string;
  employer_email?: string;
  closed?: boolean;
  fee_override_poisha?: number | null;
  applied_count?: number;
  past_apply_by?: boolean;
  updated_at?: string;
}

export interface VacancyInput {
  title: string;
  employer: string;
  country: string;
  occupation: string;
  min_experience: number;
  min_education: number;
  min_english: number;
  salary_usd: number;
  seats: number | null;
  apply_by: string | null;
  contract: string;
  benefits: string;
  conditions: string;
  employer_licence: string;
  employer_email: string;
  employer_verified: boolean;
  closed: boolean;
  fee_override_poisha: number | null;
}

export interface VisaProgram {
  id: string;
  slug: string;
  title: string;
  country: string;
  visa_type: VisaType;
  visa_type_label: string;
  processing_time: string;
  validity: string;
  government_fee: string;
  description: string;
  eligibility: string[];
  required_documents: string[];
  conditions: string;
  fee_poisha: number;
  success_rate: SuccessRate | null;
  // Admin lists only (never on the public site).
  official_link?: string;
  embassy_email?: string;
  fee_override_poisha?: number | null;
  published?: boolean;
  applied_count?: number;
  updated_at?: string;
}

export interface VisaProgramInput {
  title: string;
  country: string;
  visa_type: VisaType;
  processing_time: string;
  validity: string;
  government_fee: string;
  description: string;
  eligibility: string[];
  required_documents: string[];
  conditions: string;
  official_link: string;
  embassy_email: string;
  fee_override_poisha: number | null;
  published: boolean;
}

export interface CatalogOptions {
  study_levels: string[];
  study_fields: string[];
  study_countries: string[];
  occupations: string[];
  countries: string[];
  education_levels: string[];
  english_levels: string[];
  visa_countries: string[];
  visa_types: string[];
  // Remote Jobs: skills of open remote roles and the employers' countries.
  remote_occupations: string[];
  remote_countries: string[];
}

export interface FeeItem {
  id: string;
  name: string;
  default_poisha: number;
  override_poisha: number | null;
  effective_poisha: number;
}

export interface FeesView {
  defaults: { study: number; job: number; visa: number; remote: number };
  universities: FeeItem[];
  vacancies: FeeItem[];
  visa_programs: FeeItem[];
  remote_jobs: FeeItem[];
}

// id -> fee in poisha, or null for the default.
export type FeeChanges = Partial<Record<AppModule, Record<string, number | null>>>;

export interface MatchStudyInput {
  level: string;
  field: string;
  gpa: number;
  ielts: number;
  budget_usd: number;
  country: string;
}

export interface MatchJobInput {
  occupation: string;
  country: string;
  experience: number;
  education: string;
  english: string;
  passport_ready: boolean;
  salary_goal_usd: number | null;
}

// Remote Jobs: the job form without passport (the work is done from home).
export interface MatchRemoteInput {
  occupation: string;
  country: string;
  experience: number;
  education: string;
  english: string;
  salary_goal_usd: number | null;
}

// Success Stories (public): made automatically from cases that reached Completed.
export interface SuccessSummary {
  module: AppModule;
  module_label: string;
  completed: number;
  finished: number;
  percent: number | null;
}

export interface SuccessStory {
  id: string;
  name: string; // short name only, e.g. "Rahim K."
  module: AppModule;
  module_label: string;
  title: string;
  detail: string;
  country: string;
  completed_at: string;
}

export interface SuccessStories {
  summary: SuccessSummary[];
  stories: SuccessStory[];
}

export interface MatchVisaInput {
  country: string;
  visa_type: VisaType | "any";
  passport_ready: boolean;
  refused_before: boolean;
}

export interface MatchCheck {
  ok: boolean;
  label: string;
}

export interface MatchResult<T> {
  item: T;
  checks: MatchCheck[];
  match_percent: number;
}

// ---------- Applications and documents ----------

export type Answers = Record<string, string | number | boolean | null>;
export type AgentInputs = Answers;

export interface AppBase {
  id: string;
  ref: string;
  module: AppModule;
  stage: number;
  stage_name: string;
  stage_count: number;
  status: AppStatus;
  fee_paid: boolean;
  // Self Apply (universities): pays the self-apply fee for the official link; not processed by staff.
  self_apply: boolean;
  deadline: string | null;
  created_at: string;
  updated_at: string;
}

export interface MyApplicationSummary extends AppBase {
  item_title: string;
  item_country: string;
  item_slug: string;
  item_employer: string | null;
}

export interface AppEvent {
  id: string;
  at: string;
  by_kind: "applicant" | "admin" | "system";
  by_name: string;
  text: string;
  note: string;
  public: boolean;
}

export interface AppDocument {
  id: string;
  application_id: string;
  type: string;
  original_name: string;
  mime: string;
  size_bytes: number;
  status: DocStatus;
  shown_status: ShownDocStatus;
  expiry: string | null;
  note: string;
  uploaded_at: string;
  reviewed_at: string | null;
  file_url: string;
}

export interface DocumentsPart {
  documents: AppDocument[];
  required_types: string[];
  missing_count: number;
}

export interface InterviewFields {
  interview_at: string | null;
  interview_result: InterviewResult;
  offered_salary_usd: number | null;
}

export interface MyApplication extends AppBase, DocumentsPart, Partial<InterviewFields> {
  item: University | Vacancy | VisaProgram;
  item_title: string;
  stages: string[];
  history: AppEvent[];
  advisor_name: string | null;
  // null once paid.
  fee_poisha: number | null;
  // Study only, after the fee is paid.
  apply_link?: string;
  answers: Answers;
  // When the applicant last submitted the required documents together; null until then.
  documents_submitted_at: string | null;
  // The latest fee payment and its invoice.
  payment: FeePayment | null;
  invoice: Invoice | null;
  // B20: the completion letter, once staff issued it.
  letter: { id: string; issued_at: string; valid: boolean } | null;
}

export interface FeePayment {
  id: string;
  status: PaymentStatus;
  method: PaymentMethod;
  amount_poisha: number;
  manual_ref: string | null;
  note: string;
  created_at: string;
  paid_at: string | null;
}

export interface CaseEmail {
  id: string;
  at: string;
  channel: Channel;
  to: string;
  subject: string;
  status: NotifyStatus;
}

export interface CaseRow extends AppBase, DocumentsPart, InterviewFields {
  stages: string[];
  applicant: { id: string; public_id: string; name: string; email: string | null; phone: string };
  item: { title: string; employer: string | null; country: string; slug: string };
  provider_email: string;
  answers: Answers;
  assigned_to: { id: string; name: string; active: boolean } | null;
  // B16: the partner agent who referred this case; null for a direct case.
  agent: { id: string; name: string; active: boolean } | null;
  // B20: the completion letter, once issued (valid while the case is completed).
  letter: { id: string; issued_at: string; valid: boolean } | null;
  history: AppEvent[];
  emails: CaseEmail[];
  changed?: string[];
}

export interface CaseFilters {
  q?: string;
  status?: AppStatus | "";
  assigned?: string;
  page?: number;
}

export interface CaseChanges {
  assigned_to?: string | null;
  deadline?: string | null;
  interview_at?: string | null;
  interview_result?: InterviewResult;
  offered_salary_usd?: number | null;
}

export interface ApplicantRow {
  id: string;
  public_id: string;
  username: string | null;
  name: string;
  email: string | null;
  phone: string;
  country: string;
  education: string;
  email_verified: boolean;
  created_at: string;
}

export interface DocumentRow extends AppDocument {
  module: AppModule;
  applicant: { name: string; email: string | null };
  application_ref: string;
  item_title: string;
  application_status: AppStatus;
}

export const DOC_FILTERS = ["pending", "expiring", "expired", "rejected", "verified", "all"] as const;
export type DocFilter = (typeof DOC_FILTERS)[number];

// ---------- Money ----------

// sslcommerz / bkash: the browser goes to redirect_url. manual: waits for finance.
export interface PayStart {
  payment_id: string;
  redirect_url?: string;
  status?: "pending_verify";
}

export interface PayInput {
  method: PaymentMethod;
  phone: string;
  manual_ref?: string;
}

export interface PaymentResult {
  id: string;
  status: PaymentStatus;
  method: PaymentMethod;
  module: Module;
  ref_type: PaymentRefType;
  ref_id: string;
  amount_poisha: number;
  purpose: string;
  invoice_no: string | null;
  note: string;
  created_at: string;
  paid_at: string | null;
}

export interface Invoice {
  no: string;
  module: Module;
  name: string;
  email: string;
  description: string;
  method: string;
  amount_poisha: number;
  issued_at: string;
  company: { name: string; address: string; email: string; vat_bin: string; footer: string };
  status: "paid" | "refunded";
  refunded_at: string | null;
  email_status?: NotifyStatus | "none";
  refund_status?: RefundStatus | null;
}

export interface Refund {
  id: string;
  invoice_no: string | null;
  amount_poisha: number;
  reason: string;
  status: RefundStatus;
  decision_note: string;
  refund_method: string;
  refund_ref: string;
  requested_at: string;
  decided_at: string | null;
  // Finance list only.
  name?: string;
  email?: string;
  description?: string;
}

export interface PendingPayment {
  id: string;
  name: string;
  email: string;
  purpose: string;
  module: Module;
  method: PaymentMethod;
  method_label: string;
  manual_ref: string | null;
  gateway_ref: string | null;
  payer_phone: string;
  note: string;
  amount_poisha: number;
  created_at: string;
}

export interface OutstandingItem {
  applicant_id: string;
  name: string;
  email: string;
  phone: string;
  module: Module;
  ref_type: "application" | "enrolment";
  ref_id: string;
  ref: string;
  purpose: string;
  status: "unpaid" | "pending_verify";
  amount_poisha: number;
}

export interface LedgerEntry {
  id: string;
  ref: string;
  date: string;
  at: string;
  direction: LedgerDirection;
  category: string;
  category_label: string;
  party: string;
  email: string;
  description: string;
  method: string;
  amount_poisha: number;
  auto: boolean;
  reversed: boolean;
  reversed_by: string | null;
  reverses_ref: string | null;
  balance_poisha: number;
}

export type LedgerPeriod = "all" | "month";

export interface LedgerSummary {
  balance_all_time_poisha: number;
  in_poisha: number;
  out_poisha: number;
  net_poisha: number;
  by_source: Record<string, number>;
  by_method: Record<string, number>;
  by_expense: Record<string, number>;
  category_labels: Record<string, string>;
}

export interface NewLedgerEntry {
  direction: LedgerDirection;
  category: string;
  date: string;
  amount_poisha: number;
  party: string;
  email: string;
  method: string;
  note: string;
}

// Categories of the ledger (GL and CATS in the reference, plus Opening balance).
export const LEDGER_CATEGORIES: Record<LedgerDirection, readonly { key: string; label: string }[]> = {
  in: [
    { key: "course", label: "Course fees" },
    { key: "study", label: "Student application fees" },
    { key: "job", label: "Job application fees" },
    { key: "visa", label: "Immigration application fees" },
    { key: "remote", label: "Remote job application fees" },
    { key: "otherin", label: "Other income" },
    { key: "opening", label: "Opening balance" },
  ],
  out: [
    { key: "salary", label: "Salaries" },
    { key: "rent", label: "Rent & utilities" },
    { key: "mkt", label: "Marketing" },
    { key: "partner", label: "Paid to universities / employers" },
    { key: "tools", label: "Software & tools" },
    { key: "refund", label: "Refunds" },
    { key: "otherout", label: "Other expenses" },
  ],
};

// Ways money is received or paid in the ledger form (PMS in the reference).
export const LEDGER_METHODS = ["bKash", "Nagad", "Rocket", "Card", "Cash", "Bank transfer"] as const;

// ---------- Courses ----------

export interface Enrolment {
  id: string;
  order_no: string;
  course: { slug: string; title: string; duration: string; level: string; icon: string; colour: string };
  price_poisha: number;
  status: EnrolmentStatus;
  payment_status: PaymentStatus | null;
  method: PaymentMethod | null;
  enrolled_at: string;
  certificate_id: string | null;
  certificate_approved: boolean;
  certificate_approved_at: string | null;
  // Staff list only.
  learner?: { name: string; email: string | null; public_id: string };
}

export interface EnrolResult extends PayStart {
  enrolment: Enrolment;
}

export interface CourseCertificateCheck {
  kind?: undefined;
  valid: true;
  name: string;
  course_title: string;
  duration: string;
  level: string;
  issued_at: string;
}

// B20: a completion letter (LTR-) is valid while its case is completed.
export interface LetterCheck {
  kind: "letter";
  valid: boolean;
  name: string;
  module: AppModule;
  title: string;
  issued_at: string | null;
}

export type CertificateCheck = CourseCertificateCheck | LetterCheck;

// ---------- Certificates, letters and client messages (B20) ----------

export type DocumentKind = "certificate" | "letter";

export interface CertificateView {
  kind: DocumentKind;
  id: string; // CERT- or LTR-
  module: Module;
  holder_name: string;
  account_id: string;
  title: string;
  subtitle: string;
  issued_at: string | null;
  approved: boolean;
  valid: boolean;
}

export interface GroupFilters {
  status?: AppStatus;
  stage?: number;
  item_id?: string;
  has_application?: boolean;
  enrolment_status?: EnrolmentStatus;
}

export interface GroupPreview {
  recipients: number;
  with_email: number;
  with_whatsapp: number;
}

export interface ClientMessage {
  channels: Channel[];
  subject: string;
  body: string;
}

// ---------- Notifications, enquiries, audit ----------

export interface Notification {
  id: string;
  at: string;
  channel: Channel;
  to: string;
  to_name: string;
  module: Module | null;
  event: string;
  subject: string;
  body: string;
  status: NotifyStatus;
  tries: number;
  sent_at: string | null;
  next_attempt_at: string;
  last_error: string;
}

export interface NotificationFilter {
  channel?: Channel | "";
  status?: NotifyStatus | "";
  q?: string;
  page?: number;
}

export interface EnquiryNote {
  id: string;
  at: string;
  by: string;
  text: string;
}

export interface Enquiry {
  id: string;
  name: string;
  contact: string;
  interest: string;
  preferred_date: string | null;
  message: string;
  status: EnquiryStatus;
  assigned_to: { id: string; name: string } | null;
  created_at: string;
  notes: EnquiryNote[];
}

export interface EnquiryForm {
  name: string;
  contact: string;
  interest: string;
  preferred_date: string;
  message: string;
  // Hidden from people; bots fill it in.
  website?: string;
}

export interface EnquiryChanges {
  status?: EnquiryStatus;
  assigned_to?: string | null;
}

export interface AuditEntry {
  id: string;
  at: string;
  by_name: string;
  by_role: string | null;
  action: string;
  detail: string;
  ip: string | null;
}

export interface AuditPage {
  rows: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

// ---------- partner agents and commissions (B16) ----------

export type AgentSection = "study" | "job" | "visa" | "remote";
export const COMMISSION_TYPES = ["fixed", "percent"] as const;
export type CommissionType = (typeof COMMISSION_TYPES)[number];
export const COMMISSION_STATUSES = ["due", "paid", "cancelled"] as const;
export type CommissionStatus = (typeof COMMISSION_STATUSES)[number];

export interface PartnerAgentInput {
  name: string;
  firm: string;
  phone: string;
  email: string;
  country: string;
  address: string;
  sections: AgentSection[];
  commission_type: CommissionType;
  commission_poisha: number;
  // Basis points: 1250 = 12.50 %.
  commission_percent_bp: number;
  notes: string;
  active: boolean;
}

export interface PartnerAgent extends PartnerAgentInput {
  id: string;
  created_at: string;
  referred: number;
  due_poisha: number;
  paid_poisha: number;
}

export interface AgentFilters {
  q?: string;
  section?: AgentSection | "";
  active?: "true" | "false" | "";
}

export interface AgentCommission {
  id: string;
  agent_id: string;
  agent_name: string;
  application_id: string;
  application_ref: string;
  module: AgentSection;
  applicant_name: string;
  amount_poisha: number;
  status: CommissionStatus;
  paid_at: string | null;
  pay_reference: string;
  note: string;
  created_at: string;
}

export interface CommissionFilters {
  agent_id?: string;
  status?: CommissionStatus | "";
  module?: AgentSection | "";
}

// ---------- B2B partners (B18) ----------

export const PARTNER_TYPES = [
  "university",
  "college",
  "employer",
  "recruitment_agency",
  "training_body",
  "exam_board",
  "visa_centre",
  "law_firm",
  "other",
] as const;
export type PartnerType = (typeof PARTNER_TYPES)[number];

// What visitors see: never the contact details or the agreement.
export interface PublicPartner {
  id: string;
  name: string;
  partner_type: PartnerType;
  country: string;
  website: string;
  description: string;
  logo_url: string | null;
}

export interface PartnerInput {
  module: Module;
  partner_type: PartnerType;
  name: string;
  country: string;
  website: string;
  description: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  agreement_ref: string;
  agreement_until: string | null;
  show_on_site: boolean;
  sort_order: number;
  active: boolean;
}

export interface Partner extends PublicPartner, Omit<PartnerInput, keyof PublicPartner> {
  created_at: string;
}

export interface PartnerFilters {
  module?: Module | "";
  q?: string;
  active?: "true" | "false" | "";
}

// ---------- agreements and other documents of agents and partners (B21) ----------

export type DocumentOwnerKind = "agent" | "partner";

export const PARTY_DOC_TYPES = ["agreement", "trade_licence", "id_document", "bank_details", "other"] as const;
export type PartyDocType = (typeof PARTY_DOC_TYPES)[number];

// "expiring" (within 60 days) and "expired" come from valid_until and are never stored.
export type PartyDocShownStatus = "active" | "expiring" | "expired" | "archived";

export interface PartyDocument {
  id: string;
  doc_type: PartyDocType;
  title: string;
  original_name: string;
  mime: string;
  size_bytes: number;
  valid_until: string | null;
  note: string;
  status: "active" | "archived";
  shown_status: PartyDocShownStatus;
  uploaded_at: string;
  uploaded_by_name: string;
  archived_at: string | null;
  archived_by_name: string | null;
  file_url: string;
}

export interface PartyDocumentInput {
  doc_type: PartyDocType;
  title: string;
  valid_until: string | null;
  note: string;
  file: File;
}

// B23: Excel upload of listings.
export const IMPORT_KINDS = ["university", "vacancy", "visa"] as const;
export type ImportKind = (typeof IMPORT_KINDS)[number];

export const IMPORT_KIND_MODULE = { university: "study", vacancy: "job", visa: "visa" } as const satisfies Record<ImportKind, Module>;

export type ImportRowStatus = "new" | "skipped" | "error";

export interface ImportRow {
  row_number: number;
  label: string;
  status: ImportRowStatus;
  message: string;
  warnings: string[];
}

export interface ImportReport {
  kind: ImportKind;
  total: number;
  new_count: number;
  skipped_count: number;
  error_count: number;
  rows: ImportRow[];
}
