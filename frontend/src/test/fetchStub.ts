import { vi } from "vitest";

/**
 * Path-prefix fetch stub for component/view tests. Handlers receive the
 * request and return the `data` payload of the standard envelope (or
 * throw / return an HttpError marker for error envelopes). Unmatched
 * paths get the fallback payload — tests assert on what they stubbed.
 */
export class HttpError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Handler = (url: string, init: RequestInit) => unknown;

export function installFetchStub(handlers: Record<string, Handler>, fallback: unknown = {}) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const key = Object.keys(handlers).find((prefix) => url.includes(prefix));
    try {
      const data = key ? await handlers[key](url, init) : fallback;
      return new Response(
        JSON.stringify({ success: true, data, error: null, correlation_id: "test", meta: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    } catch (err) {
      if (err instanceof HttpError) {
        return new Response(
          JSON.stringify({
            success: false,
            data: null,
            error: { code: err.code, message: err.message, details: {} },
            correlation_id: "test",
            meta: null,
          }),
          { status: err.status, headers: { "Content-Type": "application/json" } },
        );
      }
      throw err;
    }
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export function signIn() {
  localStorage.setItem("autonomus.token", "test-token");
}
