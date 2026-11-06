import type { LicenceView, Module } from "@/lib/api";

export type InterestOption = { value: Module | "other"; label: string };

// "Interested in" choices in the order of the reference contact form, for licensed modules only, then Other.
const INTERESTS: { value: Module; label: string }[] = [
  { value: "study", label: "Study abroad" },
  { value: "job", label: "Job abroad" },
  { value: "visa", label: "Visa / immigration" },
  { value: "remote", label: "Remote jobs" },
  { value: "course", label: "Course enrolment" },
];

export function interestOptions(licence: LicenceView | null): InterestOption[] {
  return [...INTERESTS.filter((o) => !!licence?.modules[o.value]), { value: "other", label: "Other" }];
}

export function interestLabel(value: string): string {
  return INTERESTS.find((o) => o.value === value)?.label ?? (value === "other" ? "Other" : value);
}
