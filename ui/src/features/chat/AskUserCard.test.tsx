/**
 * @vitest-environment jsdom
 *
 * Regression tests for ``<AskUserCard>`` — the inline prompt that surfaces
 * a paused agent's ``ask_user`` request (Cowork-parity Phase 1 follow-up).
 *
 * The contract:
 *
 *   1. The question text is rendered prominently and missing-field hints
 *      are listed as badges.
 *   2. Pressing the Send button (or Cmd/Ctrl+Enter) calls ``onAnswer``
 *      with the trimmed text and clears the textarea afterwards.
 *   3. Empty/whitespace-only input never fires onAnswer.
 *   4. Channel-targeted prompts (Telegram, Teams, …) explicitly tell the
 *      user the answer is expected on that channel.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AskUserCard } from "./AskUserCard";

describe("AskUserCard", () => {
  it("renders the question and the missing-field hints", () => {
    render(
      <AskUserCard
        prompt={{
          question: "Which date range should I use?",
          missing: ["start_date", "end_date"],
        }}
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getByText("Which date range should I use?")).toBeInTheDocument();
    expect(screen.getByText("start_date")).toBeInTheDocument();
    expect(screen.getByText("end_date")).toBeInTheDocument();
    // Default (chat-side) prompts do NOT show the channel banner.
    expect(screen.queryByText(/Answer expected on/i)).toBeNull();
  });

  it("calls onAnswer with the trimmed text when Send is clicked", () => {
    const onAnswer = vi.fn();
    render(
      <AskUserCard
        prompt={{ question: "When?", missing: [] }}
        onAnswer={onAnswer}
      />,
    );

    const textarea = screen.getByLabelText(
      "Answer to agent question",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "  tomorrow  " } });
    fireEvent.click(screen.getByRole("button", { name: /send answer/i }));

    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(onAnswer).toHaveBeenCalledWith("tomorrow");
    // Textarea clears after submit so a second answer doesn't accidentally
    // include the first one.
    expect(textarea.value).toBe("");
  });

  it("submits on Cmd/Ctrl+Enter", async () => {
    const onAnswer = vi.fn();
    render(
      <AskUserCard
        prompt={{ question: "Confirm?", missing: [] }}
        onAnswer={onAnswer}
      />,
    );

    const textarea = screen.getByLabelText("Answer to agent question");
    fireEvent.change(textarea, { target: { value: "yes" } });
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });

    expect(onAnswer).toHaveBeenCalledWith("yes");
  });

  it("ignores empty / whitespace-only input", () => {
    const onAnswer = vi.fn();
    render(
      <AskUserCard
        prompt={{ question: "When?", missing: [] }}
        onAnswer={onAnswer}
      />,
    );

    // Send button is disabled when the input is empty.
    const sendBtn = screen.getByRole("button", { name: /send answer/i });
    expect(sendBtn).toBeDisabled();

    const textarea = screen.getByLabelText("Answer to agent question");
    fireEvent.change(textarea, { target: { value: "   " } });
    expect(sendBtn).toBeDisabled();
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("explains channel routing for channel-targeted prompts", () => {
    render(
      <AskUserCard
        prompt={{
          question: "What's your address?",
          missing: ["address"],
          channel: "telegram",
          recipientId: "user-42",
        }}
        onAnswer={vi.fn()}
      />,
    );

    // Channel banner appears.
    expect(screen.getByText(/Answer expected on/i)).toBeInTheDocument();
    expect(screen.getByText("telegram")).toBeInTheDocument();
    expect(screen.getByText("user-42")).toBeInTheDocument();
    // The override-via-chat hint is only shown when channel routing is
    // active so users know they have an escape hatch.
    expect(
      screen.getByText(/will resume automatically/i),
    ).toBeInTheDocument();
  });

  it("disables the input while disabled prop is true", () => {
    render(
      <AskUserCard
        prompt={{ question: "When?", missing: [] }}
        onAnswer={vi.fn()}
        disabled
      />,
    );
    expect(screen.getByLabelText("Answer to agent question")).toBeDisabled();
    expect(screen.getByRole("button", { name: /send answer/i })).toBeDisabled();
  });
});
