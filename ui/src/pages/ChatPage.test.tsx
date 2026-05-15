/**
 * @vitest-environment jsdom
 *
 * Regression tests for the Chat page redesign (#180):
 *   - EmptyState (not the old border-dashed pattern) is rendered when no
 *     conversation is selected and inside the message surface when the
 *     selected conversation has zero messages.
 *   - Header surfaces the topic primarily and the conversation id only
 *     as a secondary, monospaced hash chip.
 */

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChatPage from "./ChatPage";

const mocks = vi.hoisted(() => ({
  conversations: [] as Array<{
    conversation_id: string;
    topic: string | null;
    channel: string;
    last_activity: string;
    started_at: string;
    message_count: number;
  }>,
  messages: [] as Array<{ role: string; content: string }>,
}));

vi.mock("@/components/ui/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@/features/chat/ChatComposer", () => ({
  ChatComposer: () => <div data-testid="chat-composer" />,
}));

vi.mock("@/features/chat/useChatStream", () => ({
  useChatStream: () => ({
    isStreaming: false,
    state: {
      text: "",
      toolCalls: [],
      planSteps: [],
      completed: false,
      persistedAt: null,
      sessionId: null,
      pendingAskUser: null,
    },
    error: null,
    reset: vi.fn(),
    cancel: vi.fn(),
    send: vi.fn(),
  }),
}));

vi.mock("@/api/queries", async () => {
  const actual = await vi.importActual<typeof import("@/api/queries")>("@/api/queries");
  return {
    ...actual,
    useConversations: () => ({ data: mocks.conversations, isLoading: false }),
    useArchivedConversations: () => ({ data: [], isLoading: false }),
    useConversationMessages: () => ({
      data: mocks.messages,
      isLoading: false,
      error: null,
    }),
    useAgents: () => ({ data: { agents: [] }, isLoading: false }),
    useHealth: () => ({ data: undefined, isLoading: false, isError: false }),
    useCreateConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useArchiveConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useForkConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useCompactConversation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatPage redesign", () => {
  it("shows the EmptyState picker when no conversation is in the URL", () => {
    mocks.conversations = [];
    mocks.messages = [];

    renderAt("/chat");

    expect(screen.getByText("Pick or start a conversation")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /start conversation/i }),
    ).toBeInTheDocument();
  });

  it("surfaces the topic as the primary header title with the id as a hash chip", () => {
    mocks.conversations = [
      {
        conversation_id: "abc12345-6789-abcd-ef01-234567890abc",
        topic: "Quarterly review prep",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 3,
      },
    ];
    mocks.messages = [{ role: "user", content: "hi" }];

    renderAt("/chat/abc12345-6789-abcd-ef01-234567890abc");

    // Topic must be a header-level element so it wins primacy.
    expect(
      screen.getByRole("heading", { name: "Quarterly review prep" }),
    ).toBeInTheDocument();

    // The truncated id is shown but only as secondary text (preserves
    // debugging affordance without dominating the header).
    expect(screen.getByText("abc12345…")).toBeInTheDocument();
  });

  it("renders the transcript view-mode dropdown in the header", () => {
    mocks.conversations = [
      {
        conversation_id: "view-mode-1",
        topic: "Has a view picker",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 1,
      },
    ];
    mocks.messages = [{ role: "user", content: "hi" }];

    renderAt("/chat/view-mode-1");

    const picker = screen.getByLabelText("Transcript view") as HTMLSelectElement;
    expect(picker).toBeInTheDocument();
    // All three Cowork-style modes are listed.
    expect(picker.options).toHaveLength(3);
    expect(
      Array.from(picker.options).map((o) => o.value),
    ).toEqual(["normal", "verbose", "summary"]);
    // Default is "normal" (zustand store's initial value).
    expect(picker.value).toBe("normal");
  });

  it("renders the assistant empty state via <EmptyState/> when messages are empty", () => {
    mocks.conversations = [
      {
        conversation_id: "empty-1",
        topic: "Empty thread",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 0,
      },
    ];
    mocks.messages = [];

    renderAt("/chat/empty-1");

    // The new copy lives inside the shared EmptyState component instead
    // of the old ad-hoc border-dashed ConversationStarter.
    expect(screen.getByText("How can the agent help?")).toBeInTheDocument();
  });
});
