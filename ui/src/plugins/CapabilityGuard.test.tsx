/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { CapabilityGuard } from "./CapabilityGuard";
import { registry } from "./registry";

function withRouter(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>;
}

describe("CapabilityGuard", () => {
  afterEach(() => {
    registry.reset();
  });

  it("renders children when all required capabilities are active", () => {
    registry.setActiveCapabilities(["admin.users", "admin.audit"]);
    render(
      withRouter(
        <CapabilityGuard requires={["admin.users"]}>
          <div>protected content</div>
        </CapabilityGuard>,
      ),
    );
    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("renders NotFoundPage when a required capability is missing", () => {
    registry.setActiveCapabilities(["admin.users"]);
    render(
      withRouter(
        <CapabilityGuard requires={["admin.users", "admin.tenants"]}>
          <div>protected content</div>
        </CapabilityGuard>,
      ),
    );
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
    expect(screen.getByText(/page not found/i)).toBeInTheDocument();
  });

  it("renders children when requires is empty", () => {
    render(
      withRouter(
        <CapabilityGuard requires={[]}>
          <div>always visible</div>
        </CapabilityGuard>,
      ),
    );
    expect(screen.getByText("always visible")).toBeInTheDocument();
  });

  it("hides children reactively when capability is removed mid-session", async () => {
    registry.setActiveCapabilities(["admin.audit"]);
    const { findByText, queryByText } = render(
      withRouter(
        <CapabilityGuard requires={["admin.audit"]}>
          <div>audit log</div>
        </CapabilityGuard>,
      ),
    );

    expect(await findByText("audit log")).toBeInTheDocument();

    await act(async () => {
      registry.setActiveCapabilities([]);
    });

    expect(queryByText("audit log")).not.toBeInTheDocument();
    expect(await findByText(/page not found/i)).toBeInTheDocument();
  });
});
