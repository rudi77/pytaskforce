/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";

import { buildRouter } from "./router";
import { ThemeProvider } from "./theme-provider";
import { useSettings } from "@/lib/settings";
import type { PluginRegistry } from "@/plugins/types";

vi.mock("@/components/HealthIndicator", () => ({
  HealthIndicator: () => <div aria-label="Backend status" />,
}));

vi.mock("@/pages/AgentEditorPage", () => {
  return {
    default: () => {
      throw new TypeError(
        "Failed to fetch dynamically imported module: http://localhost:5173/src/pages/AgentEditorPage.tsx",
      );
    },
  };
});

const emptyRegistry: PluginRegistry = {
  register: vi.fn(),
  list: () => [],
  setActiveCapabilities: vi.fn(),
  getActiveCapabilities: () => [],
  isCapabilityActive: () => false,
  reset: vi.fn(),
};

describe("buildRouter", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    window.matchMedia = vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    window.history.pushState({}, "", "/agents/new");
    useSettings.getState().setApiToken("test-token");
  });

  afterEach(() => {
    useSettings.getState().setApiToken("");
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows the custom route error page when AgentEditorPage fails to load", async () => {
    render(
      <ThemeProvider>
        <RouterProvider router={buildRouter(emptyRegistry)} future={{ v7_startTransition: true }} />
      </ThemeProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: /page update required/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/the page module could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload page/i })).toBeInTheDocument();
    expect(screen.queryByText(/unexpected application error/i)).not.toBeInTheDocument();
  });
});
