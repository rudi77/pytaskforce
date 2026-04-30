import { describe, expect, it } from "vitest";

import { deriveProfileId, EMPTY_WIZARD_STATE } from "./types";

describe("deriveProfileId", () => {
  it("slugifies plain ascii names", () => {
    expect(deriveProfileId("Anna")).toBe("anna");
    expect(deriveProfileId("Buchhalter Bot")).toBe("buchhalter-bot");
    expect(deriveProfileId("My Helper 42")).toBe("my-helper-42");
  });

  it("transliterates German umlauts and ß so the slug matches NAME_PATTERN", () => {
    expect(deriveProfileId("Über-Helfer")).toBe("ueber-helfer");
    expect(deriveProfileId("Maße & Massen")).toBe("masse-massen");
    expect(deriveProfileId("Größe")).toBe("groesse");
  });

  it("strips other diacritics", () => {
    expect(deriveProfileId("Café")).toBe("cafe");
  });

  it("collapses whitespace and special characters into single hyphens", () => {
    expect(deriveProfileId("Mr.   Bookkeeper!")).toBe("mr.-bookkeeper");
    expect(deriveProfileId("a/b\\c")).toBe("a-b-c");
  });

  it("returns 'agent' for empty or fully invalid input", () => {
    expect(deriveProfileId("")).toBe("agent");
    expect(deriveProfileId("   ")).toBe("agent");
    expect(deriveProfileId("???")).toBe("agent");
  });

  it("preserves dots, underscores and digits (allowed characters)", () => {
    expect(deriveProfileId("v1.2_beta")).toBe("v1.2_beta");
  });
});

describe("EMPTY_WIZARD_STATE", () => {
  it("has sensible defaults that won't bypass step validation", () => {
    expect(EMPTY_WIZARD_STATE.template).toBeNull();
    expect(EMPTY_WIZARD_STATE.displayName).toBe("");
    expect(EMPTY_WIZARD_STATE.tools).toEqual([]);
    expect(EMPTY_WIZARD_STATE.tone).toBe("professionell");
    expect(EMPTY_WIZARD_STATE.language).toBe("Deutsch");
    expect(EMPTY_WIZARD_STATE.systemPrompt).toBe("");
  });
});
