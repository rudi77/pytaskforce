/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { type ReactElement } from "react";

import { buildRouter, __resetDynamicImportReloadGuard } from "./router";
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

const DYNAMIC_IMPORT_RELOAD_KEY = "tf:dynamic-import-reload-attempt";

const emptyRegistry: PluginRegistry = {
  register: vi.fn(),
  list: () => [],
  setActiveCapabilities: vi.fn(),
  getActiveCapabilities: () => [],
  isCapabilityActive: () => false,
  reset: vi.fn(),
};

function renderRouter(): { reload: ReturnType<typeof vi.fn> } {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  // jsdom's stock window.location.reload throws "Not implemented" — stub it
  // so we can both prevent the noise and assert call counts. Use
  // Object.defineProperty because `location` is read-only.
  const reload = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, reload },
  });

  const tree: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RouterProvider
          router={buildRouter(emptyRegistry)}
          future={{ v7_startTransition: true }}
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
  render(tree);
  return { reload };
}

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
    window.sessionStorage.removeItem(DYNAMIC_IMPORT_RELOAD_KEY);
    __resetDynamicImportReloadGuard();
  });

  afterEach(() => {
    useSettings.getState().setApiToken("");
    window.sessionStorage.removeItem(DYNAMIC_IMPORT_RELOAD_KEY);
    __resetDynamicImportReloadGuard();
    cleanup();
    vi.restoreAllMocks();
  });

  it("auto-reloads once on the first dynamic-import failure", async () => {
    // ``buildRouter`` mounts pages that read from React Query
    // immediately (``RequireAuth`` etc.). Without a QueryClientProvider
    // the *first* render error is ``No QueryClient set`` from React
    // Query, not the dynamic-import TypeError we mocked above — so the
    // error boundary's "Page update required" branch is never reached.
    // Wrap in a real client with retries off so the test stays
    // deterministic.
    const { reload } = renderRouter();

    // Wait for any rendered output from the error path. The boundary
    // remounts during react-router's transition recovery: first mount
    // schedules the reload, second mount sees the in-page-load guard
    // and falls back to the manual UI. In jsdom the reload is mocked,
    // so the manual UI ends up in the DOM; in production the real
    // reload tears the tree down before the second mount paints.
    await screen.findByRole("heading", { name: /page update required/i });
    // The canonical proof that the auto-reload path executed: reload
    // was invoked exactly once across the (re)mounts.
    expect(reload).toHaveBeenCalledTimes(1);
    // Guard stamp set so a fresh page load within the window won't loop.
    expect(window.sessionStorage.getItem(DYNAMIC_IMPORT_RELOAD_KEY)).not.toBeNull();
  });

  it("shows the manual error UI when a recent auto-reload didn't resolve the import", async () => {
    // Simulate "we already auto-reloaded a few seconds ago and the import
    // still fails" — the user gets the manual UI instead of a reload loop.
    window.sessionStorage.setItem(DYNAMIC_IMPORT_RELOAD_KEY, String(Date.now()));

    const { reload } = renderRouter();

    expect(
      await screen.findByRole("heading", { name: /page update required/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/the page module could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload page/i })).toBeInTheDocument();
    expect(screen.queryByText(/unexpected application error/i)).not.toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });
});
