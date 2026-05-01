import { describe, expect, it } from "vitest";

import { validateApiBaseUrl } from "./settings";

describe("validateApiBaseUrl", () => {
  it("accepts an empty string (use same-origin proxy)", () => {
    expect(validateApiBaseUrl("")).toBe("");
    expect(validateApiBaseUrl("   ")).toBe("");
  });

  it("accepts http and https URLs", () => {
    expect(validateApiBaseUrl("http://localhost:8070")).toBe("");
    expect(validateApiBaseUrl("https://api.example.com")).toBe("");
    expect(validateApiBaseUrl("http://127.0.0.1:8070/")).toBe("");
  });

  it("rejects non-http(s) protocols", () => {
    expect(validateApiBaseUrl("ftp://example.com")).not.toBe("");
    expect(validateApiBaseUrl("file:///etc/passwd")).not.toBe("");
    expect(validateApiBaseUrl("javascript:alert(1)")).not.toBe("");
  });

  it("rejects unparseable junk", () => {
    expect(validateApiBaseUrl("not a url")).not.toBe("");
    expect(validateApiBaseUrl("://broken")).not.toBe("");
  });
});
