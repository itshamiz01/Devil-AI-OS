// AUTONOMUS API client (§22.1): one place for authentication handling,
// the backend's response envelope, timeouts, cancellation and typed errors.
//
// The backend envelope is {success, data, error, correlation_id, meta}.
// This client unwraps it: callers get `data` (and `meta` for lists), and
// failures arrive as ApiError with the backend's structured code/message.
// A network-level failure (backend unreachable) is reported as
// code "connection_failed" so the UI can show the disconnect state (§22.4,
// Scenario 8) instead of pretending stale data is live.

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }

  get isConnectionFailure(): boolean {
    return this.code === "connection_failed";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface ApiResult<T> {
  data: T;
  meta: PageMeta | null;
  correlationId: string | null;
}

const TOKEN_KEY = "autonomus.token";
const API_BASE = "/api/v1";
const DEFAULT_TIMEOUT_MS = 15000;

// Connection observers let the shell show live/stale state honestly.
type ConnectionListener = (ok: boolean, at: number) => void;
const listeners = new Set<ConnectionListener>();
let lastSuccessAt: number | null = null;
let lastFailureAt: number | null = null;

export function onConnectionChange(fn: ConnectionListener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function connectionSnapshot(): { lastSuccessAt: number | null; lastFailureAt: number | null } {
  return { lastSuccessAt, lastFailureAt };
}

function notify(ok: boolean) {
  const at = Date.now();
  if (ok) lastSuccessAt = at;
  else lastFailureAt = at;
  listeners.forEach((fn) => fn(ok, at));
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable (private mode): session simply won't persist
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  auth?: boolean; // default true
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(new Error("request timed out")),
    opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  if (opts.signal) {
    if (opts.signal.aborted) controller.abort(opts.signal.reason);
    else opts.signal.addEventListener("abort", () => controller.abort(opts.signal?.reason));
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.auth !== false) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: controller.signal,
    });
  } catch (err) {
    window.clearTimeout(timeout);
    notify(false);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, { code: "request_aborted", message: "Request was cancelled or timed out." });
    }
    throw new ApiError(0, {
      code: "connection_failed",
      message: "Cannot reach the AUTONOMUS backend. Data shown may be stale.",
    });
  }
  window.clearTimeout(timeout);
  let payload: {
    success?: boolean;
    data?: T;
    error?: ApiErrorBody | null;
    correlation_id?: string | null;
    meta?: PageMeta | null;
  } = {};
  try {
    payload = (await response.json()) as typeof payload;
  } catch {
    notify(false);
    throw new ApiError(response.status, {
      code: "invalid_response",
      message: `Backend returned a non-JSON response (HTTP ${response.status}).`,
    });
  }
  if (!response.ok || payload.success === false) {
    notify(response.status < 500);
    throw new ApiError(
      response.status,
      payload.error ?? { code: "http_error", message: `HTTP ${response.status}` },
    );
  }
  notify(true);
  return {
    data: payload.data as T,
    meta: payload.meta ?? null,
    correlationId: payload.correlation_id ?? null,
  };
}

/**
 * Raw-body upload (Expansion F03 voice intake): the blob IS the
 * request body and its type the Content-Type — the voice intake
 * endpoint takes raw audio, not JSON. The response is the standard
 * envelope. Added for the Voice view; no existing behaviour changes.
 */
export async function apiUpload<T>(path: string, blob: Blob): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    "Content-Type": blob.type || "application/octet-stream",
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: blob,
    });
  } catch {
    throw new ApiError(0, {
      code: "connection_failed",
      message: "Cannot reach the AUTONOMUS backend.",
    });
  }
  let payload: {
    success?: boolean;
    data?: T;
    error?: ApiErrorBody | null;
    correlation_id?: string | null;
    meta?: PageMeta | null;
  } = {};
  try {
    payload = (await response.json()) as typeof payload;
  } catch {
    throw new ApiError(response.status, {
      code: "invalid_response",
      message: `Backend returned a non-JSON response (HTTP ${response.status}).`,
    });
  }
  if (!response.ok || payload.success === false) {
    throw new ApiError(
      response.status,
      payload.error ?? { code: "http_error", message: `HTTP ${response.status}` },
    );
  }
  return {
    data: payload.data as T,
    meta: payload.meta ?? null,
    correlationId: payload.correlation_id ?? null,
  };
}

/**
 * Binary download (Expansion F03 spoken-response playback): returns
 * the raw blob; the endpoint serves stored audio bytes, not the
 * JSON envelope.
 */
export async function apiBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { headers });
  } catch {
    throw new ApiError(0, {
      code: "connection_failed",
      message: "Cannot reach the AUTONOMUS backend.",
    });
  }
  if (!response.ok) {
    throw new ApiError(response.status, {
      code: "http_error",
      message: `HTTP ${response.status}`,
    });
  }
  return response.blob();
}

export async function login(username: string, password: string): Promise<string> {  const result = await api<{ access_token: string; principal: string }>("/auth/login", {
    method: "POST",
    body: { username, password },
    auth: false,
  });
  setToken(result.data.access_token);
  return result.data.access_token;
}

export function logout(): void {
  setToken(null);
}
