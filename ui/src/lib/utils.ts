import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind class composer used by every shadcn component. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Lightweight relative-time formatter ("3m ago", "2h ago", "5d ago"). */
export function formatRelativeTime(input: string | number | Date): string {
  const then = typeof input === "string" || typeof input === "number"
    ? new Date(input).getTime()
    : input.getTime();
  if (!Number.isFinite(then)) return "—";
  const diffMs = Date.now() - then;
  const future = diffMs < 0;
  const seconds = Math.round(Math.abs(diffMs) / 1000);
  const fmt = (value: number, unit: string) =>
    future ? `in ${value}${unit}` : `${value}${unit} ago`;
  if (seconds < 60) return fmt(seconds, "s");
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return fmt(minutes, "m");
  const hours = Math.round(minutes / 60);
  if (hours < 48) return fmt(hours, "h");
  const days = Math.round(hours / 24);
  if (days < 30) return fmt(days, "d");
  const months = Math.round(days / 30);
  if (months < 24) return fmt(months, "mo");
  const years = Math.round(days / 365);
  return fmt(years, "y");
}

/** Last path segment for both POSIX and Windows separators. Returns the
 *  input unchanged when no separator is present, and ``null`` when the
 *  input itself is nullish — useful for breadcrumb rendering. */
export function pathBasename(p: string | null | undefined): string | null {
  if (!p) return null;
  const norm = p.replace(/\\/g, "/").replace(/\/+$/, "");
  const idx = norm.lastIndexOf("/");
  return idx >= 0 ? norm.slice(idx + 1) : norm;
}
