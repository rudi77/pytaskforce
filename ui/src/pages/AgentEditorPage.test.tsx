/**
 * @vitest-environment jsdom
 *
 * Regression tests for the create-agent permission gate on AgentEditorPage.
 * Without agent:create the wizard / profi-editor must NOT render — the user
 * sees a Forbidden empty state instead. With the permission, the wizard
 * renders normally.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentEditorPage from "./AgentEditorPage";

const mocks = vi.hoisted(() => ({
  permissions: new Set<string>(),
  permissionsLoading: false,
}));

vi.mock("@/lib/permissions", () => ({
  useCurrentPermissions: () => ({
    isLoading: mocks.permissionsLoading,
    enforced: true,
    can: (permission: string) => mocks.permissions.has(permission),
  }),
}));

vi.mock("@/features/agents/wizard/AgentWizard", () => ({
  AgentWizard: () => <div data-testid="agent-wizard">wizard</div>,
}));

vi.mock("@/features/agents/AgentProfileEditor", () => ({
  AgentProfileEditor: () => <div data-testid="agent-profile-editor">profile editor</div>,
}));

vi.mock("@/api/queries", () => ({
  queryKeys: { agent: (id: string) => ["agent", id] },
  useDeleteCustomAgent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/api/client", () => ({
  ApiError: class ApiError extends Error {
    status = 500;
  },
  apiFetch: vi.fn(),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AgentEditorPage mode="create" />
    </MemoryRouter>,
  );
}

describe("AgentEditorPage create permission gate", () => {
  beforeEach(() => {
    mocks.permissions = new Set<string>();
    mocks.permissionsLoading = false;
  });

  it("blocks the wizard with a Forbidden state when the user lacks agent:create", () => {
    mocks.permissions = new Set(["agent:read"]);

    renderPage();

    expect(screen.getByText(/Forbidden/i)).toBeInTheDocument();
    expect(screen.queryByTestId("agent-wizard")).not.toBeInTheDocument();
    expect(screen.queryByTestId("agent-profile-editor")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to agents/i })).toHaveAttribute(
      "href",
      "/agents",
    );
  });

  it("renders the wizard when the user has agent:create", () => {
    mocks.permissions = new Set(["agent:read", "agent:create"]);

    renderPage();

    expect(screen.getByTestId("agent-wizard")).toBeInTheDocument();
    expect(screen.queryByText(/Forbidden/i)).not.toBeInTheDocument();
  });
});
