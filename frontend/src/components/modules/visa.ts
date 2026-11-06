import { COUNTRY_FLAGS, getVisaProgram, matchVisaPrograms, VISA_TYPE_LABELS, VISA_TYPES, type VisaProgram, type VisaType } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ModuleConfig } from "./types";

const flag = (country: string) => (COUNTRY_FLAGS[country] ? COUNTRY_FLAGS[country] + " " : "") + country;

const ANY_TYPE = "Any visa type";
// The form shows labels; the backend takes the visa type key.
const TYPE_OPTIONS = [ANY_TYPE, ...VISA_TYPES.map((t) => VISA_TYPE_LABELS[t])] as const;
const PASSPORT = ["Valid passport", "No passport yet"] as const;
const REFUSED = ["No", "Yes"] as const;

function typeKey(label: unknown): VisaType | "any" {
  const hit = VISA_TYPES.find((t) => VISA_TYPE_LABELS[t] === label);
  return hit ?? "any";
}

// Immigration Processing (spec B19): the same pattern as Student Consultancy and Job Processing.
// Field keys are the backend answer keys, so the form answers become the application answers.
export const visaConfig: ModuleConfig = {
  module: "visa",
  accent: "#E11D48",
  base: "/immigration",
  agent: {
    title: "Meet your Immigration Agent",
    subtitle: "Tell the agent where you want to go and which visa you need. It shows the visa programmes we process for you.",
    fields: [
      { key: "country", label: "Destination country", optionsFrom: "visa_countries" },
      { key: "visa_type", label: "Visa type", options: TYPE_OPTIONS },
      { key: "passport_ready", label: "Passport", options: PASSPORT, asBoolean: PASSPORT[0] },
      { key: "refused_before", label: "Refused a visa before?", options: REFUSED, asBoolean: REFUSED[1] },
    ],
    button: "Find my visa programme",
    chatPlaceholder: "Ask about documents, fees, processing time…",
    name: "Immigration Agent",
    icon: "🌍",
    resultsHeading: (n) => n + (n === 1 ? " visa programme" : " visa programmes") + " for your trip",
    noMatch: "We do not list that country and visa type yet. Try another option, or",
    nothingOpen: "Visa programmes are being added. Please check back soon, or talk to an advisor.",
  },
  match: async (inputs) =>
    (
      await matchVisaPrograms({
        country: String(inputs.country ?? ""),
        visa_type: typeKey(inputs.visa_type),
        passport_ready: inputs.passport_ready === true,
        refused_before: inputs.refused_before === true,
      })
    ).map((m) => ({
      id: m.item.slug,
      name: m.item.title,
      country: m.item.country,
      place: m.item.visa_type_label,
      percent: m.match_percent,
      checks: m.checks,
    })),
  loadItem: async (slug) => {
    const p = await getVisaProgram(slug);
    return {
      id: p.slug,
      name: p.title,
      country: p.country,
      place: p.visa_type_label,
      tag: flag(p.country) + " · " + p.visa_type_label,
      lead: p.description || p.visa_type_label + " for " + p.country + ". We prepare and follow your file up to the decision.",
      facts: [
        ["Visa type", p.visa_type_label],
        ["Processing time", p.processing_time || "–"],
        ["Validity", p.validity || "–"],
        ["Government fee", p.government_fee || "–"],
        ["Our processing fee", formatMoney(p.fee_poisha)],
      ],
      conditions: [...p.eligibility, ...p.required_documents.map((d) => "Document: " + d), p.conditions].filter(Boolean),
      fee_poisha: p.fee_poisha,
      success_rate: p.success_rate,
    };
  },
  describe: (item) => {
    const p = item as VisaProgram;
    return { name: p.title, country: p.country, place: p.visa_type_label };
  },
  item: {
    crumb: "← Back to matches",
    agentAnchor: "v-agent",
    roadColumns: 4,
    notFoundLink: "Find visa programmes",
  },
  apply: {
    authNote: "Create your Immigration Processing account to apply, then sign in to continue.",
    lockedBefore: "Pay the one-time processing fee of ",
    lockedAfter: " to start your file. Once the payment succeeds, your advisor checks your eligibility and you follow every stage here.",
    payButtonSuffix: " to start processing",
    paidText: "Your file is with our team. Upload your documents below; your advisor updates your stages, biometrics or interview and the decision here.",
    hasLink: false,
    linkButton: "",
    noLink: "",
    noApplications: "No applications yet.",
    findLabel: "Find visa programmes",
  },
};
