import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Hash,
  PlayCircle,
  Wrench,
  XCircle,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { useRunTrace, type TraceEvent } from "@/api/queries";
import { cn } from "@/lib/utils";

type StepBucket = {
  step: number | null;
  events: TraceEvent[];
};

const STRUCTURAL_EVENTS = new Set([
  "started",
  "step_start",
  "thought",
  "tool_call",
  "tool_result",
  "ask_user",
  "plan_updated",
  "final_answer",
  "complete",
  "error",
  "token_usage",
]);

function bucketByStep(events: TraceEvent[]): StepBucket[] {
  const buckets: StepBucket[] = [];
  let current: StepBucket | null = null;
  for (const ev of events) {
    if (ev.event_type === "llm_token") continue;
    if (!STRUCTURAL_EVENTS.has(ev.event_type) && !ev.step) continue;
    const stepKey = ev.step ?? null;
    if (!current || current.step !== stepKey) {
      current = { step: stepKey, events: [] };
      buckets.push(current);
    }
    current.events.push(ev);
  }
  if (buckets.length === 0 && events.length > 0) {
    buckets.push({ step: null, events });
  }
  return buckets;
}

function eventIcon(eventType: string) {
  switch (eventType) {
    case "tool_call":
      return Wrench;
    case "tool_result":
      return CheckCircle2;
    case "complete":
      return CheckCircle2;
    case "error":
      return XCircle;
    case "started":
    case "step_start":
      return PlayCircle;
    case "final_answer":
      return Bot;
    default:
      return ChevronRight;
  }
}

function eventColor(eventType: string): string {
  switch (eventType) {
    case "error":
      return "text-destructive";
    case "complete":
    case "final_answer":
      return "text-success";
    case "tool_call":
      return "text-primary";
    case "tool_result":
      return "text-muted-foreground";
    default:
      return "text-foreground";
  }
}

