import { describe, expect, it } from "vitest";
import { CRM_STAGES, stageTone, parsePhone, countryCodeHint } from "./crm";

describe("CRM stages", () => {
  it("lists the funnel in order", () => {
    expect([...CRM_STAGES]).toEqual(["New", "Contacted", "Qualified", "Proposal", "Customer", "Lost"]);
  });

  it("falls back to the New tone for unknown stages", () => {
    expect(stageTone("Won")).toBe(stageTone("New"));
    expect(stageTone("Customer")).toContain("vbase-green");
  });
});

describe("parsePhone", () => {
  it("preserves explicit country codes and strips formatting", () => {
    expect(parsePhone("+1 (415) 555-0132")).toEqual({ display: "+14155550132", hasCountryCode: true });
    expect(parsePhone("0044 20 7946 0958")).toEqual({ display: "+442079460958", hasCountryCode: true });
  });

  it("flags local numbers without inventing a code", () => {
    expect(parsePhone("98765 43210")).toEqual({ display: "9876543210", hasCountryCode: false });
  });

  it("returns null for blank values", () => {
    expect(parsePhone(null)).toBeNull();
    expect(parsePhone("   ")).toBeNull();
  });

  it("drops extensions", () => {
    expect(parsePhone("+1-800-555-0100 x123")?.display).toBe("+18005550100");
  });
});

describe("countryCodeHint", () => {
  it("only extracts the unambiguous +1 case", () => {
    expect(countryCodeHint("+14155550132")).toBe("+1");
    expect(countryCodeHint("+442079460958")).toBe("+");
    expect(countryCodeHint("02079460000")).toBeNull();
  });
});
