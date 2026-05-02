/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { UserRolesProvider } from "@taskforce/ui-shell";

import { RequireRole, __resetWarnedKeysForTests } from "./RequireRole";

function withRouter(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>;
}

describe("RequireRole", () => {
  beforeEach(() => {
    __resetWarnedKeysForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children when no roles are required", () => {
    render(
      withRouter(
        <RequireRole roles={[]}>
          <div>open content</div>
        </RequireRole>,
      ),
    );
    expect(screen.getByText("open content")).toBeInTheDocument();
  });

  it("renders children permissively when no provider is mounted (with console warning)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(
      withRouter(
        <RequireRole roles={["admin"]}>
          <div>admin content</div>
        </RequireRole>,
      ),
    );
    expect(screen.getByText("admin content")).toBeInTheDocument();
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain("UserRolesProvider");
  });

  it("only warns once per role-set when no provider is mounted", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(
      withRouter(
        <>
          <RequireRole roles={["admin"]}>
            <div>page A</div>
          </RequireRole>
          <RequireRole roles={["admin"]}>
            <div>page B</div>
          </RequireRole>
        </>,
      ),
    );
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("renders children when the user has at least one required role", () => {
    render(
      withRouter(
        <UserRolesProvider value={{ roles: ["admin", "auditor"] }}>
          <RequireRole roles={["admin"]}>
            <div>admin content</div>
          </RequireRole>
        </UserRolesProvider>,
      ),
    );
    expect(screen.getByText("admin content")).toBeInTheDocument();
  });

  it("renders forbidden when the user lacks all required roles", () => {
    render(
      withRouter(
        <UserRolesProvider value={{ roles: ["viewer"] }}>
          <RequireRole roles={["admin"]}>
            <div>admin content</div>
          </RequireRole>
        </UserRolesProvider>,
      ),
    );
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
    expect(screen.getByText(/forbidden/i)).toBeInTheDocument();
  });

  it("renders nothing while the auth state is loading", () => {
    render(
      withRouter(
        <UserRolesProvider value={{ roles: [], loading: true }}>
          <RequireRole roles={["admin"]}>
            <div>admin content</div>
          </RequireRole>
        </UserRolesProvider>,
      ),
    );
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
    expect(screen.queryByText(/forbidden/i)).not.toBeInTheDocument();
  });
});
