import type { NextConfig } from "next";

const production = process.env.NODE_ENV === "production";

// Next.js pages need inline scripts and styles; development also needs eval for fast refresh.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
].join("; ");

export const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ...(production ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  // The browser talks to one origin: /api/* is forwarded to the FastAPI backend, so its
  // session cookies are first-party. Set API_ORIGIN in frontend/.env.local for other hosts.
  async rewrites() {
    const origin = (process.env.API_ORIGIN || "http://localhost:8000").replace(/\/+$/, "");
    return [{ source: "/api/:path*", destination: origin + "/api/:path*" }];
  },
};

export default nextConfig;
