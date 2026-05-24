import * as React from "react";
import { Input as FluentInput } from "@fluentui/react-components";
import { cn } from "@/lib/utils";

export type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size">;

/**
 * shadcn-API-compatible Input rendered via FluentUI v9.
 *
 * Native onChange `(e) => e.target.value` is preserved by forwarding
 * Fluent's first callback arg (which IS a real ChangeEvent<HTMLInputElement>)
 * straight through, so the ~30 unmigrated call sites keep working.
 */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, onChange, value, ...rest }, ref) => {
    // FluentInput accepts a stricter `type` union than React's native
    // HTMLInputTypeAttribute (e.g. "reset", "submit", "button" aren't
    // valid Fluent input types — they belong on <button>, not <input>).
    // Cast via unknown so the rare caller passing those still type-checks;
    // Fluent will ignore the unknown value at runtime.
    return (
      <FluentInput
        ref={ref}
        type={type as never}
        value={value as string | undefined}
        className={cn("w-full", className)}
        onChange={(e) => onChange?.(e)}
        {...(rest as Record<string, unknown>)}
      />
    );
  },
);
Input.displayName = "Input";
