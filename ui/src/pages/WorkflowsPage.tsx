import { useMemo, useState } from "react";
import {
  Add20Regular,
  Delete20Regular,
  Edit16Regular,
  Flow20Regular,
  Play16Regular,
} from "@fluentui/react-icons";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import {
  useDeleteWorkflowDefinition,
  useRunWorkflowDefinition,
  useSaveWorkflowDefinition,
  useWorkflowDefinitions,
  type RunWorkflowResponse,
  type SaveWorkflowResponse,
  type WorkflowDefinition,
  type WorkflowStepResult,
} from "@/api/queries";
import { WorkflowEditor } from "@/features/workflows/WorkflowEditor";
import { useCurrentPermissions } from "@/lib/permissions";

interface DialogState {
  open: boolean;
  mode: "create" | "edit";
  workflow: WorkflowDefinition | null;
}

interface SaveBanner {
  workflowId: string;
  scheduledJobId: string | null;
  webhookUrl: string | null;
}

interface RunPanelState {
  workflowId: string;
  status: "running" | "completed" | "failed";
  steps: WorkflowStepResult[];
  error?: string;
}

function buildWebhookUrl(workflow: WorkflowDefinition): string | null {
  if (workflow.trigger !== "webhook") return null;
  const path = workflow.trigger_config?.path;
  if (typeof path !== "string" || !path) return null;
  // Path is appended to /api/v1/workflows/webhooks/. We show a relative
  // URL because the UI typically lives behind the same host as the API,
  // and a relative URL is safe to copy-paste regardless of host.
  return `/api/v1/workflows/webhooks/${path.replace(/^\/+/, "")}`;
}

function describeTrigger(workflow: WorkflowDefinition): string {
  const cfg = workflow.trigger_config ?? {};
  switch (workflow.trigger) {
    case "schedule": {
      const cron = typeof cfg.cron === "string" ? cfg.cron : "?";
      const tz = typeof cfg.timezone === "string" ? ` (${cfg.timezone})` : "";
      return `cron: ${cron}${tz}`;
    }
    case "webhook": {
      const path = typeof cfg.path === "string" ? cfg.path : "?";
      return `path: ${path}`;
    }
    case "event": {
      const evt = typeof cfg.event_type === "string" ? cfg.event_type : "*";
      return `event: ${evt}`;
    }
    case "chat":
      return `@${workflow.name}`;
    default:
      return "manual";
  }
}

