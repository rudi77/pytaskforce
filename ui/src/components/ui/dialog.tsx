import * as React from "react";
import {
  Dialog as FluentDialog,
  DialogSurface,
  DialogBody,
  DialogTitle as FluentDialogTitle,
} from "@fluentui/react-components";
import { cn } from "@/lib/utils";

/**
 * shadcn-API-compatible Dialog wrapping FluentUI v9 Dialog.
 *
 * The shadcn shape is:
 *   <Dialog open={…} onOpenChange={(b)=>…}>
 *     <DialogContent>
 *       <DialogHeader><DialogTitle/><DialogDescription/></DialogHeader>
 *       …content…
 *       <DialogFooter><Button/></DialogFooter>
 *     </DialogContent>
 *   </Dialog>
 *
 * Fluent v9 uses a different slot composition (DialogSurface + DialogBody
 * + DialogTitle + DialogContent + DialogActions). The wrappers in this
 * file translate so existing call sites (WorkflowEditor, NewProjectModal,
 * AcpPeerDialog) work unmodified.
 *
 * Notable mapping decisions
 *  - `Dialog` adapts Fluent's (event, data) onOpenChange to the
 *    shadcn `(open: boolean)=>void` signature.
 *  - `DialogContent` renders Fluent's DialogSurface; a plain <div>
 *    wraps children so `DialogHeader / DialogFooter` keep their
 *    existing flex layouts. Fluent ships its own close button via
 *    DialogTrigger; we let the user close via Esc / overlay click.
 *  - `DialogHeader` / `DialogFooter` / `DialogDescription` are styled
 *    divs (no Fluent equivalent).
 */

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  // FluentDialog's children type expects a strict tuple (Trigger?, Surface)
  // but our consumers pass a flat list of arbitrary JSX. Cast widens
  // — runtime requires only that <DialogSurface> appears in the tree,
  // which our <DialogContent> emits.
  const FluentDialogAny = FluentDialog as unknown as React.ComponentType<{
    open: boolean;
    onOpenChange: (event: unknown, data: { open: boolean; type?: string }) => void;
    modalType: "modal" | "alert" | "non-modal";
    children: React.ReactNode;
  }>;
  return (
    <FluentDialogAny
      open={open}
      onOpenChange={(_, data) => onOpenChange(data.open)}
      modalType="modal"
    >
      {children}
    </FluentDialogAny>
  );
}

export const DialogContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { className?: string }
>(({ className, children, ...props }, ref) => (
  <DialogSurface aria-modal="true">
    <DialogBody>
      <div
        ref={ref}
        className={cn("grid w-full gap-4", className)}
        {...props}
      >
        {children}
      </div>
    </DialogBody>
  </DialogSurface>
));
DialogContent.displayName = "DialogContent";

export function DialogHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 text-left", className)} {...props} />;
}

export function DialogFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 sm:flex-row sm:justify-end",
        className,
      )}
      {...props}
    />
  );
}

export const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, children, ...props }, ref) => (
  <FluentDialogTitle>
    <h2
      ref={ref}
      className={cn("text-lg font-semibold leading-none tracking-tight", className)}
      {...props}
    >
      {children}
    </h2>
  </FluentDialogTitle>
));
DialogTitle.displayName = "DialogTitle";

export const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";
