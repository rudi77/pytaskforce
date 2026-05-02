/**
 * Version-skew detection for UI plugins.
 *
 * Each backend plugin manifest may declare a `min_ui_version`
 * constraint that the host UI version must satisfy. When the host is
 * older than the constraint, the user is likely missing newer plugin
 * pages that ship their UI counterpart in the freshly-published
 * `@taskforce/<plugin>-ui` package. We emit a console warning so
 * operators see the mismatch in their browser devtools without
 * blocking the app.
 *
 * The grammar accepted by `min_ui_version` is intentionally tiny:
 *
 *   ">=1.0.0"            host must be >= 1.0.0
 *   ">=1.0.0,<2.0.0"     host must be >= 1.0.0 AND < 2.0.0
 *   "1.2.3"              host must be exactly 1.2.3
 *
 * Anything else short-circuits as "no constraint" — false negatives
 * are preferable to spurious warnings.
 */

export interface SkewIssue {
  pluginId: string;
  hostVersion: string;
  pluginVersion: string;
  constraint: string;
  reason: "host_too_old" | "host_too_new" | "host_mismatch";
}

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
}

function parseVersion(input: string): ParsedVersion | null {
  const match = /^v?(\d+)\.(\d+)\.(\d+)/.exec(input.trim());
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

function compareVersions(a: ParsedVersion, b: ParsedVersion): number {
  if (a.major !== b.major) return a.major - b.major;
  if (a.minor !== b.minor) return a.minor - b.minor;
  return a.patch - b.patch;
}

interface RangeClause {
  op: ">=" | ">" | "<=" | "<" | "=";
  version: ParsedVersion;
}

function parseClause(raw: string): RangeClause | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const match = /^(>=|<=|>|<|=)?\s*(.+)$/.exec(trimmed);
  if (!match) return null;
  const op = (match[1] ?? "=") as RangeClause["op"];
  const version = parseVersion(match[2]);
  if (!version) return null;
  return { op, version };
}

function evaluate(host: ParsedVersion, clause: RangeClause): boolean {
  const cmp = compareVersions(host, clause.version);
  switch (clause.op) {
    case ">=":
      return cmp >= 0;
    case ">":
      return cmp > 0;
    case "<=":
      return cmp <= 0;
    case "<":
      return cmp < 0;
    case "=":
      return cmp === 0;
  }
}

/**
 * Return an explanation when the host fails the constraint, or null
 * when it satisfies the constraint (or when the constraint cannot be
 * parsed).
 */
export function checkSkew(args: {
  pluginId: string;
  hostVersion: string;
  pluginVersion: string;
  constraint: string | null | undefined;
}): SkewIssue | null {
  const { pluginId, hostVersion, pluginVersion, constraint } = args;
  if (!constraint) return null;

  const host = parseVersion(hostVersion);
  if (!host) return null;

  const clauses = constraint
    .split(",")
    .map(parseClause)
    .filter((c): c is RangeClause => c !== null);

  if (clauses.length === 0) return null;

  for (const clause of clauses) {
    if (evaluate(host, clause)) continue;
    const reason: SkewIssue["reason"] =
      clause.op === ">=" || clause.op === ">"
        ? "host_too_old"
        : clause.op === "<=" || clause.op === "<"
          ? "host_too_new"
          : "host_mismatch";
    return { pluginId, hostVersion, pluginVersion, constraint, reason };
  }
  return null;
}

const HINT: Record<SkewIssue["reason"], string> = {
  host_too_old:
    "The host UI is older than the plugin requires. Update the host bundle (npm install + rebuild).",
  host_too_new:
    "The host UI is newer than the plugin supports. Pin or upgrade the plugin package.",
  host_mismatch:
    "The host UI version does not match the plugin's exact-version requirement.",
};

export function logSkewIssue(issue: SkewIssue, log: (msg: string) => void = console.warn): void {
  log(
    `[ui-plugins] ${issue.pluginId}@${issue.pluginVersion} expects host ${issue.constraint}, ` +
      `but host is ${issue.hostVersion}. ${HINT[issue.reason]}`,
  );
}
