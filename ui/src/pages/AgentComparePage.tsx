import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, GitCompare } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useProfile, useProfiles } from "@/api/queries";
import { ApiError } from "@/api/client";
import { diffLines, type DiffRow } from "@/features/agents/diff";
import { cn } from "@/lib/utils";

function ProfilePicker({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select
        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— select profile —</option>
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function AgentComparePage() {
  const profiles = useProfiles();
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const leftDetail = useProfile(left || undefined);
  const rightDetail = useProfile(right || undefined);

  const names = useMemo(
    () => (profiles.data?.profiles ?? []).map((p) => p.name).sort(),
    [profiles.data],
  );

  const rows = useMemo<DiffRow[] | null>(() => {
    if (!leftDetail.data || !rightDetail.data) return null;
    return diffLines(leftDetail.data.yaml_text, rightDetail.data.yaml_text);
  }, [leftDetail.data, rightDetail.data]);

  const stats = useMemo(() => {
    if (!rows) return null;
    let adds = 0;
    let removes = 0;
    for (const r of rows) {
      if (r.op === "add") adds += 1;
      if (r.op === "remove") removes += 1;
    }
    return { adds, removes };
  }, [rows]);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/agents">
            <ArrowLeft className="h-4 w-4" />
            All agents
          </Link>
        </Button>
        <h2 className="ml-1 flex items-center gap-2 text-base font-semibold">
          <GitCompare className="h-4 w-4" />
          Compare profiles
        </h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pick two profiles</CardTitle>
          <CardDescription>
            Side-by-side diff of the on-disk YAML. Useful when tuning variants
            or before cloning a shipped profile.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <ProfilePicker
            label="Left"
            value={left}
            options={names.filter((n) => n !== right)}
            onChange={setLeft}
          />
          <ProfilePicker
            label="Right"
            value={right}
            options={names.filter((n) => n !== left)}
            onChange={setRight}
          />
        </CardContent>
      </Card>

      {!left || !right ? (
        <EmptyState
          title="Pick two profiles to compare"
          description="They can be framework profiles, agent-package profiles, or your own clones."
        />
      ) : leftDetail.error || rightDetail.error ? (
        <EmptyState
          title="Could not load one of the profiles"
          description={
            leftDetail.error instanceof ApiError
              ? leftDetail.error.message
              : rightDetail.error instanceof ApiError
                ? rightDetail.error.message
                : "Backend returned an error."
          }
        />
      ) : leftDetail.isLoading || rightDetail.isLoading || !rows ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="font-mono text-sm">
                {left} ↔ {right}
              </CardTitle>
              {stats ? (
                <CardDescription>
                  +{stats.adds} additions · −{stats.removes} deletions
                </CardDescription>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            <DiffTable rows={rows} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function DiffTable({ rows }: { rows: DiffRow[] }) {
  return (
    <div className="overflow-auto rounded-md border border-border">
      <table className="w-full table-fixed font-mono text-[12px] leading-relaxed">
        <colgroup>
          <col style={{ width: "3rem" }} />
          <col />
          <col style={{ width: "3rem" }} />
          <col />
        </colgroup>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <td
                className={cn(
                  "select-none border-r border-border px-2 text-right text-[10px] tabular-nums text-muted-foreground",
                  row.op === "remove" && "bg-destructive/10",
                )}
              >
                {row.left?.lineNo ?? ""}
              </td>
              <td
                className={cn(
                  "whitespace-pre-wrap break-words px-3 align-top",
                  row.op === "remove" && "bg-destructive/5 text-destructive",
                )}
              >
                {row.left?.line ?? ""}
              </td>
              <td
                className={cn(
                  "select-none border-l border-r border-border px-2 text-right text-[10px] tabular-nums text-muted-foreground",
                  row.op === "add" && "bg-success/10",
                )}
              >
                {row.right?.lineNo ?? ""}
              </td>
              <td
                className={cn(
                  "whitespace-pre-wrap break-words px-3 align-top",
                  row.op === "add" && "bg-success/5 text-success",
                )}
              >
                {row.right?.line ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