function relTime(iso: string, base: Date): string {
  const ms = new Date(iso).getTime() - base.getTime();
  if (ms < 0) return "0s";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

export default function RunDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const trace = useRunTrace(sessionId);

  const startedAt = trace.data ? new Date(trace.data.started_at) : null;
  // Memoise on the event-count signature so identical re-fetched payloads
  // (TanStack Query returns a fresh object reference per refetch) don't
  // re-bucket thousands of events on every poll tick.
  const eventCount = trace.data?.events.length ?? 0;
  const finished = trace.data?.finished ?? false;
  const buckets = useMemo(
    () => (trace.data ? bucketByStep(trace.data.events) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trace.data?.session_id, eventCount, finished],
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/monitoring">
            <ArrowLeft className="h-4 w-4" />
            Monitoring
          </Link>
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {trace.data ? (
            trace.data.finished ? (
              <Badge
                variant={
                  trace.data.final_status === "failed" ? "destructive" : "success"
                }
              >
                {trace.data.final_status ?? "completed"}
              </Badge>
            ) : (
              <Badge variant="outline">live</Badge>
            )
          ) : null}
        </div>
      </div>

      {trace.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : trace.error ? (
        <EmptyState
          title="Run not found"
          description={
            trace.error instanceof ApiError
              ? trace.error.message
              : "The trace store may have evicted this session, or it never existed."
          }
        />
      ) : trace.data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Hash className="h-4 w-4" />
                <span className="font-mono text-sm">{trace.data.session_id}</span>
              </CardTitle>
              <CardDescription className="line-clamp-2">
                {trace.data.mission || "(no mission text recorded)"}
              </CardDescription>
            </CardHeader>
            <CardContent
              className="grid gap-3"
              style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
            >
              <Stat label="Profile" value={trace.data.profile ?? "—"} />
              <Stat label="Agent id" value={trace.data.agent_id ?? "—"} />
              <Stat
                label="Started"
                value={startedAt ? startedAt.toLocaleString() : "—"}
                icon={Clock}
              />
              <Stat
                label="Tokens"
                value={`${trace.data.total_prompt_tokens.toLocaleString()} / ${trace.data.total_completion_tokens.toLocaleString()}`}
                hint="prompt / completion"
              />
              <Stat
                label="Cost"
                value={`$${trace.data.total_cost_usd.toFixed(4)}`}
                icon={Coins}
              />
              <Stat
                label="Events"
                value={String(trace.data.events.length)}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">ReAct trace</CardTitle>
              <CardDescription>
                Step-by-step reasoning. <code>llm_token</code> events are hidden.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {buckets.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No structural events recorded yet.
                </p>
              ) : (
                buckets.map((bucket, idx) => (
                  <StepBucketView
                    key={idx}
                    bucket={bucket}
                    base={startedAt ?? new Date(bucket.events[0]?.timestamp ?? Date.now())}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

interface StatProps {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
}

function Stat({ label, value, hint, icon: Icon }: StatProps) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {Icon ? <Icon className="h-3 w-3" /> : null}
        {label}
      </div>
      <div className="mt-0.5 truncate text-sm font-medium">{value}</div>
      {hint ? <div className="text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function StepBucketView({ bucket, base }: { bucket: StepBucket; base: Date }) {
  return (
    <div className="rounded-md border border-border">
      <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {bucket.step !== null ? `Step ${bucket.step}` : "Events"}
        <span className="ml-auto text-[10px] normal-case text-muted-foreground">
          {bucket.events.length} events
        </span>
      </div>
      <ol className="divide-y divide-border">
        {bucket.events.map((ev, i) => (
          <TraceEventView key={i} event={ev} base={base} />
        ))}
      </ol>
    </div>
  );
}

function TraceEventView({ event, base }: { event: TraceEvent; base: Date }) {
  const [open, setOpen] = useState(
    event.event_type === "tool_call" || event.event_type === "error",
  );
  const Icon = eventIcon(event.event_type);
  const hasDetails = event.details && Object.keys(event.details).length > 0;
  const summary =
    event.message ||
    (event.details ? summarizeDetails(event.event_type, event.details) : "");

  return (
    <li className="px-3 py-2">
      <button
        type="button"
        onClick={() => hasDetails && setOpen((o) => !o)}
        disabled={!hasDetails}
        className={cn(
          "flex w-full items-start gap-2 text-left",
          hasDetails ? "hover:bg-accent/30" : "cursor-default",
        )}
      >
        <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", eventColor(event.event_type))} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-2">
            <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
              {event.event_type}
            </Badge>
            {summary ? (
              <span className="line-clamp-2 text-xs">{summary}</span>
            ) : null}
          </span>
        </span>
        <span className="ml-auto shrink-0 text-[10px] tabular-nums text-muted-foreground">
          +{relTime(event.timestamp, base)}
        </span>
        {hasDetails ? (
          open ? (
            <ChevronDown className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
          )
        ) : null}
      </button>
      {open && hasDetails ? (
        <pre className="ml-5 mt-2 max-h-64 overflow-auto scrollbar-thin rounded-md border border-border bg-muted/40 p-2 text-[11px] leading-relaxed">
          <code>{JSON.stringify(event.details, null, 2)}</code>
        </pre>
      ) : null}
    </li>
  );
}

function summarizeDetails(eventType: string, details: Record<string, unknown>): string {
  if (eventType === "tool_call") {
    const tool = (details.tool ?? details.name) as string | undefined;
    return tool ? `→ ${tool}` : "tool call";
  }
  if (eventType === "tool_result") {
    const tool = details.tool as string | undefined;
    return tool ? `← ${tool}` : "tool result";
  }
  if (eventType === "final_answer") {
    const content = details.content as string | undefined;
    return content ? content.slice(0, 200) : "(empty)";
  }
  if (eventType === "error") {
    return (details.error as string | undefined) ?? "(unknown error)";
  }
  return "";
}
