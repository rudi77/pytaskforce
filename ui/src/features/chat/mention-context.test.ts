/**
 * Unit tests for the ``@mention`` context detector. Boundary handling
 * is the whole game — easier to TDD here than to debug inside the
 * composer.
 */
import { describe, expect, it } from "vitest";

import { applyMentionPick, getMentionContext } from "./mention-context";

describe("getMentionContext", () => {
  it("returns null when the cursor isn't after any @", () => {
    expect(getMentionContext("hello world", 5)).toBeNull();
  });

  it("detects an @ at the start of the value", () => {
    expect(getMentionContext("@foo", 4)).toEqual({ start: 0, query: "foo" });
  });

  it("returns empty query when cursor is right after @", () => {
    // User just typed ``@`` — picker should open with the root listing.
    expect(getMentionContext("@", 1)).toEqual({ start: 0, query: "" });
  });

  it("requires whitespace before @ (rejects email-like patterns)", () => {
    // ``foo@bar`` is not a file mention — the @ has letters to its left.
    expect(getMentionContext("foo@bar", 7)).toBeNull();
    expect(getMentionContext("foo@", 4)).toBeNull();
  });

  it("accepts @ preceded by space or newline", () => {
    expect(getMentionContext("look at @src", 12)).toEqual({
      start: 8,
      query: "src",
    });
    expect(getMentionContext("first line\n@s", 13)).toEqual({
      start: 11,
      query: "s",
    });
  });

  it("terminates the mention when a space appears in the query", () => {
    // Cursor is past the space — the mention is "completed".
    expect(getMentionContext("@foo bar", 8)).toBeNull();
  });

  it("ignores @ further back when an intervening space resets context", () => {
    // ``@a`` mention started, then space, then plain typing — picker
    // must NOT come back.
    expect(getMentionContext("@a more text", 12)).toBeNull();
  });

  it("works mid-string with cursor before the end", () => {
    const value = "use @src/foo and @tests/bar";
    //  positions:  0123456789012345678901234567
    //                       1111111111222222222
    // Cursor at 22 sits right after the 's' in "tests" (chars 18..21 are
    // "test", char 22 is 's', cursor between 21 and 22 is after "test").
    expect(getMentionContext(value, 22)).toEqual({
      start: 17,
      query: "test",
    });
  });

  it("handles cursor=0 safely", () => {
    expect(getMentionContext("@foo", 0)).toBeNull();
  });

  it("rejects newlines inside the query", () => {
    // Multi-line paste with @ on a previous line — picker should NOT
    // span the line break.
    expect(getMentionContext("@foo\nbar", 8)).toBeNull();
  });
});

describe("applyMentionPick", () => {
  it("replaces @partial with @full-path and appends a trailing space", () => {
    const result = applyMentionPick("look at @sr", { start: 8, query: "sr" }, "src/foo.py");
    expect(result.value).toBe("look at @src/foo.py ");
    expect(result.cursor).toBe(result.value.length);
  });

  it("preserves text after the mention", () => {
    const value = "use @s here";
    const result = applyMentionPick(value, { start: 4, query: "s" }, "src/foo.py");
    expect(result.value).toBe("use @src/foo.py  here");
    // Cursor sits right after the inserted "@src/foo.py " (with its
    // trailing space) — i.e. between the two spaces.
    expect(result.value.slice(0, result.cursor)).toBe("use @src/foo.py ");
  });

  it("works when the mention is at the very start", () => {
    const result = applyMentionPick("@", { start: 0, query: "" }, "README.md");
    expect(result.value).toBe("@README.md ");
    expect(result.cursor).toBe("@README.md ".length);
  });
});
