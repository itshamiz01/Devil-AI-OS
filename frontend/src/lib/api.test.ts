import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, onConnectionChange, setToken } from "./api";

// The real API client against a stubbed fetch: envelope unwrapping,
// error mapping, and the connection signal that drives Scenario 8
// (backend disconnect -> visible stale/connection state).
function envelope(data: unknown, status = 200): Response {
  return new Response(
    JSON.stringify({ success: true, data, error: null, correlation_id: "t-1", meta: null }),
    { status, headers: { "Content-Type": "application/json" } },
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  setToken(null);
});

describe("api client", () => {
  it("unwraps the standard envelope and sends the bearer token", async () => {
    setToken("tok-123");
    const fetchMock = vi.fn(async () => envelope({ value: 42 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await api<{ value: number }>("/dashboard/overview");
    expect(result.data.value).toBe(42);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/dashboard/overview");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });

  it("maps backend error envelopes to ApiError with the backend code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            success: false,
            data: null,
            error: { code: "permission_denied", message: "nope", details: {} },
            correlation_id: "t-2",
            meta: null,
          }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    await expect(api("/security/status")).rejects.toMatchObject({
      name: "ApiError",
      code: "permission_denied",
      status: 403,
    });
  });

  it("reports connection failure distinctly and notifies observers (Scenario 8)", async () => {
    const seen: boolean[] = [];
    const off = onConnectionChange((online) => seen.push(online));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const err = await api("/dashboard/overview").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("connection_failed");
    expect(seen).toContain(false);
    off();
  });
});
