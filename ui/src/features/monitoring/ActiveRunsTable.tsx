import { Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/EmptyState";
import { useActiveRuns, useCancelRun, type ActiveRun } from "@/api/queries";
import { formatRelativeTime } from "@/lib/utils";
import { formatTokens, formatUsd } from "@/features/monitoring/KpiCard";

interface Props {
  /** Polling interval in ms; lower for the dedicated monitoring page. */
  intervalMs?: number;
}

export function ActiveRunsTable({ intervalMs = 4_000 }: Props) {
  const { data, isLoading } = useActiveRuns(intervalMs);
  const cancel = useCancelRun();
  const runs = data?.runs ?? [];

  if (isLoading && runs.length === 0) {
    return <p className="text-sm text-muted-foreground">Loading active runs…</p>;
  }

  if (runs.length === 0) {
    return (
      <EmptyState
        title="Nothing running"
        description="Active executions show up here in real time."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Mission</th>
            <th className="px-3 py-2 text-left font-medium">Agent</th>
            <th className="px-3 py-2 text-left font-medium">Started</th>
            <th className="px-3 py-2 text-right font-medium">Tokens</th>
            <th className="px-3 py-2 text-right font-medium">Cost</th>
            <th className="px-3 py-2 text-right font-medium">Last event</th>
            <th className="px-3 py-2"> </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <Row
              key={run.session_id}
              run={run}
              onCancel={() => cancel.mutate(run.session_id)}
              cancelDisabled={cancel.isPending}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  run,
  onCancel,
  cancelDisabled,
}: {
  run: ActiveRun;
  onCancel: () => void;
  cancelDisabled: boolean;
}) {
  return (
    <tr className="border-t border-border align-top hover:bg-accent/30">
      <td className="max-w-[280px] px-3 py-2">
        <p className="line-clamp-2 text-sm">
          {run.mission_preview || <em className="text-muted-foreground">no mission</em>}
        </p>
        <p className="font-mono text-[10px] text-muted-foreground">{run.session_id.slice(0, 12)}…</p>
      </td>
      <td className="px-3 py-2 text-sm">
        <div className="flex flex-col">
          <span>{run.agent_id ?? run.profile ?? "—"}</span>
          {run.profile && run.agent_id ? (
            <span className="text-xs text-muted-foreground">{run.profile}</span>
          ) : null}
        </div>
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {formatRelativeTime(run.started_at)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-sm">
        {formatTokens(run.total_tokens)}
        <div className="text-[10px] text-muted-foreground">
          {formatTokens(run.prompt_tokens)} / {formatTokens(run.completion_tokens)}
        </div>
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-sm">{formatUsd(run.cost_usd)}</td>
      <td className="px-3 py-2 text-right">
        <Badge variant="outline" className="text-[10px]">
          {run.last_event || "running"}
        </Badge>
      </td>
      <td className="px-3 py-2 text-right">
        <Button variant="outline" size="sm" onClick={onCancel} disabled={cancelDisabled}>
          <Square className="h-3 w-3" />
          Cancel
        </Button>
      </td>
    </tr>
  );
}
