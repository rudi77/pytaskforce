import { afterEach, describe, expect, it } from "vitest";
import { Bot } from "lucide-react";

import { capabilitiesSatisfied, registry } from "./registry";
import type { UIPlugin } from "./types";

function makePlugin(overrides: Partial<UIPlugin> = {}): UIPlugin {
  return {
    id: overrides.id ?? "enterprise",
    displayName: overrides.displayName ?? "Enterprise",
    version: overrides.version ?? "1.0.0",
    capabilities: overrides.capabilities ?? ["admin.users"],
    navItems: overrides.navItems ?? [
      { to: "/admin/users", label: "Users", icon: Bot },
    ],
    routes: overrides.routes ?? [],
    ...overrides,
  };
}

describe("plugin registry", () => {
  afterEach(() => {
    registry.reset();
  });

  it("starts empty with no active capabilities", () => {
    expect(registry.list()).toEqual([]);
    expect(registry.getActiveCapabilities()).toEqual([]);
  });

  it("registers plugins and returns them via list()", () => {
    const plugin = makePlugin();
    registry.register(plugin);

    expect(registry.list()).toHaveLength(1);
    expect(registry.list()[0].id).toBe("enterprise");
  });

  it("replaces a previous registration when ids match (HMR-friendly)", () => {
    registry.register(makePlugin({ version: "1.0.0" }));
    registry.register(makePlugin({ version: "2.0.0" }));

    expect(registry.list()).toHaveLength(1);
    expect(registry.list()[0].version).toBe("2.0.0");
  });

  it("tracks active capability flags", () => {
    registry.setActiveCapabilities(["admin.users", "admin.audit"]);

    expect(registry.isCapabilityActive("admin.users")).toBe(true);
    expect(registry.isCapabilityActive("admin.audit")).toBe(true);
    expect(registry.isCapabilityActive("admin.tenants")).toBe(false);
  });

  it("clears capabilities when reset", () => {
    registry.setActiveCapabilities(["admin.users"]);
    registry.reset();
    expect(registry.getActiveCapabilities()).toEqual([]);
    expect(registry.list()).toEqual([]);
  });

  it("replaces (not appends) capabilities on each setActiveCapabilities call", () => {
    registry.setActiveCapabilities(["admin.users"]);
    registry.setActiveCapabilities(["admin.audit"]);

    expect(registry.isCapabilityActive("admin.users")).toBe(false);
    expect(registry.isCapabilityActive("admin.audit")).toBe(true);
  });
});

describe("capabilitiesSatisfied", () => {
  it("returns true for empty / undefined requires", () => {
    const active = new Set<string>();
    expect(capabilitiesSatisfied([], active)).toBe(true);
    expect(capabilitiesSatisfied(undefined, active)).toBe(true);
  });

  it("returns true only when ALL flags are active", () => {
    const active = new Set(["a", "b"]);
    expect(capabilitiesSatisfied(["a"], active)).toBe(true);
    expect(capabilitiesSatisfied(["a", "b"], active)).toBe(true);
    expect(capabilitiesSatisfied(["a", "c"], active)).toBe(false);
  });

  it("returns false when active set is empty but flags are required", () => {
    expect(capabilitiesSatisfied(["a"], new Set<string>())).toBe(false);
  });
});
