import { describe, expect, it } from "vitest";
import { bpToText, percentToBp, poishaToText, takaToPoisha } from "../amounts";

describe("amounts (B16)", () => {
  it("taka to poisha without floats", () => {
    expect(takaToPoisha("1500")).toBe(150000);
    expect(takaToPoisha("1,500.5")).toBe(150050);
    expect(takaToPoisha(" 0.07 ")).toBe(7);
    expect(takaToPoisha("0.1")).toBe(10);
    for (const bad of ["", "-5", "1.234", "abc", "1e3", "12 000"]) expect(takaToPoisha(bad)).toBeNull();
  });

  it("percent to basis points, at most 100 %", () => {
    expect(percentToBp("12.5")).toBe(1250);
    expect(percentToBp("100")).toBe(10000);
    expect(percentToBp("100.01")).toBeNull();
    expect(percentToBp("-1")).toBeNull();
  });

  it("back to text for the form", () => {
    expect(poishaToText(150050)).toBe("1500.50");
    expect(poishaToText(500000)).toBe("5000");
    expect(bpToText(1250)).toBe("12.5");
    expect(bpToText(1205)).toBe("12.05");
    expect(bpToText(1000)).toBe("10");
  });
});
