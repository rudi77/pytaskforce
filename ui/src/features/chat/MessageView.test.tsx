/**
 * @vitest-environment jsdom
 *
 * Regression tests for ``MessageBubble`` view-mode handling (Cowork-parity
 * Phase 1). Three transcript modes mirror Claude Code Desktop:
 *
 *   - normal:  tool calls visible but COLLAPSED
 *   - verbose: tool calls visible and AUTO-EXPANDED
 *   - summary: tool calls HIDDEN entirely
 *
 * These tests pin the rendering contract so we don't accidentally regress
 * one mode while iterating on the others.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageBubble } from "./MessageView";
import type { ToolCallView } from "./useChatStream";

const sampleToolCalls: ToolCallView[] = [
  {
    id: "call-1",
    name: "file_read",
    args: { path: "/tmp/foo.txt" },
    result: "file contents",
    pending: false,
  },
];

describe("MessageBubble view modes", () => {
  it("normal mode renders tool calls as collapsed details", () => {
    render(
      <MessageBubble
        message={{ role: "assistant", content: "Done." }}
        toolCalls={sampleToolCalls}
        viewMode="normal"
      />,
    );
    // The tool name is in the <summary>, so it's visible even when
    // collapsed.
    expect(screen.getByText("file_read")).toBeInTheDocument();
    const details = screen.getByText("file_read").closest("details");
    expect(details).toBeTruthy();
    // Collapsed by default — no ``open`` attribute.
    expect(details?.hasAttribute("open")).toBe(false);
  });

  it("verbose mode renders tool calls auto-expanded", () => {
    render(
      <MessageBubble
        message={{ role: "assistant", content: "Done." }}
        toolCalls={sampleToolCalls}
        viewMode="verbose"
      />,
    );
    const details = screen.getByText("file_read").closest("details");
    expect(details?.hasAttribute("open")).toBe(true);
    // Args label only appears when the <details> body is rendered.
    expect(screen.getByText("args")).toBeInTheDocument();
  });

  it("summary mode hides tool calls entirely", () => {
    render(
      <MessageBubble
        message={{ role: "assistant", content: "Done." }}
        toolCalls={sampleToolCalls}
        viewMode="summary"
      />,
    );
    // The tool name should not appear anywhere.
    expect(screen.queryByText("file_read")).toBeNull();
    // Final assistant text remains visible — that's the whole point of
    // summary mode.
    expect(screen.getByText("Done.")).toBeInTheDocument();
  });

  it("defaults to normal when viewMode is omitted (backwards compat)", () => {
    render(
      <MessageBubble
        message={{ role: "assistant", content: "Done." }}
        toolCalls={sampleToolCalls}
      />,
    );
    const details = screen.getByText("file_read").closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
  });
});
