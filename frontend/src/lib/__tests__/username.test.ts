import { describe, expect, it } from "vitest";
import { checkUsername } from "../username";

describe("checkUsername", () => {
  it("accepts the same usernames as the server", () => {
    for (const ok of ["rahim", "rahim_uddin", "Rahim.2026", "abc", "  rahim  ", "a".repeat(30)]) {
      expect(checkUsername(ok)).toEqual({ problem: null, suggestion: null });
    }
  });

  it("says nothing while the box is empty", () => {
    expect(checkUsername("   ").problem).toBeNull();
  });

  it("explains spaces and suggests a fixed username", () => {
    expect(checkUsername("Rahim Uddin")).toEqual({
      problem: "A username cannot have spaces. Use _ or . instead.",
      suggestion: "rahim_uddin",
    });
  });

  it("explains an email typed as a username", () => {
    const r = checkUsername("rahim@gmail.com");
    expect(r.problem).toContain("not an email");
    expect(r.suggestion).toBe("rahim");
  });

  it("names the characters that cannot be used", () => {
    expect(checkUsername("rahim-uddin!").problem).toBe('"-" "!" cannot be used. Use only English letters, numbers, . or _.');
    expect(checkUsername("rahim-uddin").suggestion).toBe("rahim_uddin");
    expect(checkUsername("রহিম").suggestion).toBeNull();
  });

  it("explains the length", () => {
    expect(checkUsername("ab").problem).toBe("A username needs at least 3 characters.");
    expect(checkUsername("a".repeat(31)).problem).toBe("A username can have at most 30 characters.");
    expect(checkUsername("a".repeat(31)).suggestion).toBe("a".repeat(30));
  });
});
