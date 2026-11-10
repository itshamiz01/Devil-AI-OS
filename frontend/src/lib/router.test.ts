import { describe, expect, it } from "vitest";
import { breakpointForWidth } from "./hooks";
import { parseHash } from "./router";

// §23: the five layout bands. jsdom has no layout engine, so the bands
// are verified at the breakpoint-function level here; the CSS media
// queries consume the same thresholds (720/1100/1440/1920).
describe("breakpointForWidth (§28.5 bands)", () => {
  it("maps widths to the five bands", () => {
    expect(breakpointForWidth(390)).toBe("mobile");
    expect(breakpointForWidth(719)).toBe("mobile");
    expect(breakpointForWidth(720)).toBe("tablet");
    expect(breakpointForWidth(1099)).toBe("tablet");
    expect(breakpointForWidth(1100)).toBe("desktop-sm");
    expect(breakpointForWidth(1439)).toBe("desktop-sm");
    expect(breakpointForWidth(1440)).toBe("desktop");
    expect(breakpointForWidth(1919)).toBe("desktop");
    expect(breakpointForWidth(1920)).toBe("wide");
    expect(breakpointForWidth(2560)).toBe("wide");
  });
});

describe("parseHash", () => {
  it("defaults to overview", () => {
    expect(parseHash("").name).toBe("overview");
    expect(parseHash("#/").name).toBe("overview");
  });
  it("parses view + id params (deep links)", () => {
    const r = parseHash("#/businesses/abc-123");
    expect(r.name).toBe("businesses");
    expect(r.param).toBe("abc-123");
  });
  it("parses plain views", () => {
    expect(parseHash("#/security")).toEqual({ name: "security", param: null, raw: "security" });
  });
});
