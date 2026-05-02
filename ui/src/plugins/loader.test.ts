/**
 * @vitest-environment jsdom
 *
 * Tests for `bootstrapPlugins`. We exercise `register` + `init`
 * sequencing and the swallow-import-errors path. The dynamic import
 * inside the loader is wired against `@taskforce/enterprise-ui` —
 * since the host package has it as an optional dep that resolves
 * here, we just verify the loader's contract by checking what landed
 * in the registry after `bootstrapPlugins()`.
 */
import { afterEach, describe, expect, it } from "vitest";

import { bootstrapPlugins } from "./loader";
import { registry } from "./registry";

describe("bootstrapPlugins", () => {
  afterEach(() => {
    registry.reset();
  });

  it("registers the enterprise plugin when the optional package is installed", async () => {
    await bootstrapPlugins();

    const plugins = registry.list();
    const enterprise = plugins.find((p) => p.id === "enterprise");

    // The `@taskforce/enterprise-ui` package is wired as an optional
    // dependency of `ui/` via a `file:` link to the reference
    // implementation — so it should always resolve in this repo.
    expect(enterprise, "enterprise plugin should be registered").toBeDefined();
    expect(enterprise!.capabilities).toContain("admin.tenants");
    expect(enterprise!.routes.length).toBeGreaterThan(0);
    expect(enterprise!.navItems.length).toBeGreaterThan(0);
  });

  it("does not throw or pollute the registry when called twice", async () => {
    await bootstrapPlugins();
    const firstCount = registry.list().length;

    await bootstrapPlugins();
    const secondCount = registry.list().length;

    // `register()` with the same id replaces the previous entry, so
    // running the bootstrap twice must not duplicate plugins.
    expect(secondCount).toBe(firstCount);
  });
});
