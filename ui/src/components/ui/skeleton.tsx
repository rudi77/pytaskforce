import { cn } from "@/lib/utils";

/**
 * Loading-state placeholder.
 *
 * API stays shadcn-shaped (single styled <div> sized by className) so the
 * ~20 consumers in pages/features don't need changes. Internally the
 * surface color is bridged to FluentUI's `--colorNeutralBackground3` so
 * the placeholder visually belongs with the rest of the Fluent UI.
 *
 * Fluent's <Skeleton><SkeletonItem /> with shimmer is a different
 * structural shape (item-per-line) that would force a per-caller rewrite —
 * not worth it for the visual gain.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-[var(--colorNeutralBackground3)]",
        className,
      )}
      {...props}
    />
  );
}