export default function WorkflowsPage() {
  const workflows = useWorkflowDefinitions();
  const saveMutation = useSaveWorkflowDefinition();
  const deleteMutation = useDeleteWorkflowDefinition();
  const runMutation = useRunWorkflowDefinition();
  const permissions = useCurrentPermissions();

  const [dialog, setDialog] = useState<DialogState>({
    open: false,
    mode: "create",
    workflow: null,
  });
  const [saveBanner, setSaveBanner] = useState<SaveBanner | null>(null);
  const [runPanel, setRunPanel] = useState<RunPanelState | null>(null);

  const items = workflows.data?.workflows ?? [];
  const canCreateOrUpdateWorkflow =
    permissions.can("agent:create") || permissions.can("agent:update");
  const canDeleteWorkflow = permissions.can("agent:delete");
  const canRunWorkflow = permissions.can("agent:execute");

  // Sort by name for stable display.
  const sortedItems = useMemo(
    () => [...items].sort((a, b) => a.name.localeCompare(b.name)),
    [items],
  );

  const onSubmit = async (payload: WorkflowDefinition) => {
    const response: SaveWorkflowResponse = await saveMutation.mutateAsync(payload);
    toast.success("Workflow saved", response.workflow.name);
    setSaveBanner({
      workflowId: response.workflow.workflow_id,
      scheduledJobId: response.scheduled_job_id,
      webhookUrl: buildWebhookUrl(response.workflow),
    });
  };

  const onDelete = async (workflow: WorkflowDefinition) => {
    if (!window.confirm(`Delete workflow "${workflow.name}"?`)) return;
    try {
      await deleteMutation.mutateAsync(workflow.workflow_id);
      toast.success("Workflow deleted", workflow.name);
      if (saveBanner?.workflowId === workflow.workflow_id) setSaveBanner(null);
      if (runPanel?.workflowId === workflow.workflow_id) setRunPanel(null);
    } catch (err) {
      toast.error(
        "Delete failed",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  const onRun = async (workflow: WorkflowDefinition) => {
    setRunPanel({ workflowId: workflow.workflow_id, status: "running", steps: [] });
    try {
      const response: RunWorkflowResponse = await runMutation.mutateAsync({
        workflowId: workflow.workflow_id,
      });
      setRunPanel({
        workflowId: workflow.workflow_id,
        status: "completed",
        steps: response.steps,
      });
      toast.success(
        "Workflow finished",
        `${response.steps.length} step${response.steps.length === 1 ? "" : "s"}`,
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      setRunPanel({
        workflowId: workflow.workflow_id,
        status: "failed",
        steps: [],
        error: message,
      });
      toast.error("Workflow failed", message);
    }
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Flow20Regular className="h-5 w-5" />
              Workflows
            </CardTitle>
            <CardDescription>
              First-class workflow definitions (ADR-022 §7). Compose multiple
              agents into a sequence or fan-out, triggered manually, on a
              schedule, by webhook, or via <code>@workflow_name</code> in chat.
            </CardDescription>
          </div>
          {canCreateOrUpdateWorkflow ? (
            <Button
              onClick={() =>
                setDialog({ open: true, mode: "create", workflow: null })
              }
            >
              <Add20Regular className="h-4 w-4" />
              New workflow
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {workflows.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : workflows.error ? (
            <EmptyState
              title="Could not load workflows"
              description={
                workflows.error instanceof ApiError
                  ? workflows.error.message
                  : "Backend returned an error."
              }
            />
          ) : sortedItems.length === 0 ? (
            <EmptyState
              title="No workflows yet"
              description="Define a workflow to coordinate multiple agents on a recurring or triggered task."
              action={
                canCreateOrUpdateWorkflow ? (
                <Button
                  onClick={() =>
                    setDialog({ open: true, mode: "create", workflow: null })
                  }
                >
                  <Add20Regular className="h-4 w-4" />
                  New workflow
                </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className="space-y-3">
              {sortedItems.map((wf) => (
                <li
                  key={wf.workflow_id}
                  className="rounded-md border border-border bg-card/30 p-3"
                >
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{wf.name}</span>
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {wf.workflow_id}
                        </Badge>
                        <Badge variant="secondary" className="text-[10px]">
                          {wf.trigger}
                        </Badge>
                        <Badge variant="outline" className="text-[10px]">
                          {wf.steps.length} step{wf.steps.length === 1 ? "" : "s"}
                        </Badge>
                      </div>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        {describeTrigger(wf)}
                      </p>
                      {wf.description ? (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {wf.description}
                        </p>
                      ) : null}
                      {saveBanner?.workflowId === wf.workflow_id ? (
                        <SaveBannerLine banner={saveBanner} />
                      ) : null}
                      {runPanel?.workflowId === wf.workflow_id ? (
                        <RunResultPanel state={runPanel} />
                      ) : null}
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-2">
                      {canRunWorkflow ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void onRun(wf)}
                          disabled={
                            runMutation.isPending &&
                            runPanel?.workflowId === wf.workflow_id
                          }
                        >
                          <Play16Regular className="h-3.5 w-3.5" />
                          Run
                        </Button>
                      ) : null}
                      {canCreateOrUpdateWorkflow ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setDialog({
                              open: true,
                              mode: "edit",
                              workflow: wf,
                            })
                          }
                        >
                          <Edit16Regular className="h-3.5 w-3.5" />
                          Edit
                        </Button>
                      ) : null}
                      {canDeleteWorkflow ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => void onDelete(wf)}
                          disabled={deleteMutation.isPending}
                          aria-label="Delete workflow"
                        >
                          <Delete20Regular className="h-4 w-4 text-destructive" />
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <WorkflowEditor
        open={dialog.open}
        mode={dialog.mode}
        initial={dialog.workflow}
        onClose={() => setDialog((d) => ({ ...d, open: false }))}
        onSubmit={onSubmit}
      />
    </div>
  );
}

function SaveBannerLine({ banner }: { banner: SaveBanner }) {
  const lines: string[] = [];
  if (banner.scheduledJobId) {
    lines.push(`Scheduled job: ${banner.scheduledJobId}`);
  }
  if (banner.webhookUrl) {
    lines.push(`Webhook: ${banner.webhookUrl}`);
  }
  if (lines.length === 0) return null;
  return (
    <p className="mt-2 break-all rounded-md bg-success/10 px-2 py-1 font-mono text-xs text-success">
      ✓ {lines.join(" · ")}
    </p>
  );
}

function RunResultPanel({ state }: { state: RunPanelState }) {
  if (state.status === "running") {
    return (
      <p className="mt-2 text-xs text-muted-foreground">Running workflow…</p>
    );
  }
  if (state.status === "failed") {
    return (
      <p className="mt-2 text-xs text-destructive">
        ✗ {state.error ?? "Run failed"}
      </p>
    );
  }
  return (
    <div className="mt-2 space-y-1 rounded-md border border-border bg-background/50 p-2">
      <p className="text-xs font-medium">Last run</p>
      <ul className="space-y-1">
        {state.steps.map((step, idx) => (
          <li key={`${step.step_id}-${idx}`} className="font-mono text-[11px]">
            <span className="text-muted-foreground">[{idx + 1}]</span>{" "}
            <span className="font-medium">{step.step_id}</span>
            {" · "}
            <span className="text-muted-foreground">{step.agent}</span>
            {step.status ? (
              <>
                {" · "}
                <span
                  className={
                    step.error || step.status === "failed"
                      ? "text-destructive"
                      : "text-success"
                  }
                >
                  {step.status}
                </span>
              </>
            ) : null}
            {step.error ? (
              <div className="mt-0.5 text-destructive">{step.error}</div>
            ) : step.output ? (
              <div className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap break-words text-muted-foreground">
                {step.output}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
