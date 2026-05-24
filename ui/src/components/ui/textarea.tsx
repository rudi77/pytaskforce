import * as React from "react";
import { Textarea as FluentTextarea } from "@fluentui/react-components";
import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

/**
 * shadcn-API-compatible Textarea rendered via FluentUI v9.
 *
 * Like Input, Fluent's onChange ev arg is a real React ChangeEvent so
 * legacy `(e) => e.target.value` callers keep working unchanged.
 * Monospace class kept (matches the pre-Fluent visual for JSON/YAML
 * editing throughout the wizard / settings forms).
 */
export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, onChange, value, ...rest }, ref) => (
    <FluentTextarea
      ref={ref}
      value={value as string | undefined}
      className={cn("w-full font-mono", className)}
      onChange={(e) => onChange?.(e)}
      {...(rest as Record<string, unknown>)}
    />
  ),
);
Textarea.displayName = "Textarea";
