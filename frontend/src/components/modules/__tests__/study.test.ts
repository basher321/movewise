import { describe, expect, it } from "vitest";
import { criteriaGroup } from "../criteria";
import type { MatchView } from "../types";

function match(met: number): MatchView {
  const checks = Array.from({ length: 5 }, (_, i) => ({ ok: i < met, label: "c" + i }));
  return { id: "x", name: "X", country: "Malaysia", place: "KL", percent: 50, checks };
}

describe("study results headings", () => {
  it.each([
    [5, "All criteria match"],
    [4, "Most criteria match"],
    [3, "Most criteria match"],
    [2, "Two criteria match"],
    [1, "One criterion matches"],
  ])("%i of 5 criteria goes under %s", (met, title) => {
    expect(criteriaGroup(match(met))).toBe(title);
  });
});
