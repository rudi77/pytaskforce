/**
 * @vitest-environment jsdom
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowsPage from "./WorkflowsPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <WorkflowsPage />
    </MemoryRouter>,
  );
}

const mocks = vi.hoisted(() => ({
  permissions: new Set<string>(),
  runWorkflow: vi.fn(),
}));

vi.mock("@/features/workflows/WorkflowEditor", () => ({
  WorkflowEditor: () => null,
}));

vi.mock("@/components/ui/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/lib/permissions", () => ({
  useCurrentPermissions: () => ({
    isLoading: false,
    enforced: true,
    can: (permission: string) => mocks.permissions.has(permission),
  }),
}));

vi.mock("@/api/queries", () => ({
  useWorkflowDefinitions: () => ({
    data: {
      workflows: [
        {
          workflow_id: "daily-report",
          name: "Daily Report",
          description: "Send the daily briefing",
          trigger: "manual",
          trigger_config: {},
          steps: [{ step_id: "collect", agent: "butler", task: "Collect news" }],
          metadata: {},
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useSaveWorkflowDefinition: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useDeleteWorkflowDefinition: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useRunWorkflowDefinition: () => ({
    mutateAsync: mocks.runWorkflow,
    isPending: false,
  }),
  ApiError: class ApiError extends Error {},
}));

describe("WorkflowsPage permissions and run results", () => {
  beforeEach(() => {
    mocks.permissions = new Set<string>();
    mocks.runWorkflow.mockReset();
  });

  it("hides workflow mutation and run actions from read-only users", () => {
    mocks.permissions = new Set(["agent:read"]);

    renderPage();

    expect(screen.getByText("Daily Report")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /new workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^run$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete workflow/i })).not.toBeInTheDocument();
  });

  it("renders workflow step output after a successful run", async () => {
    mocks.permissions = new Set(["agent:read", "agent:execute"]);
    mocks.runWorkflow.mockResolvedValue({
      success: true,
      workflow_id: "daily-report",
      steps: [
        {
          step_id: "notify",
          agent: "config-butler",
          task: "Send notification",
          status: "failed",
          error: "No outbound sender configured for channel 'telegram'",
        },
      ],
    });

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /^run$/i }));

    await waitFor(() => {
      expect(mocks.runWorkflow).toHaveBeenCalledWith({ workflowId: "daily-report" });
    });
    expect(await screen.findByText("Last run")).toBeInTheDocument();
    expect(screen.getByText("notify")).toBeInTheDocument();
    expect(
      screen.getByText("No outbound sender configured for channel 'telegram'"),
    ).toBeInTheDocument();
  });
});
