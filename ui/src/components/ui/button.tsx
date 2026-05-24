import * as React from "react";
import {
  Button as FluentButton,
  type ButtonProps as FluentButtonProps,
} from "@fluentui/react-components";
import { cva, type VariantProps } from "class-variance-authority";

/**
 * Variant + size axes preserved from the shadcn API so existing call
 * sites keep working unchanged. The CVA definition still lives here
 * to type-check `variant` / `size` props; the class strings themselves
 * are no longer applied (FluentButton renders the actual visual).
 *
 * `buttonVariants` remains exported because a handful of non-Button
 * surfaces (e.g. styled `<a>` tags inside JSX) still call it to get
 * Button-shaped classNames. Those can be migrated to a small
 * `<LinkButton>` helper later.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-border bg-background hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type ShadcnVariant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;
type ShadcnSize = NonNullable<VariantProps<typeof buttonVariants>["size"]>;

const VARIANT_TO_APPEARANCE: Record<ShadcnVariant, FluentButtonProps["appearance"]> = {
  default: "primary",
  destructive: "primary", // closest available; destructive color is delivered via className override
  outline: "outline",
  secondary: "secondary",
  ghost: "subtle",
  link: "transparent",
};

const SIZE_TO_FLUENT: Record<ShadcnSize, FluentButtonProps["size"]> = {
  default: "medium",
  sm: "small",
  lg: "large",
  icon: "medium",
};

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

/**
 * shadcn-API-compatible Button rendered via FluentUI v9.
 *
 * - `variant` → Fluent `appearance` (default→primary, ghost→subtle, …).
 * - `size`    → Fluent `size`       (default→medium, sm→small, lg→large,
 *                                     icon→medium; icon-only callers
 *                                     should pass `aria-label`).
 *
 * Note: the `asChild` polymorphic-Slot escape hatch is gone — every
 * call site converted to `onClick + useNavigate` for navigation, which
 * lets us drop `@radix-ui/react-slot`. If a future caller really needs
 * `<a>`-as-Button, use Fluent's `as="a" href="..."` instead (full-page
 * reload — acceptable for external links only).
 */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, children, ...props }, ref) => {
    const appearance = VARIANT_TO_APPEARANCE[(variant ?? "default") as ShadcnVariant];
    const fluentSize = SIZE_TO_FLUENT[(size ?? "default") as ShadcnSize];
    // Cast through `unknown` — Fluent Button accepts polymorphic ref
    // (`HTMLButtonElement | HTMLAnchorElement`) while shadcn-API exposes
    // the narrower `HTMLButtonElement`. Forwarded `...props` are valid
    // button attributes at runtime; the type widening is purely for
    // TypeScript happiness.
    const FluentButtonAny = FluentButton as unknown as React.ComponentType<
      FluentButtonProps & {
        ref?: React.Ref<HTMLButtonElement>;
        children?: React.ReactNode;
        className?: string;
      }
    >;
    return (
      <FluentButtonAny
        ref={ref}
        appearance={appearance}
        size={fluentSize}
        className={className}
        {...(props as Record<string, unknown>)}
      >
        {children}
      </FluentButtonAny>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
