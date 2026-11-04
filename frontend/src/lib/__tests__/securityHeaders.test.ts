import { describe, expect, it } from "vitest";
import nextConfig, { securityHeaders } from "../../../next.config";

// g05 (part): the headers next.config sends on every path. The built app is checked with curl.
describe("security headers", () => {
  it("applies to every path", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toEqual([{ source: "/:path*", headers: securityHeaders }]);
  });

  it("lists every header from the spec", () => {
    const byKey = Object.fromEntries(securityHeaders.map((h) => [h.key, h.value]));
    expect(byKey["X-Frame-Options"]).toBe("DENY");
    expect(byKey["X-Content-Type-Options"]).toBe("nosniff");
    expect(byKey["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(byKey["Permissions-Policy"]).toBe("camera=(), microphone=(), geolocation=()");
    const csp = byKey["Content-Security-Policy"];
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("img-src 'self' data:");
  });

  it("sends Strict-Transport-Security only in production", () => {
    const hsts = securityHeaders.some((h) => h.key === "Strict-Transport-Security");
    expect(hsts).toBe(process.env.NODE_ENV === "production");
  });
});
