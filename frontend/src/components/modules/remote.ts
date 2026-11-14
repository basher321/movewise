import { COUNTRY_FLAGS, EDUCATION_LEVELS, ENGLISH_LEVELS, getRemoteJob, matchRemoteJobs, type Vacancy } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { criteriaGroup } from "./criteria";
import type { ModuleConfig } from "./types";

const usd = (n: number) => "$" + n.toLocaleString("en-US");
const flag = (country: string) => (COUNTRY_FLAGS[country] ? COUNTRY_FLAGS[country] + " " : "") + country;

// Remote Jobs: the Job Processing pattern for roles done from home. There is no visa, medical or
// flight: search, match, pay, processing, then the offer and completion letter.
// Field keys are the backend answer keys, so the form answers become the application answers.
export const remoteConfig: ModuleConfig = {
  module: "remote",
  accent: "#059669",
  base: "/remote-jobs",
  agent: {
    title: "Meet your Remote Jobs Agent",
    subtitle: "Tell the agent about your skills. It matches you with verified remote roles you can do from home.",
    fields: [
      { key: "occupation", label: "Your skill or role", optionsFrom: "remote_occupations" },
      { key: "country", label: "Employer country", optionsFrom: "remote_countries" },
      { key: "experience", label: "Experience (years)", min: 0, max: 40, step: 1, placeholder: "e.g. 3", required: true },
      { key: "education", label: "Education", options: EDUCATION_LEVELS },
      { key: "english", label: "English level", options: ENGLISH_LEVELS },
      { key: "salary_goal_usd", label: "Expected salary (USD/month)", min: 0, max: 20000, step: 50, placeholder: "optional", empty: null },
    ],
    button: "Find my remote job",
    chatPlaceholder: "Ask about salary, hours, process…",
    name: "Remote Jobs Agent",
    icon: "💻",
    resultsHeading: (n) => n + (n === 1 ? " remote role matched" : " remote roles matched") + " to your skills",
    noMatch: "Nothing fits your details yet. Try changing them, or",
    nothingOpen: "Verified remote roles are being added. Please check back soon, or talk to an advisor.",
    // B25: roles meeting some of the criteria are shown too, grouped like the study results.
    group: criteriaGroup,
  },
  match: async (inputs) =>
    (
      await matchRemoteJobs({
        occupation: String(inputs.occupation ?? ""),
        country: String(inputs.country ?? ""),
        experience: Number(inputs.experience),
        education: String(inputs.education ?? ""),
        english: String(inputs.english ?? ""),
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
    const v = await getRemoteJob(slug);
    return {
      id: v.slug,
      name: v.title,
      country: v.country,
      place: v.employer,
      tag: "💻 Remote · " + flag(v.country) + " · " + v.employer + (v.employer_verified ? " ✓ verified employer" : ""),
      lead: v.occupation + " role, done from home. No visa or travel. " + (v.contract || "Written contract before you start."),
      facts: [
        ["Salary", usd(v.salary_usd) + " per month"],
        ["Work type", "Remote (work from home)"],
        ["Experience", v.min_experience + "+ years"],
        ["Education", EDUCATION_LEVELS[v.min_education] ?? "–"],
        ["English", (ENGLISH_LEVELS[v.min_english] ?? "–") + " English"],
        ["Seats", v.seats ? String(v.seats) : "–"],
        ["Apply by", v.apply_by ? formatDate(v.apply_by) : "Open"],
        ["Application fee", formatMoney(v.fee_poisha)],
      ],
      conditions: [
        v.min_experience + "+ years of experience in " + v.occupation.toLowerCase(),
        "Education: " + (EDUCATION_LEVELS[v.min_education] ?? "–") + " or higher",
        "English: " + (ENGLISH_LEVELS[v.min_english] ?? "–") + " or better",
        "A computer and a reliable internet connection",
        v.contract ? "Contract: " + v.contract : "",
        v.benefits ? "Benefits: " + v.benefits : "",
        v.conditions,
      ].filter(Boolean),
      fee_poisha: v.fee_poisha,
      success_rate: v.success_rate,
    };
  },
  describe: (item) => {
    const v = item as Vacancy;
    return { name: v.title + " · " + v.employer, country: v.country, place: v.occupation };
  },
  item: {
    crumb: "← Back to matches",
    agentAnchor: "r-agent",
    roadColumns: 3,
    notFoundLink: "Find remote jobs",
  },
  apply: {
    authNote: "Create your Remote Jobs account to apply, then sign in to continue.",
    lockedBefore: "Pay the one-time processing fee of ",
    lockedAfter: " to start your file. Once the payment succeeds, your advisor starts the employer process and you follow every stage here.",
    payButtonSuffix: " to start processing",
    paidText: "Your file is with our team. Upload your documents below; your advisor updates your stages, interview, offer and start date here.",
    hasLink: false,
    linkButton: "",
    noLink: "",
    noApplications: "No applications yet.",
    findLabel: "Find remote jobs",
  },
};
