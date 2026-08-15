import { describe, expect, it } from "vitest";

import {
  GULONG_ORIGIN,
  isAllowedGulongOrigin,
  resolveGulongParentOrigin,
} from "./gulong-origin";

describe("Gulong parent origin handling", () => {
  it("accepts both official website hostnames", () => {
    expect(GULONG_ORIGIN).toBe("https://sologle.com");
    expect(isAllowedGulongOrigin("https://sologle.com")).toBe(true);
    expect(isAllowedGulongOrigin("https://www.sologle.com")).toBe(true);
  });

  it("rejects opaque, malformed, and unrelated origins", () => {
    expect(isAllowedGulongOrigin("null")).toBe(false);
    expect(isAllowedGulongOrigin("not-a-url")).toBe(false);
    expect(isAllowedGulongOrigin("https://example.com")).toBe(false);
  });

  it("uses the actual official referrer so postMessage reaches www", () => {
    expect(resolveGulongParentOrigin("https://www.sologle.com/short-drama")).toBe(
      "https://www.sologle.com",
    );
    expect(resolveGulongParentOrigin("https://example.com/short-drama")).toBe(
      "https://sologle.com",
    );
  });
});
