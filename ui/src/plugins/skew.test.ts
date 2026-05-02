import { beforeEach, describe, expect, it, vi } from "vitest";

import { __resetSkewWarningsForTests, checkSkew, logSkewIssue } from "./skew";

beforeEach(() => {
  __resetSkewWarningsForTests();
});

describe("checkSkew", () => {
  it("returns null when no constraint is given", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "1.0.0",
        pluginVersion: "1.0.0",
        constraint: null,
      }),
    ).toBeNull();

    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "1.0.0",
        pluginVersion: "1.0.0",
        constraint: undefined,
      }),
    ).toBeNull();
  });

  it("returns null when host satisfies a single >= clause", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "1.0.0",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0",
      }),
    ).toBeNull();

    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "2.5.7",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0",
      }),
    ).toBeNull();
  });

  it("flags host_too_old when host is below >= bound", () => {
    const issue = checkSkew({
      pluginId: "enterprise",
      hostVersion: "0.9.0",
      pluginVersion: "1.0.0",
      constraint: ">=1.0.0",
    });
    expect(issue).not.toBeNull();
    expect(issue!.reason).toBe("host_too_old");
    expect(issue!.pluginId).toBe("enterprise");
  });

  it("flags host_too_new when host is above < bound", () => {
    const issue = checkSkew({
      pluginId: "p",
      hostVersion: "2.0.0",
      pluginVersion: "1.0.0",
      constraint: ">=1.0.0,<2.0.0",
    });
    expect(issue).not.toBeNull();
    expect(issue!.reason).toBe("host_too_new");
  });

  it("accepts inclusive ranges that span major versions", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "1.7.0",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0,<2.0.0",
      }),
    ).toBeNull();
  });

  it("flags host_mismatch on exact-version constraint when host differs", () => {
    const issue = checkSkew({
      pluginId: "p",
      hostVersion: "1.0.1",
      pluginVersion: "1.0.0",
      constraint: "1.0.0",
    });
    expect(issue).not.toBeNull();
    expect(issue!.reason).toBe("host_mismatch");
  });

  it("returns null on exact-version constraint when host matches", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "1.0.0",
        pluginVersion: "1.0.0",
        constraint: "1.0.0",
      }),
    ).toBeNull();
  });

  it("returns null on garbage constraints and warns once via the log callback", () => {
    const log = vi.fn();
    expect(
      checkSkew(
        {
          pluginId: "p",
          hostVersion: "1.0.0",
          pluginVersion: "1.0.0",
          constraint: "not a version",
        },
        log,
      ),
    ).toBeNull();
    expect(log).toHaveBeenCalledTimes(1);
    expect(log.mock.calls[0][0]).toContain("min_ui_version");

    // Second call with the same plugin+constraint must not re-warn.
    checkSkew(
      {
        pluginId: "p",
        hostVersion: "1.0.0",
        pluginVersion: "1.0.0",
        constraint: "not a version",
      },
      log,
    );
    expect(log).toHaveBeenCalledTimes(1);
  });

  it("returns null when host version is unparseable", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "dev",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0",
      }),
    ).toBeNull();
  });

  it("tolerates a leading 'v' prefix in versions", () => {
    expect(
      checkSkew({
        pluginId: "p",
        hostVersion: "v1.2.3",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0",
      }),
    ).toBeNull();
  });
});

describe("logSkewIssue", () => {
  it("emits a single warning with plugin id, version, constraint and host version", () => {
    const log = vi.fn();
    logSkewIssue(
      {
        pluginId: "enterprise",
        hostVersion: "0.9.0",
        pluginVersion: "1.0.0",
        constraint: ">=1.0.0",
        reason: "host_too_old",
      },
      log,
    );
    expect(log).toHaveBeenCalledTimes(1);
    const message = log.mock.calls[0][0] as string;
    expect(message).toContain("enterprise");
    expect(message).toContain(">=1.0.0");
    expect(message).toContain("0.9.0");
    expect(message).toContain("older");
  });
});
