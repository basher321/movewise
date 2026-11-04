// f02: the http layer turns backend answers into ApiError with the same code and status.

import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, NETWORK_MESSAGE } from "../errors";
import { request } from "../http/client";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("http client", () => {
  it("returns the JSON body on success and sends cookies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("GET", "/settings/public", { query: { a: "1", b: "" } })).resolves.toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/settings/public?a=1");
    expect(init.credentials).toBe("include");
  });

  it('turns {"code":"CONFLICT"} into ApiError CONFLICT 409', async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answer(409, { code: "CONFLICT", message: "Already done." })));
    const error = await request("POST", "/admin/payments/x/verify").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("CONFLICT");
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("Already done.");
  });

  it("keeps MODULE_NOT_LICENSED with its 403 status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(answer(403, { code: "MODULE_NOT_LICENSED", message: "Not licensed." })));
    const error = (await request("GET", "/courses").catch((e: unknown) => e)) as ApiError;
    expect([error.code, error.status]).toEqual(["MODULE_NOT_LICENSED", 403]);
  });

  it("turns a network failure into the Cannot reach the server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = (await request("GET", "/settings/public").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("NETWORK");
    expect(error.message).toBe(NETWORK_MESSAGE);
    expect(NETWORK_MESSAGE).toBe("Cannot reach the server. Please try again.");
  });

  it("turns a non-JSON server error into INTERNAL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })));
    const error = (await request("GET", "/settings/public").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("INTERNAL");
  });

  it("sends a JSON body with its content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(answer(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await request("POST", "/enquiries", { body: { name: "A" } });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"name":"A"}');
  });
});
