/**
 * Tiny line-diff implementation (LCS) — enough for side-by-side YAML compare.
 *
 * Returns a list of paired rows where each side may be missing, indicating
 * insertions on one side and deletions on the other.
 */

export type DiffOp = "equal" | "add" | "remove";

export interface DiffRow {
  left: { line: string; lineNo: number } | null;
  right: { line: string; lineNo: number } | null;
  op: DiffOp;
}

function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  const t: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      if (a[i] === b[j]) t[i][j] = 1 + t[i + 1][j + 1];
      else t[i][j] = Math.max(t[i + 1][j], t[i][j + 1]);
    }
  }
  return t;
}

export function diffLines(left: string, right: string): DiffRow[] {
  const a = left.replace(/\r\n/g, "\n").split("\n");
  const b = right.replace(/\r\n/g, "\n").split("\n");
  const t = lcsTable(a, b);
  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      rows.push({
        left: { line: a[i], lineNo: i + 1 },
        right: { line: b[j], lineNo: j + 1 },
        op: "equal",
      });
      i += 1;
      j += 1;
    } else if (t[i + 1][j] >= t[i][j + 1]) {
      rows.push({
        left: { line: a[i], lineNo: i + 1 },
        right: null,
        op: "remove",
      });
      i += 1;
    } else {
      rows.push({
        left: null,
        right: { line: b[j], lineNo: j + 1 },
        op: "add",
      });
      j += 1;
    }
  }
  while (i < a.length) {
    rows.push({
      left: { line: a[i], lineNo: i + 1 },
      right: null,
      op: "remove",
    });
    i += 1;
  }
  while (j < b.length) {
    rows.push({
      left: null,
      right: { line: b[j], lineNo: j + 1 },
      op: "add",
    });
    j += 1;
  }
  return rows;
}
