// AI CV Agent (B28): every text of the CV Agent screens in one place, so a Bengali version can be
// added later (spec B28 Decisions 3). The company name always comes from Settings.

import type { CvCategory, CvDocKind, CvSection, CvTemplate, CvType } from "@/lib/api";

export const CV_TEXT = {
  product: "AI CV Agent",
  productLong: "AI CV Agent — Professional CV Builder",
  tagline: "Create an international-standard CV for jobs, education and immigration.",
  how: "Click options, upload your documents and confirm. The AI agent reads them, asks only for what is missing and writes your CV.",
  create: "Create new CV",
  myCvs: "My CVs",
  noCvs: "No CVs yet. Choose a CV type above to start.",
  badges: ["PDF", "DOCX", "Maximum 2 pages", "ATS-friendly"],
  coverToggle: "Also create a cover letter",
  back: "Back",
  next: "Next",
  saved: "Saved",
  signInTitle: "Sign in to build your CV",
  signInText: "Your CVs are kept in your account, so you can leave and come back at any time.",
  honest:
    "The agent never invents qualifications, employers, dates or results. It only uses your documents and your answers. A CV does not guarantee a job, admission or visa.",
} as const;

export const STEP_TITLES = ["CV type", "Country", "Category", "Documents", "Your details", "Template", "Review", "Download"] as const;

export const CV_TYPE_CARDS: { type: CvType; title: string; subtitle: string; icon: string }[] = [
  { type: "new", title: "New CV", subtitle: "Build from scratch", icon: "📝" },
  { type: "update", title: "Update CV", subtitle: "Improve existing CV", icon: "🔄" },
  { type: "overseas", title: "Overseas Jobs", subtitle: "International recruitment", icon: "✈️" },
  { type: "immigration", title: "Immigration CV", subtitle: "Skilled migration", icon: "🛂" },
  { type: "student", title: "Student CV", subtitle: "Study applications", icon: "🎓" },
  { type: "graduate", title: "Fresh Graduate CV", subtitle: "First job after studies", icon: "🌱" },
  { type: "professional", title: "Professional CV", subtitle: "Experienced candidates", icon: "💼" },
  { type: "academic", title: "Academic CV", subtitle: "Research and teaching", icon: "🔬" },
  { type: "europass", title: "Europass CV", subtitle: "European format", icon: "🇪🇺" },
];

export const CATEGORY_LABELS: Record<CvCategory, string> = {
  skilled_worker: "🛠️ Skilled Worker",
  it: "💻 IT Professional",
  healthcare: "🩺 Healthcare",
  engineering: "⚙️ Engineering",
  construction: "🏗️ Construction",
  hospitality: "🏨 Hospitality",
  agriculture: "🌾 Agriculture",
  manufacturing: "🏭 Manufacturing",
  driving: "🚚 Driving",
  administration: "🗂️ Administration",
  business: "📈 Business",
  finance: "💰 Finance",
  education: "📚 Education",
  research: "🔬 Research",
  student_admission: "🎓 Student Admission",
  general: "👔 General Employment",
};

export const CV_FLAGS: Record<string, string> = {
  Canada: "🇨🇦",
  USA: "🇺🇸",
  UK: "🇬🇧",
  Australia: "🇦🇺",
  "New Zealand": "🇳🇿",
  Germany: "🇩🇪",
  France: "🇫🇷",
  Italy: "🇮🇹",
  Sweden: "🇸🇪",
  Switzerland: "🇨🇭",
  Finland: "🇫🇮",
  Netherlands: "🇳🇱",
  Denmark: "🇩🇰",
  Ireland: "🇮🇪",
  Malaysia: "🇲🇾",
  Singapore: "🇸🇬",
  Japan: "🇯🇵",
  "South Korea": "🇰🇷",
};

export const DOC_KIND_LABELS: Record<CvDocKind, string> = {
  cv: "Existing CV",
  academic: "Academic certificates",
  experience: "Experience letters",
  training: "Training certificates",
  licence: "Professional licences",
  language: "Language test (IELTS/TOEFL etc.)",
  passport: "Passport (optional)",
  other: "Other document",
};

export const TEMPLATE_LABELS: Record<CvTemplate, { name: string; text: string }> = {
  modern: { name: "Modern Professional", text: "Clean headings with a blue accent." },
  corporate: { name: "Corporate", text: "Centred name, formal and classic." },
  minimalist: { name: "Minimalist", text: "Plain, light and very easy to read." },
  technical: { name: "Technical", text: "Skills first, for IT and engineering." },
  academic: { name: "Academic", text: "Serif type, education first." },
  europass: { name: "Europass", text: "Official European structure." },
  international: { name: "International Recruitment", text: "Formal, with the personal details agencies ask for." },
};

export const SECTION_LABELS: Record<CvSection, string> = {
  summary: "Professional summary",
  experience: "Work experience",
  education: "Education",
  skills: "Skills",
  languages: "Languages",
  certifications: "Certifications and licences",
  training: "Training",
  achievements: "Achievements",
  references: "References",
  custom: "Other sections",
};

export const SENSITIVE_LABELS = {
  nationality: "Nationality",
  date_of_birth: "Date of birth",
  gender: "Gender",
  marital_status: "Marital status",
  religion: "Religion",
} as const;
