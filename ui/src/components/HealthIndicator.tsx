import { useHealth } from "@/api/queries";
import { cn } from "@/lib/utils";

export function HealthIndicator() {
  const { data, isError, isFetching } = useHealth();
  const ok = !!data && !isError;
  const label = isError
    ? "Backend unreachable"
    : data
      ? `Backend ${data.status}${data.version ? ` · v${data.version}` : ""}`
      : "Checking…";
  return (
    <div
      className="flex items-center gap-2 rounded-full border border-border bg-card/50 px-3 py-1 text-xs text-muted-foreground"
      title={label}
      aria-label={label}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          ok ? "bg-success" : isError ? "bg-destructive" : "bg-warning",
          isFetching && "animate-pulse",
        )}
      />
      <span className="hidden sm:inline">{ok ? "Online" : isError ? "Offline" : "…"}</span>
    </div>
  );
}
