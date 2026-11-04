import type { AgentInputs, AppModule, CatalogOptions, MatchCheck, University, Vacancy, VisaProgram } from "@/lib/api";
import type { Accent } from "../PageShell";

// One input of the agent form (fld() in the reference): a select when options are given, else a number.
export type AgentField = {
  key: string;
  label: string;
  options?: readonly string[];
  // Choices from what the agency offers now (GET /catalog/options), instead of fixed options.
  optionsFrom?: keyof CatalogOptions;
  // A yes/no select: the answer is true when this option is chosen.
  asBoolean?: string;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  required?: boolean;
  // Used when the box is left empty and the field is not required.
  empty?: number | null;
};

// The AgentWidget texts and form (CFG in the reference).
export type AgentConfig = {
  title: string;
  subtitle: string;
  fields: AgentField[];
  button: string;
  chatPlaceholder: string;
  name: string; // chat card heading, e.g. "Study Advisor Agent"
  icon: string;
  resultsHeading: (count: number) => string;
  noMatch: string;
  // Shown when a choice list is empty (nothing published yet).
  nothingOpen: string;
};

// A match as the widget and the item page show it.
export type MatchView = {
  id: string;
  name: string;
  country: string;
  place: string;
  percent: number;
  checks: MatchCheck[];
};

// What the item page shows about one item.
export type ItemInfo = {
  id: string;
  name: string;
  country: string;
  place: string;
  tag: string;
  lead: string;
  facts: [label: string, value: string][];
  conditions: string[];
  fee_poisha: number;
};

// Everything module-specific that AgentWidget, ItemPage and ApplicationPage need.
export type ModuleConfig = {
  module: AppModule;
  accent: Accent;
  base: string; // e.g. "/consultancy"
  agent: AgentConfig;
  match: (inputs: AgentInputs) => Promise<MatchView[]>;
  loadItem: (id: string) => Promise<ItemInfo>;
  describe: (item: University | Vacancy | VisaProgram) => { name: string; country: string; place: string };
  item: {
    crumb: string; // "← Back to matches"
    agentAnchor: string; // the agent section id
    roadColumns: number;
    notFoundLink: string;
  };
  apply: {
    authNote: string;
    lockedBefore: string; // text before the fee in the Next step card
    lockedAfter: string; // text after the fee
    payButtonSuffix: string; // "to unlock link"
    paidText: string;
    hasLink: boolean;
    linkButton: string;
    noLink: string;
    noApplications: string;
    findLabel: string;
  };
};
