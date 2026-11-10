// Formatting helpers. Money ALWAYS arrives from the backend as integer
// minor units (P-07); the UI only formats — it never recomputes totals
// and never converts currencies (P-07 §14: no undocumented conversion).

const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK"]);

export function currencyExponent(currency: string): number {
  return ZERO_DECIMAL.has(currency.toUpperCase()) ? 0 : 2;
}

/** Format integer minor units as a currency string, e.g. 123456 INR → ₹1,234.56 */
export function formatMoney(minor: number | null | undefined, currency = "INR"): string {
  if (minor === null || minor === undefined || Number.isNaN(minor)) return "—";
  const exp = currencyExponent(currency);
  const value = minor / 10 ** exp;
  try {
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
      minimumFractionDigits: exp,
      maximumFractionDigits: exp,
    }).format(value);
  } catch {
    return `${value.toFixed(exp)} ${currency}`;
  }
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-GB").format(n);
}

/** Basis points (P-08/P-09 convention) → percentage string. */
export function formatBps(bps: number | null | undefined): string {
  if (bps === null || bps === undefined) return "—";
  return `${(bps / 100).toFixed(1)}%`;
}

export function formatDateTime(iso: string | null | undefined, timezone = "UTC"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

export function formatTime(iso: string | null | undefined, timezone = "UTC"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "unknown";
  const seconds = Math.max(0, Math.round((now - t) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Map a backend status/severity string to the §4.1 meaning colors. */
export type Tone = "ok" | "warn" | "bad" | "info" | "neutral";

const OK_WORDS = new Set([
  "ok", "healthy", "operational", "ready", "completed",
  "complete", "approved", "verified", "success", "succeeded", "alive",
  "normal", "granted", "open_account", "collected", "paid",
]);
const WARN_WORDS = new Set([
  "warning", "warn", "pending", "awaiting_approval", "awaiting_human",
  "degraded", "operational_with_warnings", "medium", "paused", "waiting",
  "queued", "accepted", "validating", "requires_human_action", "at_risk",
  "investigating", "restricted", "safe_mode",
]);
const BAD_WORDS = new Set([
  "critical", "high", "error", "failed", "failure", "down", "blocked",
  "rejected", "denied", "emergency", "cancelled", "timed_out", "revoked",
  "suspended", "failing",
]);
const INFO_WORDS = new Set([
  "info", "in_progress", "starting", "created", "proposed",
  // §4.1: blue means active — running work and active entities.
  "running", "active",
]);

export function toneFor(status: string | null | undefined): Tone {
  if (!status) return "neutral";
  const s = status.toLowerCase();
  if (OK_WORDS.has(s)) return "ok";
  if (BAD_WORDS.has(s)) return "bad";
  if (WARN_WORDS.has(s)) return "warn";
  if (INFO_WORDS.has(s)) return "info";
  return "neutral";
}

export function humanize(status: string | null | undefined): string {
  if (!status) return "—";
  // Normalise first so ALL-CAPS backend enums read as titles, not shouting.
  return status
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
