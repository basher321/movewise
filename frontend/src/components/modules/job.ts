import { COUNTRY_FLAGS, EDUCATION_LEVELS, ENGLISH_LEVELS, getVacancy, matchVacancies, PASSPORT_OPTIONS, type Vacancy } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { ModuleConfig } from "./types";

const usd = (n: number) => "$" + n.toLocaleString("en-US");
const flag = (country: string) => (COUNTRY_FLAGS[country] ? COUNTRY_FLAGS[country] + " " : "") + country;

// Job Processing: texts from CFG.job, showItem() and showApply() in the reference.
// Field keys are the backend answer keys (spec B05), so the form answers become the application answers.
export const jobConfig: ModuleConfig = {
  module: "job",
  accent: "#D97706",
  base: "/jobs",
  agent: {
    title: "Meet your Job Processing Agent",
    subtitle: "Tell the agent about your skills and papers. It matches you with verified roles you qualify for.",
    fields: [
      { key: "occupation", label: "Your occupation", optionsFrom: "occupations" },
      { key: "country", label: "Preferred country", optionsFrom: "countries" },
      { key: "experience", label: "Experience (years)", min: 0, max: 40, step: 1, placeholder: "e.g. 3", required: true },
      { key: "education", label: "Education", options: EDUCATION_LEVELS },
      { key: "english", label: "English level", options: ENGLISH_LEVELS },
      { key: "passport_ready", label: "Passport", options: PASSPORT_OPTIONS, asBoolean: PASSPORT_OPTIONS[0] },
      { key: "salary_goal_usd", label: "Expected salary (USD/month)", min: 0, max: 20000, step: 50, placeholder: "optional", empty: null },
    ],
    button: "Find my job match",
    chatPlaceholder: "Ask about salary, documents, process…",
    name: "Job Processing Agent",
    icon: "🛂",
    resultsHeading: (n) => n + (n === 1 ? " role matched" : " roles matched") + " to your profile",
    noMatch: "No open role fits that occupation and country yet. Try another option, or",
    nothingOpen: "Verified jobs are being added. Please check back soon, or talk to an advisor.",
  },
  match: async (inputs) =>
    (
      await matchVacancies({
        occupation: String(inputs.occupation ?? ""),
        country: String(inputs.country ?? ""),
        experience: Number(inputs.experience),
        education: String(inputs.education ?? ""),
        english: String(inputs.english ?? ""),
        passport_ready: inputs.passport_ready === true,
        salary_goal_usd: inputs.salary_goal_usd === null || inputs.salary_goal_usd === undefined || inputs.salary_goal_usd === "" ? null : Number(inputs.salary_goal_usd),
      })
    ).map((m) => ({
      id: m.item.slug,
      name: m.item.title + " · " + m.item.employer,
      country: m.item.country,
      place: m.item.occupation,
      percent: m.match_percent,
      checks: m.checks,
    })),
  loadItem: async (slug) => {
    const v = await getVacancy(slug);
    return {
      id: v.slug,
      name: v.title,
      country: v.country,
      place: v.employer,
      tag: flag(v.country) + " · " + v.employer + (v.employer_verified ? " ✓ verified employer" : ""),
      lead: v.occupation + " role. " + (v.contract || "Written contract before you travel."),
      facts: [
        ["Salary", usd(v.salary_usd) + " per month"],
        ["Experience", v.min_experience + "+ years"],
        ["Education", EDUCATION_LEVELS[v.min_education] ?? "–"],
        ["English", (ENGLISH_LEVELS[v.min_english] ?? "–") + " English"],
        ["Seats", v.seats ? String(v.seats) : "–"],
        ["Apply by", v.apply_by ? formatDate(v.apply_by) : "Open"],
        ["Application fee", formatMoney(v.fee_poisha)],
      ],
      conditions: [
        v.min_experience + "+ years of experience as " + v.occupation.toLowerCase(),
        "Education: " + (EDUCATION_LEVELS[v.min_education] ?? "–") + " or higher",
        "English: " + (ENGLISH_LEVELS[v.min_english] ?? "–") + " or better",
        "Passport valid for 18 months or more",
        v.contract ? "Contract: " + v.contract : "",
        v.benefits ? "Benefits: " + v.benefits : "",
        v.conditions,
      ].filter(Boolean),
      fee_poisha: v.fee_poisha,
    };
  },
  describe: (item) => {
    const v = item as Vacancy;
    return { name: v.title + " · " + v.employer, country: v.country, place: v.occupation };
  },
  item: {
    crumb: "← Back to matches",
    agentAnchor: "j-agent",
    roadColumns: 4,
    notFoundLink: "Find jobs",
  },
  apply: {
    authNote: "Create your Job Processing account to apply, then sign in to continue.",
    lockedBefore: "Pay the one-time processing fee of ",
    lockedAfter: " to start your file. Once the payment succeeds, your advisor starts the employer process and you follow every stage here.",
    payButtonSuffix: " to start processing",
    paidText: "Your file is with our team. Upload your documents below; your advisor updates your stages, interview and offer here.",
    hasLink: false,
    linkButton: "",
    noLink: "",
    noApplications: "No applications yet.",
    findLabel: "Find jobs",
  },
};
