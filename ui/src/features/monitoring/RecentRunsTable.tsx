import { Link } from "react-router-dom";
import { ChevronRight16Regular } from "@fluentui/react-icons";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useRecentRuns } from "@/api/queries";
import { formatRelativeTime } from "@/lib/utils";
import { formatTokens, formatUsd } from "@/features/monitoring/KpiCard";

export function RecentRunsTable() {
  const { data, isLoading } = useRecentRuns();
  const runs = data?.runs ?? [];

  if (isLoading && runs.length === 0) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (runs.length === 0) {
    return (
      <EmptyState
        title="No recent runs"
        description="As soon as a mission runs, it will be captured here."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Mission</th>
            <th className="px-3 py-2 text-left font-medium">Profile</th>
            <th className="px-3 py-2 text-left font-medium">Started</th>
            <th className="px-3 py-2 text-right font-medium">Tokens</th>
            <th className="px-3 py-2 text-right font-medium">Cost</th>
            <th className="px-3 py-2 text-right font-medium">Status</th>
            <th className="px-3 py-2"> </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.session_id}
              className="border-t border-border align-top hover:bg-accent/30"
            >
              <td className="max-w-[280px] px-3 py-2">
                <Link
                  to={`/monitoring/runs/${encodeURIComponent(run.session_id)}`}
                  className="block hover:underline"
                >
                  <p className="line-clamp-2 text-sm">
                    {run.mission_preview || (
                      <em className="text-muted-foreground">no mission</em>
                    )}
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {run.session_id.slice(0, 12)}…
                  </p>
                </Link>
              </td>
              <td className="px-3 py-2 text-sm">{run.profile ?? "—"}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {formatRelativeTime(run.started_at)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-sm">
                {formatTokens(run.total_prompt_tokens + run.total_completion_tokens)}
                <div className="text-[10px] text-muted-foreground">
                  {formatTokens(run.total_prompt_tokens)} /{" "}
                  {formatTokens(run.total_completion_tokens)}
                </div>
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-sm">
                {formatUsd(run.total_cost_usd)}
              </td>
              <td className="px-3 py-2 text-right">
                {run.finished ? (
                  <Badge
                    variant={run.final_status === "failed" ? "destructive" : "success"}
                    className="text-[10px]"
                  >
                    {run.final_status ?? "completed"}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">
                    live
                  </Badge>
                )}
              </td>
              <td className="px-3 py-2 text-right">
                <Link
                  to={`/monitoring/runs/${encodeURIComponent(run.session_id)}`}
                  className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground"
                >
                  trace <ChevronRight16Regular className="h-3 w-3" />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
