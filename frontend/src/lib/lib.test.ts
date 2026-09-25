import { describe, expect, it } from "vitest";
import { slug } from "./download";
import { humanize, minutes } from "./labels";

describe("labels", () => {
  it("humanizes enum values", () => {
    expect(humanize("OWNER_AMBIGUITY")).toBe("Owner ambiguity");
  });

  it("formats minutes", () => {
    expect(minutes(30)).toBe("30 min");
    expect(minutes(7.25)).toBe("7.3 min");
  });
});

describe("slug", () => {
  it("makes file-name-safe slugs", () => {
    expect(slug("Payment Gateway (EU)")).toBe("payment-gateway-eu");
    expect(slug("***")).toBe("report");
  });
});
