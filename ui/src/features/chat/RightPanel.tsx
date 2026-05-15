import { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  FileText,
  FolderOpen,
  Layers,
  Wrench,
  Loader2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ToolCallView, PlanStepView } from "@/features/chat/useChatStream";

interface RightPanelProps {
  projectName?: string | null;
  planSteps: PlanStepView[];
  toolCalls: ToolCallView[];
  /** Whether the assistant stream is currently running. Drives the
   *  "in-progress" treatment of the next pending plan step. */
  streaming: boolean;
}

/**
 * Cowork-style three-card side panel: Progress / Files / Context.
 *
 * Cards collapse independently and remember their open state in component
 * memory (intentionally not persisted — the panel is short-lived per
 * conversation). Each card is a self-contained section and can be empty;
 * empty cards stay visible as small placeholders so the user can see what
 * the panel *would* show once the agent gets going.
 */
export function RightPanel({
  projectName,
  planSteps,
  toolCalls,
  streaming,
}: RightPanelProps) {
  const files = useMemo(() => collectReferencedFiles(toolCalls), [toolCalls]);
  const toolStats = useMemo(() => summarizeTools(toolCalls), [toolCalls]);

  return (
    <aside className="hidden w-80 shrink-0 flex-col gap-3 border-l border-border bg-card/40 p-3 lg:flex">
      <ProgressCard
        planSteps={planSteps}
        toolCalls={toolCalls}
        streaming={streaming}
      />
      <FilesCard projectName={projectName} files={files} />
      <ContextCard stats={toolStats} fileCount={files.length} />
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Card scaffold
// ---------------------------------------------------------------------------

function Card({
  title,
  icon,
  defaultOpen = true,
  children,
  headerExtra,
}: {
  title: string;
  icon: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
  headerExtra?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-semibold text-foreground hover:bg-accent/40"
        aria-expanded={open}
      >
        <span className="text-muted-foreground">{icon}</span>
        <span className="flex-1 text-left">{title}</span>
        {headerExtra}
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform",
            !open && "-rotate-90",
          )}
        />
      </button>
      {open ? <div className="border-t border-border px-3 py-2">{children}</div> : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Progress card — Cowork's "Fortschritt": plan items + nested tool calls
// ---------------------------------------------------------------------------

function ProgressCard({
  planSteps,
  toolCalls,
  streaming,
}: {
  planSteps: PlanStepView[];
  toolCalls: ToolCallView[];
  streaming: boolean;
}) {
  // When the agent has a plan, we show the checklist as the primary view
  // with each step in done/active/pending state. The "active" step is the
  // first pending step while streaming.
  const hasPlan = planSteps.length > 0;
  const activeIndex = streaming
    ? planSteps.findIndex((s) => !s.done)
    : -1;

  const fallbackSteps = useMemo(
    () => deriveStepsFromToolCalls(toolCalls, streaming),
    [toolCalls, streaming],
  );

  const steps = hasPlan ? planSteps : fallbackSteps;

  return (
    <Card title="Fortschritt" icon={<Layers className="h-4 w-4" />}>
      {steps.length === 0 ? (
        <p className="py-1 text-xs text-muted-foreground">
          {streaming ? "Plan wird erstellt…" : "Noch keine Schritte."}
        </p>
      ) : (
        <ol className="space-y-1.5">
          {steps.map((step, idx) => {
            const isActive = idx === activeIndex;
            return (
              <li key={idx} className="flex items-start gap-2 text-sm">
                <StepIcon done={step.done} active={isActive} index={idx + 1} />
                <span
                  className={cn(
                    "min-w-0 flex-1 leading-snug",
                    step.done && "text-muted-foreground line-through",
                    isActive && "font-medium",
                  )}
                  title={step.description}
                >
                  {step.description}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {/* If a real plan is shown, list the most recent tool calls as a
       *  secondary "current work" view — gives Cowork's combined feel
       *  without losing the high-level checklist. */}
      {hasPlan && toolCalls.length > 0 ? (
        <details className="mt-3 border-t border-border pt-2 text-xs">
          <summary className="cursor-pointer list-none text-muted-foreground hover:text-foreground">
            Aktuelle Tool-Calls ({toolCalls.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {toolCalls.slice(-8).map((tc) => (
              <li
                key={tc.id}
                className="flex items-center gap-1.5 truncate text-muted-foreground"
                title={tc.name}
              >
                {tc.pending ? (
                  <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                ) : (
                  <CheckCircle2 className="h-3 w-3 shrink-0 text-success" />
                )}
                <Wrench className="h-3 w-3 shrink-0" />
                <span className="truncate font-mono">{tc.name}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  );
}

function StepIcon({
  done,
  active,
  index,
}: {
  done: boolean;
  active: boolean;
  index: number;
}) {
  if (done) {
    return (
      <CheckCircle2
        className="mt-0.5 h-4 w-4 shrink-0 text-primary"
        aria-label="Done"
      />
    );
  }
  if (active) {
    return (
      <span
        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center"
        aria-label="In progress"
      >
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      </span>
    );
  }
  return (
    <span
      className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground"
      aria-hidden
    >
      {index}
    </span>
  );
}

/** When the agent doesn't have a Plan, fall back to a tool-call-derived
 *  step list so the panel still says something useful. Adjacent identical
 *  tool names collapse so a chatty grep loop doesn't overwhelm the view. */
function deriveStepsFromToolCalls(
  toolCalls: ToolCallView[],
  streaming: boolean,
): PlanStepView[] {
  if (toolCalls.length === 0) return [];
  const steps: PlanStepView[] = [];
  for (const tc of toolCalls) {
    const last = steps[steps.length - 1];
    const label = humanizeToolCall(tc);
    if (last && last.description === label) continue;
    steps.push({
      description: label,
      done: !tc.pending,
    });
  }
  // The currently-streaming call should not appear done even if its
  // pending flag flickers; the active-index logic also depends on this.
  if (streaming && steps.length > 0) {
    const last = steps[steps.length - 1];
    if (toolCalls[toolCalls.length - 1]?.pending) last.done = false;
  }
  return steps;
}

function humanizeToolCall(tc: ToolCallView): string {
  const a = (tc.args ?? {}) as Record<string, unknown>;
  const path = (a.path ?? a.file_path) as string | undefined;
  switch (tc.name) {
    case "file_read":
      return path ? `Liest ${shortPath(path)}` : "Datei lesen";
    case "file_write":
      return path ? `Schreibt ${shortPath(path)}` : "Datei schreiben";
    case "edit":
      return path ? `Bearbeitet ${shortPath(path)}` : "Datei bearbeiten";
    case "grep":
      return typeof a.pattern === "string" ? `Sucht „${a.pattern}"` : "Sucht im Code";
    case "glob":
      return typeof a.pattern === "string"
        ? `Findet Dateien (${a.pattern})`
        : "Sucht Dateien";
    case "shell":
    case "bash":
    case "powershell":
      return typeof a.command === "string"
        ? `Führt Befehl aus: ${truncate(a.command, 50)}`
        : "Befehl ausführen";
    case "web_search":
      return typeof a.query === "string"
        ? `Sucht im Web: ${truncate(a.query, 40)}`
        : "Web-Suche";
    case "web_fetch":
      return typeof a.url === "string" ? `Holt ${shortDomain(a.url)}` : "Web-Fetch";
    case "ask_user":
      return "Wartet auf Antwort";
    default:
      return `${tc.name}`;
  }
}

// ---------------------------------------------------------------------------
// Files card — Cowork's "TuttiPaletti" file list
// ---------------------------------------------------------------------------

interface ReferencedFile {
  path: string;
  display: string;
  ext: string;
  /** Why we know about the file — informs the icon/tone. */
  origin: "read" | "write" | "edit" | "match";
}

function collectReferencedFiles(toolCalls: ToolCallView[]): ReferencedFile[] {
  const seen = new Map<string, ReferencedFile>();

  const add = (path: string, origin: ReferencedFile["origin"]) => {
    if (!path || typeof path !== "string") return;
    if (seen.has(path)) return;
    const display = pathBasename(path);
    const ext = display.includes(".") ? display.split(".").pop()!.toLowerCase() : "";
    seen.set(path, { path, display, ext, origin });
  };

  for (const tc of toolCalls) {
    const a = (tc.args ?? {}) as Record<string, unknown>;
    if (tc.name === "file_read" && typeof a.path === "string") add(a.path, "read");
    if (tc.name === "file_write" && typeof a.path === "string") add(a.path, "write");
    if (tc.name === "edit" && typeof a.file_path === "string") add(a.file_path, "edit");

    // Some tools list paths in their result (grep, glob). We surface them
    // as "match" so they don't crowd the panel with read/write semantics.
    const result = tc.result as unknown;
    if (typeof result === "string" && (tc.name === "grep" || tc.name === "glob")) {
      for (const line of result.split("\n").slice(0, 20)) {
        const candidate = line.split(":")[0]?.trim();
        if (candidate && candidate.includes("/")) add(candidate, "match");
      }
    }
  }

  return Array.from(seen.values());
}

function FilesCard({
  projectName,
  files,
}: {
  projectName: string | null | undefined;
  files: ReferencedFile[];
}) {
  return (
    <Card
      title={projectName || "Workspace"}
      icon={<FolderOpen className="h-4 w-4" />}
      headerExtra={
        files.length > 0 ? (
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            {files.length}
          </span>
        ) : null
      }
    >
      {files.length === 0 ? (
        <p className="py-1 text-xs text-muted-foreground">
          Noch keine Dateien referenziert.
        </p>
      ) : (
        <ul className="space-y-1">
          {files.map((file) => (
            <li
              key={file.path}
              className="flex items-center gap-2 truncate text-sm"
              title={file.path}
            >
              <FileExtIcon ext={file.ext} />
              <span className="truncate">{file.display}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function FileExtIcon({ ext }: { ext: string }) {
  // Coloured chip à la Cowork. The colour signals file type at a glance.
  const colour: Record<string, string> = {
    md: "bg-blue-500/15 text-blue-600 dark:text-blue-300",
    csv: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    json: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    yaml: "bg-purple-500/15 text-purple-700 dark:text-purple-300",
    yml: "bg-purple-500/15 text-purple-700 dark:text-purple-300",
    py: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
    ts: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
    tsx: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
    js: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300",
    txt: "bg-muted text-muted-foreground",
  };
  const cls = colour[ext] ?? "bg-muted text-muted-foreground";
  if (!ext) {
    return (
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
    );
  }
  return (
    <span
      className={cn(
        "flex h-4 w-6 shrink-0 items-center justify-center rounded text-[9px] font-bold uppercase",
        cls,
      )}
      aria-hidden
    >
      {ext.slice(0, 3)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Context card — Cowork's "Kontext" stats
// ---------------------------------------------------------------------------

interface ToolStats {
  total: number;
  unique: number;
  pending: number;
  topNames: string[];
}

function summarizeTools(toolCalls: ToolCallView[]): ToolStats {
  const byName = new Map<string, number>();
  let pending = 0;
  for (const tc of toolCalls) {
    byName.set(tc.name, (byName.get(tc.name) ?? 0) + 1);
    if (tc.pending) pending += 1;
  }
  const topNames = Array.from(byName.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([name, count]) => `${name} ×${count}`);
  return {
    total: toolCalls.length,
    unique: byName.size,
    pending,
    topNames,
  };
}

function ContextCard({
  stats,
  fileCount,
}: {
  stats: ToolStats;
  fileCount: number;
}) {
  return (
    <Card
      title="Kontext"
      icon={<Wrench className="h-4 w-4" />}
      defaultOpen={false}
    >
      {stats.total === 0 ? (
        <p className="text-xs text-muted-foreground">
          Verfolge die Tools und referenzierten Dateien, die in dieser Aufgabe
          verwendet werden.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
          <dt className="text-muted-foreground">Tool-Calls</dt>
          <dd className="text-right font-medium">{stats.total}</dd>
          <dt className="text-muted-foreground">Verschiedene Tools</dt>
          <dd className="text-right font-medium">{stats.unique}</dd>
          <dt className="text-muted-foreground">Dateien</dt>
          <dd className="text-right font-medium">{fileCount}</dd>
          {stats.pending > 0 ? (
            <>
              <dt className="text-muted-foreground">Laufend</dt>
              <dd className="text-right font-medium text-primary">
                {stats.pending}
              </dd>
            </>
          ) : null}
          {stats.topNames.length > 0 ? (
            <>
              <dt className="col-span-2 mt-1 text-muted-foreground">Top Tools</dt>
              <dd className="col-span-2 font-mono text-[11px]">
                {stats.topNames.join(", ")}
              </dd>
            </>
          ) : null}
        </dl>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------

function pathBasename(p: string): string {
  // Handle both POSIX and Windows separators since tool args can come from
  // either platform.
  const norm = p.replace(/\\/g, "/");
  const idx = norm.lastIndexOf("/");
  return idx >= 0 ? norm.slice(idx + 1) : norm;
}

function shortPath(p: string): string {
  return pathBasename(p);
}

function shortDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 40);
  }
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max - 1) + "…";
}
