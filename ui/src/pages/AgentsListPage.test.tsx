/**
 * @vitest-environment jsdom
 *
 * Regression test for permission-gated actions on AgentsListPage. Read-only
 * users (operator role) must NOT see the "+ New Agent" / "Advanced Editor"
 * buttons. With agent:create granted both must reappear.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentsListPage from "./AgentsListPage";

const mocks = vi.hoisted(() => ({
  permissions: new Set<string>(),
}));

vi.mock("@/lib/permissions", () => ({
  useCurrentPermissions: () => ({
    isLoading: false,
    enforced: true,
    can: (permission: string) => mocks.permissions.has(permission),
  }),
}));

vi.mock("@/api/queries", () => ({
  useAgents: () => ({
    data: {
      agents: [
        {
          source: "custom",
          agent_id: "writer",
          name: "Writer",
          description: "A test agent",
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useActiveDeployment: () => ({ data: null, isLoading: false }),
}));

vi.mock("@/api/client", () => ({
  ApiError: class ApiError extends Error {},
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AgentsListPage />
    </MemoryRouter>,
  );
}

describe("AgentsListPage permissions", () => {
  beforeEach(() => {
    mocks.permissions = new Set<string>();
  });

  it("hides create-agent buttons when the user lacks agent:create", () => {
    mocks.permissions = new Set(["agent:read"]);

    renderPage();

    // Was role="link" (Button asChild + <Link>) before the FluentUI migration —
    // the actions are now Fluent <Button onClick={() => navigate(...)}>, so
    // their semantic role is "button". Behaviour is identical.
    expect(screen.queryByRole("button", { name: /New Agent/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Advanced Editor/i })).not.toBeInTheDocument();
    expect(screen.getByText("Writer")).toBeInTheDocument();
  });

  it("shows create-agent buttons when the user has agent:create", () => {
    mocks.permissions = new Set(["agent:read", "agent:create"]);

    renderPage();

    expect(screen.getByRole("button", { name: /New Agent/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Advanced Editor/i })).toBeInTheDocument();
  });
});
