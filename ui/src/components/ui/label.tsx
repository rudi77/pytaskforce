import * as React from "react";
import { Label as FluentLabel } from "@fluentui/react-components";
import { cn } from "@/lib/utils";

export type LabelProps = React.LabelHTMLAttributes<HTMLLabelElement>;

/**
 * shadcn-API-compatible Label rendered via FluentUI v9 Label. The
 * peer-disabled cursor tweak from the shadcn original is dropped —
 * Fluent Label handles its own disabled visual via the `disabled` prop.
 */
export const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, ...props }, ref) => (
    <FluentLabel
      ref={ref}
      className={cn("text-sm font-medium leading-none", className)}
      {...(props as Record<string, unknown>)}
    />
  ),
);
Label.displayName = "Label";
