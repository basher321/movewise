import { getUniversity, matchUniversities, COUNTRY_FLAGS, type University } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ModuleConfig } from "./types";

const usd = (n: number) => "$" + n.toLocaleString("en-US");
const flag = (country: string) => (COUNTRY_FLAGS[country] ? COUNTRY_FLAGS[country] + " " : "") + country;

// Student Consultancy: texts and data copied from CFG.study, showItem() and showApply() in the reference.
export const studyConfig: ModuleConfig = {
  module: "study",
  accent: "#0EA5A4",
  base: "/consultancy",
  agent: {
    title: "Meet your Study Advisor Agent",
    subtitle: "Share your results and budget. The agent matches you with universities where you can realistically get in.",
    fields: [
      { key: "level", label: "Study level", optionsFrom: "study_levels" },
      { key: "field", label: "Field of study", optionsFrom: "study_fields" },
      { key: "gpa", label: "GPA (4.0 scale)", min: 0, max: 4, step: 0.01, placeholder: "5.0 GPA × 0.8", required: true },
      { key: "ielts", label: "IELTS band (0 if none)", min: 0, max: 9, step: 0.5, placeholder: "e.g. 6.5", empty: 0 },
      { key: "budget_usd", label: "Budget per year (USD)", min: 0, max: 100000, step: 500, placeholder: "e.g. 12000", required: true },
    ],
    button: "Find my universities",
    chatPlaceholder: "Ask about fees, IELTS, scholarships…",
    name: "Study Advisor Agent",
    icon: "🎓",
    resultsHeading: (n) => n + " universities matched to your profile",
    noMatch: "Nothing fits that level or field yet. Try another option, or",
    nothingOpen: "Universities are being added. Please check back soon, or talk to an advisor.",
  },
  match: async (inputs) =>
    (
      await matchUniversities({
        level: String(inputs.level ?? ""),
        field: String(inputs.field ?? ""),
        gpa: Number(inputs.gpa),
        ielts: Number(inputs.ielts ?? 0),
        budget_usd: Number(inputs.budget_usd),
      })
    ).map((m) => ({ id: m.item.slug, name: m.item.name, country: m.item.country, place: m.item.city, percent: m.match_percent, checks: m.checks })),
  loadItem: async (slug) => {
    const u = await getUniversity(slug);
    return {
      id: u.slug,
      name: u.name,
      country: u.country,
      place: u.city,
      tag: flag(u.country) + " · " + u.city,
      lead: u.levels.join(" and ") + " programmes in " + u.fields.join(", ") + ".",
      facts: [
        ["Tuition per year", usd(u.tuition_usd)],
        ["Minimum GPA", u.min_gpa + " / 4.0"],
        ["IELTS", u.min_ielts + " overall"],
        ["Intakes", u.intakes || "–"],
        ["Deadline", u.deadline_text || "–"],
        ["Scholarships", u.scholarships || "–"],
        ["Application fee", formatMoney(u.fee_poisha)],
      ],
      conditions: [
        "Minimum GPA " + u.min_gpa + " on a 4.0 scale",
        "IELTS " + u.min_ielts + " overall",
        "Tuition about " + usd(u.tuition_usd) + " per year",
        u.intakes ? "Intakes: " + u.intakes : "",
        u.deadline_text ? "Application deadline: " + u.deadline_text : "",
        u.work_rights ? "Work rights: " + u.work_rights : "",
        u.conditions,
      ].filter(Boolean),
      fee_poisha: u.fee_poisha,
    };
  },
  describe: (item) => {
    const u = item as University;
    return { name: u.name, country: u.country, place: u.city };
  },
  item: {
    crumb: "← Back to matches",
    agentAnchor: "s-agent",
    roadColumns: 5,
    notFoundLink: "Find universities",
  },
  apply: {
    authNote: "Create your Student Consultancy account to apply, then sign in to continue.",
    lockedBefore: "Pay the one-time application fee of ",
    lockedAfter:
      " to unlock the official application link. Once the payment succeeds, the link appears here and you can apply on the university website.",
    payButtonSuffix: " to unlock link",
    paidText: "Complete the official application on the university website. After you submit, your advisor updates your stages here.",
    hasLink: true,
    linkButton: "Open official application ↗",
    noLink: "Application link coming soon",
    noApplications: "No applications yet.",
    findLabel: "Find universities",
  },
};
