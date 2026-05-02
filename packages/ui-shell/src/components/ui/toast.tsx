import { create } from "zustand";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";
import { useEffect } from "react";

import { cn } from "@/lib/utils";

type ToastVariant = "info" | "success" | "warning" | "error";

interface ToastEntry {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastStore {
  toasts: ToastEntry[];
  push: (entry: Omit<ToastEntry, "id">) => number;
  dismiss: (id: number) => void;
}

const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (entry) => {
    const id = Date.now() + Math.random();
    set((s) => ({ toasts: [...s.toasts, { id, ...entry }] }));
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const toast = {
  info: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "info" }),
  success: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "success" }),
  warning: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "warning" }),
  error: (title: string, description?: string) =>
    useToastStore.getState().push({ title, description, variant: "error" }),
};

const VARIANT_STYLES: Record<ToastVariant, string> = {
  info: "border-border",
  success: "border-success/40",
  warning: "border-warning/40",
  error: "border-destructive/40",
};

const VARIANT_ICON = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const VARIANT_ICON_COLOR: Record<ToastVariant, string> = {
  info: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  error: "text-destructive",
};

function ToastItem({ entry }: { entry: ToastEntry }) {
  const dismiss = useToastStore((s) => s.dismiss);
  useEffect(() => {
    const handle = window.setTimeout(() => dismiss(entry.id), 4500);
    return () => window.clearTimeout(handle);
  }, [entry.id, dismiss]);

  const Icon = VARIANT_ICON[entry.variant];
  return (
    <div
      role="status"
      className={cn(
        "pointer-events-auto flex w-80 items-start gap-3 rounded-md border bg-card p-3 shadow-lg",
        VARIANT_STYLES[entry.variant],
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", VARIANT_ICON_COLOR[entry.variant])} />
      <div className="min-w-0 flex-1 space-y-0.5 text-sm">
        <p className="font-medium leading-none">{entry.title}</p>
        {entry.description ? (
          <p className="text-xs text-muted-foreground">{entry.description}</p>
        ) : null}
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => dismiss(entry.id)}
        className="text-muted-foreground hover:text-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((entry) => (
        <ToastItem key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
