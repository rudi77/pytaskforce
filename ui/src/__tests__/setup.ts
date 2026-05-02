/**
 * Vitest setup. Adds jest-dom matchers (`toBeInTheDocument`, ...) and
 * resets the testing-library DOM between tests.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
