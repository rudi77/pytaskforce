/**
 * @vitest-environment jsdom
 *
 * Regression tests for the permissions hook used to gate enterprise-only
 * actions in the host UI. The hook MUST stay permissive when the backend
 * has no auth provider (404 / 501 from /api/v1/admin/me) so framework-only
 * builds keep working, and it MUST gate by permission strings when the
 * enterprise backend returns a permissions list.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCurrentPermissions } from "./permissions";

const apiMocks = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return {
    apiFetch: vi.fn(),
    ApiError: FakeApiError,
  };
});

vi.mock("@/api/client", () => ({
  apiFetch: apiMocks.apiFetch,
  ApiError: apiMocks.ApiError,
}));

function Probe() {
  const result = useCurrentPermissions();
  return (
    <div>
      <span data-testid="state">{result.isLoading ? "loading" : "ready"}</span>
      <span data-testid="enforced">{String(result.enforced)}</span>
      <span data-testid="can-create">{String(result.can("agent:create"))}</span>
      <span data-testid="can-execute">{String(result.can("agent:execute"))}</span>
    </div>
  );
}

function renderProbe() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe />
    </QueryClientProvider>,
  );
}

describe("useCurrentPermissions", () => {
  beforeEach(() => {
    apiMocks.apiFetch.mockReset();
  });
  afterEach(() => {
    apiMocks.apiFetch.mockReset();
  });

  it("treats a 404 from /admin/me as permissive (framework-only deployment)", async () => {
    apiMocks.apiFetch.mockRejectedValueOnce(new apiMocks.ApiError("not found", 404));

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("ready");
    });
    expect(screen.getByTestId("enforced").textContent).toBe("false");
    expect(screen.getByTestId("can-create").textContent).toBe("true");
    expect(screen.getByTestId("can-execute").textContent).toBe("true");
  });

  it("treats a 501 from /admin/me as permissive (no auth provider)", async () => {
    apiMocks.apiFetch.mockRejectedValueOnce(new apiMocks.ApiError("not implemented", 501));

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("ready");
    });
    expect(screen.getByTestId("enforced").textContent).toBe("false");
    expect(screen.getByTestId("can-create").textContent).toBe("true");
  });

  it("gates by the returned permission set when the enterprise backend answers", async () => {
    apiMocks.apiFetch.mockResolvedValueOnce({
      roles: ["operator"],
      permissions: ["agent:read", "agent:execute"],
    });

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe("ready");
    });
    expect(screen.getByTestId("enforced").textContent).toBe("true");
    expect(screen.getByTestId("can-create").textContent).toBe("false");
    expect(screen.getByTestId("can-execute").textContent).toBe("true");
  });

  it("returns can()=false for every permission while still loading", () => {
    let resolveFetch: ((value: unknown) => void) | undefined;
    apiMocks.apiFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );

    renderProbe();

    expect(screen.getByTestId("state").textContent).toBe("loading");
    expect(screen.getByTestId("can-create").textContent).toBe("false");
    expect(screen.getByTestId("can-execute").textContent).toBe("false");

    resolveFetch?.({ permissions: ["agent:create"] });
  });
});
