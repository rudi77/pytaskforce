/**
 * Vitest setup. Adds jest-dom matchers (`toBeInTheDocument`, ...) and
 * resets the testing-library DOM between tests.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// botframework-webchat ships an ESM bundle that depends on
// `p-defer-es5/lib/esm/index.mjs`, a build artifact pnpm declines to
// create by default (it warns about ignored postinstall scripts). The
// missing file makes Vitest's module loader throw on import, even
// though we never exercise WebChat in unit tests. Stub the module
// surface globally so any test that imports a component touching
// `botframework-webchat` (currently `TaskforceWebChat`) keeps loading.
vi.mock("botframework-webchat", () => ({
  default: () => null,
}));
