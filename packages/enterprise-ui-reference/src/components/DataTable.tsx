import type { ReactNode } from "react";

import { Skeleton } from "@taskforce/ui-shell";

export interface ColumnDef<T> {
  /** Stable key for React. */
  key: string;
  /** Column header rendered in the table head. */
  header: ReactNode;
  /** How to render a single cell for the given row. */
  cell: (row: T) => ReactNode;
  /** Optional Tailwind class applied to every cell in this column. */
  className?: string;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  rows: T[] | undefined;
  isLoading?: boolean;
  emptyState?: ReactNode;
  rowKey: (row: T) => string;
}

/**
 * Lightweight read-only table used by every enterprise list page. Kept
 * intentionally small; richer features (sort, paging) can be added
 * later without breaking the page-level signatures.
 */
export function DataTable<T>({
  columns,
  rows,
  isLoading,
  emptyState,
  rowKey,
}: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        {emptyState ?? "Nothing to show yet."}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2 text-left font-medium text-muted-foreground ${col.className ?? ""}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-t border-border">
              {columns.map((col) => (
                <td key={col.key} className={`px-3 py-2 align-middle ${col.className ?? ""}`}>
                  {col.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
