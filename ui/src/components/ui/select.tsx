import * as React from "react";
import { Select as FluentSelect } from "@fluentui/react-components";
import { cn } from "@/lib/utils";

export type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "size">;

/**
 * shadcn-style Select rendered via FluentUI v9's `Select` — which wraps a
 * real native `<select>`, so `<option>` children and the native
 * `value` / `onChange (e) => e.target.value` API keep working unchanged.
 *
 * This replaces the bare native `<select>` elements scattered across the
 * app (settings, agent editor, workflow editor, ACP) so dropdowns stop
 * rendering with OS-native chrome and match the rest of the Fluent UI.
 * Fluent's `Select` passes the real ChangeEvent as the first onChange arg,
 * so callers that read `e.target.value` need no changes.
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, onChange, value, children, ...rest }, ref) => (
    <FluentSelect
      ref={ref as never}
      className={cn("w-full", className)}
      value={value as string | undefined}
      onChange={(e) => onChange?.(e)}
      {...(rest as Record<string, unknown>)}
    >
      {children}
    </FluentSelect>
  ),
);
Select.displayName = "Select";
