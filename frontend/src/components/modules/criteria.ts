import type { MatchView } from "./types";

// The results heading for a university or remote role, from how many of the criteria it meets.
export function criteriaGroup(match: MatchView): string {
  const met = match.checks.filter((c) => c.ok).length;
  if (met === match.checks.length) return "All criteria match";
  if (met >= 3) return "Most criteria match";
  return met === 2 ? "Two criteria match" : "One criterion matches";
}
