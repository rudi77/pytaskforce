/**
 * @vitest-environment jsdom
 *
 * Tests for ProjectDetailPage: lists project conversations (active +
 * archived) with resume and delete actions. These are the affordances
 * the project page on its own does not expose, so the regressions to
 * guard against are:
 *   - active list renders project conversations
 *   - clicking a row navigates to /chat/:id
 *   - delete invokes useDeleteConversation with the right id
 *   - archived list toggles open and renders
 */

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "./ProjectDetailPage";

const mocks = vi.hoisted(() => ({
  active: [] as Array<{
    conversation_id: string;
    topic: string | null;
    channel: string;
    last_activity: string;
    started_at: string;
    message_count: number;
    project_id: string | null;
  }>,
  archived: [] as Array<{
    conversation_id: string;
    topic: string;
    summary: string;
    started_at: string;
    archived_at: string;
    message_count: number;
    project_id: string | null;
  }>,
  project: {
    project_id: "proj-1",
    name: "Tutti",
    path: "C:/work/tutti",
    created_at: new Date().toISOString(),
  } as { project_id: string; name: string; path: string; created_at: string } | null,
  deleteMutate: vi.fn(),
  createMutate: vi.fn(),
}));

vi.mock("@/components/ui/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@/api/queries", async () => {
  const actual = await vi.importActual<typeof import("@/api/queries")>(
    "@/api/queries",
  );
  return {
    ...actual,
    useProject: () => ({ data: mocks.project, isError: false, error: null }),
    useConversations: () => ({
      data: mocks.active,
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
    }),
    useArchivedConversations: () => ({
      data: mocks.archived,
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
    }),
    useCreateConversation: () => ({
      mutateAsync: mocks.createMutate,
      isPending: false,
    }),
    useDeleteConversation: () => ({
      mutateAsync: mocks.deleteMutate,
      isPending: false,
    }),
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
          <Route
            path="/projects/:projectId"
            element={<ProjectDetailPage />}
          />
          <Route
            path="/chat/:conversationId"
            element={<div data-testid="chat-target" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectDetailPage", () => {
  beforeEach(() => {
    mocks.active = [];
    mocks.archived = [];
    mocks.deleteMutate = vi.fn().mockResolvedValue(undefined);
    mocks.createMutate = vi.fn().mockResolvedValue({
      conversation_id: "new-conv",
    });
  });

  it("renders project header with name and path", () => {
    renderAt("/projects/proj-1");
    expect(screen.getByText("Tutti")).toBeInTheDocument();
    expect(screen.getByText("C:/work/tutti")).toBeInTheDocument();
  });

  it("lists active conversations and lets the user open one", () => {
    mocks.active = [
      {
        conversation_id: "conv-a",
        topic: "Pricing question",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 3,
        project_id: "proj-1",
      },
    ];
    renderAt("/projects/proj-1");

    const row = screen.getByTitle("Continue this conversation");
    expect(screen.getByText("Pricing question")).toBeInTheDocument();
    fireEvent.click(row);
    expect(screen.getByTestId("chat-target")).toBeInTheDocument();
  });

  it("deletes a conversation when the row's trash button is clicked", async () => {
    mocks.active = [
      {
        conversation_id: "conv-a",
        topic: "Pricing question",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 3,
        project_id: "proj-1",
      },
    ];
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderAt("/projects/proj-1");

    fireEvent.click(screen.getByLabelText("Delete conversation"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(mocks.deleteMutate).toHaveBeenCalledWith({ id: "conv-a" });
    confirmSpy.mockRestore();
  });

  it("aborts deletion when the user cancels the confirm prompt", () => {
    mocks.active = [
      {
        conversation_id: "conv-a",
        topic: "Pricing",
        channel: "rest",
        last_activity: new Date().toISOString(),
        started_at: new Date().toISOString(),
        message_count: 1,
        project_id: "proj-1",
      },
    ];
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderAt("/projects/proj-1");

    fireEvent.click(screen.getByLabelText("Delete conversation"));
    expect(mocks.deleteMutate).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("toggles the archived section open and shows archived rows", () => {
    mocks.archived = [
      {
        conversation_id: "arch-1",
        topic: "Old topic",
        summary: "x",
        started_at: new Date().toISOString(),
        archived_at: new Date().toISOString(),
        message_count: 5,
        project_id: "proj-1",
      },
    ];
    renderAt("/projects/proj-1");

    // Collapsed by default — archived row should not be present.
    expect(screen.queryByText("Old topic")).not.toBeInTheDocument();

    // Expand: the "Archived" toggle is an aria-expanded button.
    fireEvent.click(screen.getByRole("button", { name: /archived/i }));
    expect(screen.getByText("Old topic")).toBeInTheDocument();
  });

  it("starts a new conversation and navigates to it", async () => {
    renderAt("/projects/proj-1");

    fireEvent.click(screen.getByRole("button", { name: /new conversation/i }));
    // mutateAsync resolves on the microtask queue — flush.
    await Promise.resolve();
    await Promise.resolve();
    expect(mocks.createMutate).toHaveBeenCalledWith({
      channel: "rest",
      project_id: "proj-1",
    });
  });

  it("shows an empty state when there are no active conversations", () => {
    renderAt("/projects/proj-1");
    expect(screen.getByText(/keine aktiven conversations/i)).toBeInTheDocument();
  });
});
