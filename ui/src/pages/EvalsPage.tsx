import { useMemo, useState } from "react";
import { Beaker, Play, Plus, Trash2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  useCreateEvalRun,
  useEvalRun,
  useEvalRuns,
  useProfiles,
  type EvalCellResult,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "outline" | "warning" | "destructive" | "success"
> = {
  pending: "outline",
  running: "warning",
  completed: "success",
  failed: "destructive",
  cancelled: "outline",
  timeout: "destructive",
};

export default function EvalsPage() {
  const profilesQuery = useProfiles();
  const profiles = useMemo(
    () => (profilesQuery.data?.profiles ?? []).map((p) => p.name).sort(),
    [profilesQuery.data],
  );

  const [missions, setMissions] = useState<string[]>([
    "List the available files in the working directory.",
  ]);
  const [selected, setSelected] = useState<string[]>([]);
  const [parallelism, setParallelism] = useState(2);
  const [cellTimeout, setCellTimeout] = useState(120);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const create = useCreateEvalRun();
  const runs = useEvalRuns();
  const run = useEvalRun(activeRunId ?? undefined);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanMissions = missions.map((m) => m.trim()).filter((m) => m.length > 0);
    if (cleanMissions.length === 0 || selected.length === 0) return;
    const result = await create.mutateAsync({
      missions: cleanMissions,
      profiles: selected,
      parallelism,
      cell_timeout_s: cellTimeout,
    });
    setActiveRunId(result.run_id);
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Beaker className="h-4 w-4 text-primary" />
            Run a comparison
          </CardTitle>
          <CardDescription>
            Pick a few missions and the profiles you want to compare. Each
            cell runs once; results land in the matrix below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium">Missions</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setMissions((m) => [...m, ""])}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add
                </Button>
              </div>
              <div className="space-y-2">
                {missions.map((mission, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <Textarea
                      rows={2}
                      value={mission}
                      onChange={(e) =>
                        setMissions((m) =>
                          m.map((v, j) => (j === i ? e.target.value : v)),
                        )
                      }
                      placeholder="Describe a mission to run…"
                      className="font-sans"
                    />
                    {missions.length > 1 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() =>
                          setMissions((m) => m.filter((_, j) => j !== i))
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium">Profiles</span>
                <span className="text-xs text-muted-foreground">
                  {selected.length} selected
                </span>
              </div>
              {profilesQuery.isLoading ? (
                <Skeleton className="h-12 w-full" />
              ) : profiles.length === 0 ? (
                <p className="text-sm text-muted-foreground">No profiles found.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {profiles.map((p) => {
                    const active = selected.includes(p);
                    return (
                      <button
                        key={p}
                        type="button"
                        onClick={() =>
                          setSelected((sel) =>
                            active ? sel.filter((x) => x !== p) : [...sel, p],
                          )
                        }
                        className={cn(
                          "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                          active
                            ? "border-primary/50 bg-primary/10 text-primary"
                            : "border-border bg-background text-muted-foreground hover:bg-accent",
                        )}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs">
                <span className="font-medium text-muted-foreground">
                  Parallelism
                </span>
                <Input
                  type="number"
                  min={1}
                  max={8}
                  value={parallelism}
                  onChange={(e) =>
                    setParallelism(Math.max(1, Math.min(8, Number(e.target.value))))
                  }
                  className="w-20"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span className="font-medium text-muted-foreground">
                  Cell timeout (s)
                </span>
                <Input
                  type="number"
                  min={5}
                  max={600}
                  value={cellTimeout}
                  onChange={(e) =>
                    setCellTimeout(Math.max(5, Math.min(600, Number(e.target.value))))
                  }
                  className="w-24"
                />
              </label>
              <Button type="submit" disabled={create.isPending || selected.length === 0}>
                <Play className="h-4 w-4" />
                {create.isPending ? "Starting…" : "Run comparison"}
              </Button>
              {create.error ? (
                <span className="text-xs text-destructive">
                  {create.error instanceof ApiError
                    ? create.error.message
                    : create.error.message}
                </span>
              ) : null}
            </div>
          </form>
        </CardContent>
      </Card>

      {activeRunId ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="font-mono text-sm">{activeRunId}</CardTitle>
              <CardDescription>
                {run.data?.finished
                  ? `Finished · ${run.data.cells.length} cells`
                  : "Running…"}
              </CardDescription>
            </div>
            {run.data?.finished ? (
              <Badge variant="success">complete</Badge>
            ) : (
              <Badge variant="warning">live</Badge>
            )}
          </CardHeader>
          <CardContent>
            {run.isLoading || !run.data ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <ResultsMatrix run={run.data} />
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <CardDescription>Click any row to jump back to its matrix.</CardDescription>
        </CardHeader>
        <CardContent>
          {runs.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (runs.data?.runs ?? []).length === 0 ? (
            <EmptyState
              title="No eval runs yet"
              description="Configure a comparison above to see results here."
            />
          ) : (
            <ul className="space-y-2">
              {(runs.data?.runs ?? []).map((r) => (
                <li key={r.run_id}>
                  <button
                    type="button"
                    onClick={() => setActiveRunId(r.run_id)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors",
                      r.run_id === activeRunId
                        ? "border-primary/40 bg-primary/5"
                        : "border-border hover:bg-accent/40",
                    )}
                  >
                    <div className="flex flex-col text-left">
                      <span className="font-mono text-xs">{r.run_id}</span>
                      <span className="text-xs text-muted-foreground">
                        {r.missions.length} missions × {r.profiles.length} profiles ·{" "}
                        {formatRelativeTime(r.created_at)}
                      </span>
                    </div>
                    <Badge variant={r.finished ? "success" : "warning"}>
                      {r.finished
                        ? "done"
                        : `${r.completed_cells}/${r.cell_count}`}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ResultsMatrix({ run }: { run: ReturnType<typeof useEvalRun>["data"] & {} }) {
  // Index cells by ``(missionIndex, profileIndex)`` rather than raw strings
  // so duplicate mission text or profile names cannot collapse rows together.
  const cellsByCoord = useMemo(() => {
    const map = new Map<string, EvalCellResult>();
    for (const cell of run.cells) {
      const mi = run.missions.indexOf(cell.mission);
      const pi = run.profiles.indexOf(cell.profile);
      if (mi === -1 || pi === -1) continue;
      map.set(`${mi}::${pi}`, cell);
    }
    return map;
  }, [run.cells, run.missions, run.profiles]);

  return (
    <div className="overflow-auto rounded-md border border-border">
      <table className="w-full text-xs">
        <thead className="bg-muted/40">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Mission</th>
            {run.profiles.map((p, pi) => (
              <th key={`${pi}-${p}`} className="px-3 py-2 text-left font-medium">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {run.missions.map((mission, mi) => (
            <tr key={mi} className="border-t border-border align-top">
              <td className="max-w-[280px] px-3 py-2">
                <p className="line-clamp-3 text-xs">{mission}</p>
              </td>
              {run.profiles.map((_, pi) => {
                const cell = cellsByCoord.get(`${mi}::${pi}`);
                return (
                  <td key={pi} className="px-3 py-2">
                    {cell ? <CellView cell={cell} /> : <span>—</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CellView({ cell }: { cell: EvalCellResult }) {
  const variant = STATUS_VARIANT[cell.status] ?? "outline";
  return (
    <div className="space-y-1">
      <Badge variant={variant} className="text-[10px]">
        {cell.status}
      </Badge>
      <div className="flex flex-col gap-0 text-[11px] tabular-nums text-muted-foreground">
        {cell.latency_ms !== null && cell.latency_ms !== undefined ? (
          <span>{cell.latency_ms} ms</span>
        ) : null}
        {cell.prompt_tokens + cell.completion_tokens > 0 ? (
          <span>
            {cell.prompt_tokens.toLocaleString()} +{" "}
            {cell.completion_tokens.toLocaleString()} tokens
          </span>
        ) : null}
        {cell.cost_usd > 0 ? <span>${cell.cost_usd.toFixed(4)}</span> : null}
      </div>
      {cell.error ? (
        <p className="line-clamp-2 text-[10px] text-destructive">{cell.error}</p>
      ) : cell.final_message ? (
        <p className="line-clamp-2 text-[11px]">{cell.final_message}</p>
      ) : null}
    </div>
  );
}
