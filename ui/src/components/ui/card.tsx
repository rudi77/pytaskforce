import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Card primitive — Fluent-tokenized but shadcn-API compatible.
 *
 * The outer Card consumes FluentUI v9 CSS variables (set by
 * <FluentProvider> at root) for surface, border and text colors so it
 * visually belongs to the Fluent system. The composition pattern stays
 * shadcn-shaped (Card / CardHeader / CardTitle / CardDescription /
 * CardContent / CardFooter) so existing pages don't need to be
 * restructured — Fluent's slot-based <CardHeader header description>
 * stays out of the import path.
 *
 * Why a styled <div> instead of Fluent's <Card>?
 *   Fluent's Card applies its own padding via Griffel; our header /
 *   content sub-components apply their own (`p-5`). Stacking both
 *   produces double-padding. A styled <div> consuming Fluent tokens
 *   avoids the conflict while keeping the Fluent neutral palette.
 *
 * Token mapping (all set by <FluentProvider>):
 *   - --colorNeutralBackground1 → card surface
 *   - --colorNeutralStroke2     → card border
 *   - --colorNeutralForeground1 → primary text
 *   - --colorNeutralForeground3 → subtle text (CardDescription)
 */
export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border border-[var(--colorNeutralStroke2)] bg-[var(--colorNeutralBackground1)] text-[var(--colorNeutralForeground1)] shadow-sm",
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
    className={cn("text-sm text-[var(--colorNeutralForeground3)]", className)}
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
