// B27: the custom payment amount is whole taka from 100 to 1,000,000.

import { describe, expect, it } from "vitest";
import { parseCustomAmount } from "../customAmount";

describe("parseCustomAmount", () => {
  it("accepts whole taka with or without commas", () => {
    expect(parseCustomAmount("25000")).toEqual({ poisha: 2_500_000 });
    expect(parseCustomAmount(" 1,00,000 ")).toEqual({ poisha: 10_000_000 });
    expect(parseCustomAmount("100")).toEqual({ poisha: 10_000 });
    expect(parseCustomAmount("1000000")).toEqual({ poisha: 100_000_000 });
  });

  it("refuses poisha, words, empty and out-of-range amounts", () => {
    for (const bad of ["", "  ", "99", "1000001", "250.50", "abc", "-500", "1e5"]) {
      expect(parseCustomAmount(bad)).toHaveProperty("error");
    }
  });
});
