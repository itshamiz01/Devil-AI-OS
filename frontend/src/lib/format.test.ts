import { describe, expect, it } from "vitest";
import { currencyExponent, formatBps, formatMoney, humanize, toneFor } from "./format";

// §15.2/§28.2: money is integer minor units end-to-end; the UI only
// formats. These tests pin the formatting rules (incl. zero-decimal
// currencies) so a display bug can never silently change a figure.
describe("formatMoney", () => {
  it("formats INR minor units (paise) with two decimals", () => {
    expect(formatMoney(100000, "INR")).toBe("₹1,000.00");
    expect(formatMoney(75050, "INR")).toBe("₹750.50");
    expect(formatMoney(0, "INR")).toBe("₹0.00");
    expect(formatMoney(-25000, "INR")).toBe("-₹250.00");
  });
  it("formats USD and zero-decimal JPY by exponent", () => {
    // en-GB renders USD disambiguated as US$ in this ICU — that is the
    // platform-correct string, asserted as-is.
    expect(formatMoney(123456, "USD")).toBe("US$1,234.56");
    expect(currencyExponent("JPY")).toBe(0);
    expect(formatMoney(1200, "JPY")).toBe("JP¥1,200");
  });
  it("renders null/undefined as an explicit unavailable marker", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
  });
});

describe("formatBps / humanize / toneFor", () => {
  it("formats basis points as percentages", () => {
    expect(formatBps(250)).toBe("2.5%");
    expect(formatBps(null)).toBe("—");
  });
  it("humanizes backend status strings", () => {
    expect(humanize("safe_mode")).toBe("Safe Mode");
    expect(humanize("PAYMENT_SETTLED")).toBe("Payment Settled");
    expect(humanize(null)).toBe("—");
  });
  it("maps statuses to meaning tones (§4.1)", () => {
    expect(toneFor("healthy")).toBe("ok");
    expect(toneFor("pending")).toBe("warn");
    expect(toneFor("at_risk")).toBe("warn");
    expect(toneFor("failed")).toBe("bad");
    expect(toneFor("critical")).toBe("bad");
    // §4.1: blue = active.
    expect(toneFor("running")).toBe("info");
    expect(toneFor("active")).toBe("info");
    expect(toneFor("retired")).toBe("neutral");
  });
});
