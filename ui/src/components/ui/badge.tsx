import * as React from "react";
import {
  Badge as FluentBadge,
  type BadgeProps as FluentBadgeProps,
} from "@fluentui/react-components";
import { cn } from "@/lib/utils";

export type BadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "success"
  | "warning";

const VARIANT_MAP: Record<
  BadgeVariant,
  Pick<FluentBadgeProps, "appearance" | "color">
> = {
  default: { appearance: "filled", color: "brand" },
  secondary: { appearance: "tint", color: "subtle" },
  destructive: { appearance: "filled", color: "danger" },
  outline: { appearance: "outline", color: "subtle" },
  success: { appearance: "filled", color: "success" },
  warning: { appearance: "filled", color: "warning" },
};

export interface BadgeProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "color"> {
  variant?: BadgeVariant;
}

/**
 * shadcn-API-compatible Badge. Internally renders FluentUI v9 Badge with
 * appearance + color mapped from the legacy variant axis (default→brand,
 * secondary→subtle/tint, destructive→danger, outline→outline/subtle,
 * success→success, warning→warning).
 *
 * className passthrough is preserved so `className="font-mono text-[10px]"`
 * etc. that callers add for ID-style badges keeps working.
 */
export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const map = VARIANT_MAP[variant];
  return (
    <FluentBadge
      appearance={map.appearance}
      color={map.color}
      className={cn(className)}
      {...(props as Record<string, unknown>)}
    />
  );
}
