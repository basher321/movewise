// The one place that talks to the backend. Requests go to /api/... on this site; next.config.ts
// forwards them to the FastAPI backend (API_ORIGIN), so cookies stay first-party.
// Every {"code","message"} answer becomes an ApiError with the same code and status; no answer
// at all becomes the NETWORK error "Cannot reach the server. Please try again."

import { ApiError, ERROR_STATUS, NETWORK_MESSAGE, type ErrorCode } from "../errors";

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  form?: FormData;
}

function url(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return "/api" + path + (qs ? "?" + qs : "");
}

function isCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && value in ERROR_STATUS;
}

async function toError(response: Response): Promise<ApiError> {
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // Not JSON (for example a proxy error page).
  }
  if (data && typeof data === "object" && "code" in data && "message" in data) {
    const { code, message } = data as { code: unknown; message: unknown };
    if (isCode(code)) return new ApiError(code, String(message), undefined, response.status);
  }
  if (response.status >= 500) return new ApiError("INTERNAL", "Something went wrong. Please try again.", undefined, response.status);
  if (response.status === 404) return new ApiError("NOT_FOUND", "Not found.");
  return new ApiError("VALIDATION", "The request was not accepted.", undefined, response.status);
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form; // the browser sets the multipart boundary
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(url(path, options.query), { method, headers, body, credentials: "include", cache: "no-store" });
  } catch {
    throw new ApiError("NETWORK", NETWORK_MESSAGE);
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const get = <T>(path: string, query?: Query) => request<T>("GET", path, { query });
export const post = <T>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} });
export const put = <T>(path: string, body: unknown) => request<T>("PUT", path, { body });
export const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, { body });

// A link the browser can open directly (files, CSV export).
export function apiUrl(path: string, query?: Query): string {
  return url(path, query);
}
