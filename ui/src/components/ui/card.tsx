import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Card primitive — shadcn-API compatible, Tailwind-tokenized.
 *
 * The composition pattern stays shadcn-shaped (Card / CardHeader /
 * CardTitle / CardDescription / CardContent / CardFooter) so existing
 * pages don't need restructuring — Fluent's slot-based
 * <CardHeader header description> stays out of the import path.
 *
 * Why a styled <div> instead of Fluent's <Card>?
 *   Fluent's Card applies its own padding via Griffel; our header /
 *   content sub-components apply their own (`p-5`). Stacking both
 *   produces double-padding. A styled <div> avoids the conflict.
 *
 * Colors use the shared Tailwind token namespace (`bg-card`,
 * `border-border`, `text-foreground`, `text-muted-foreground`) — the
 * same tokens the 51 consumer files use — so the primitive layer can't
 * drift from its consumers. Those tokens are kept value-identical to the
 * custom Fluent theme in `theme/themes.ts` (see P0), so styled-div
 * primitives and Fluent-native components render the same slate surface.
 */
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("flex flex-col gap-1.5 p-5", className)} {...props} />
));
CardHeader.displayName = "CardHeader";

export const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("text-base font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
CardTitle.displayName = "CardTitle";

export const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
CardDescription.displayName = "CardDescription";

export const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-5 pt-0", className)} {...props} />
));
CardContent.displayName = "CardContent";

export const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center p-5 pt-0", className)}
    {...props}
  />
));
CardFooter.displayName = "CardFooter";
