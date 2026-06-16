import { cn } from "@/lib/utils";

/**
 * Loading-state placeholder.
 *
 * API stays shadcn-shaped (single styled <div> sized by className) so the
 * ~20 consumers in pages/features don't need changes. The surface color
 * uses the shared `bg-muted` Tailwind token (kept value-identical to the
 * Fluent theme in `theme/themes.ts`) so the placeholder belongs with the
 * rest of the UI without splitting token namespaces.
 *
 * Fluent's <Skeleton><SkeletonItem /> with shimmer is a different
 * structural shape (item-per-line) that would force a per-caller rewrite —
 * not worth it for the visual gain.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}
