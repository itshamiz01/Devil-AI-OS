import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";

export interface LoadState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  /** Timestamp (ms) of the last successful load — drives freshness UI. */
  updatedAt: number | null;
  reload: () => void;
}

/**
 * Fetch-on-mount + manual reload, with cancellation. When `pollMs` is set,
 * polling runs ONLY while the document is visible (§27: never poll
 * inactive views) and stops on unmount.
 */
export function useApi<T>(path: string | null, pollMs?: number): LoadState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);
  const pathRef = useRef(path);
  pathRef.current = path;

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    api<T>(path, { signal: controller.signal })
      .then((result) => {
        if (cancelled) return;
        setData(result.data);
        setError(null);
        setUpdatedAt(Date.now());
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === "request_aborted") return;
        setError(err instanceof ApiError ? err : new ApiError(0, { code: "unknown", message: String(err) }));
        setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path, nonce]);

  useEffect(() => {
    if (!pollMs || path === null) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, path, reload]);

  return { data, error, loading, updatedAt, reload };
}

/** Responsive breakpoint hook (§23): bands mirror the design tokens. */
export type Breakpoint = "mobile" | "tablet" | "desktop-sm" | "desktop" | "wide";

export function breakpointForWidth(width: number): Breakpoint {
  if (width < 720) return "mobile";
  if (width < 1100) return "tablet";
  if (width < 1440) return "desktop-sm";
  if (width < 1920) return "desktop";
  return "wide";
}

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(() => breakpointForWidth(window.innerWidth));
  useEffect(() => {
    const onResize = () => setBp(breakpointForWidth(window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return bp;
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

/** Debounced value (§27: search input debounce). */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
