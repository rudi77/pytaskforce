import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/FormField";
import { ApiError } from "@/api/client";
import type { WorkflowDefinition, WorkflowStep } from "@/api/queries";

const TRIGGER_KINDS = ["manual", "chat", "schedule", "event", "webhook"] as const;
type TriggerKind = (typeof TRIGGER_KINDS)[number];

const SIGNATURE_ALGOS = ["sha256", "sha1", "sha512"] as const;

interface StepDraft extends Omit<WorkflowStep, "depends_on" | "metadata"> {
  depends_on_csv: string;
}

function emptyStep(): StepDraft {
  return {
    step_id: "",
    agent: "",
    task: "",
    depends_on_csv: "",
    acp_peer: null,
  };
}

function stepFromDef(step: WorkflowStep): StepDraft {
  return {
    step_id: step.step_id,
    agent: step.agent,
    task: step.task,
    depends_on_csv: (step.depends_on ?? []).join(", "),
    acp_peer: step.acp_peer ?? null,
  };
}

function stepToPayload(draft: StepDraft): WorkflowStep {
  return {
    step_id: draft.step_id.trim(),
    agent: draft.agent.trim(),
    task: draft.task,
    depends_on: draft.depends_on_csv
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    metadata: {},
    acp_peer: draft.acp_peer && draft.acp_peer.trim() ? draft.acp_peer.trim() : null,
  };
}

interface Props {
  open: boolean;
  mode: "create" | "edit";
  initial?: WorkflowDefinition | null;
  onClose: () => void;
  onSubmit: (payload: WorkflowDefinition) => Promise<void>;
}

export function WorkflowEditor({ open, mode, initial, onClose, onSubmit }: Props) {
  const [workflowId, setWorkflowId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [trigger, setTrigger] = useState<TriggerKind>("manual");

  // Specialized trigger fields. ``advancedJson`` carries any extra keys we
  // don't expose explicitly (e.g. event_type) so power users can still
  // edit them.
  const [cron, setCron] = useState("");
  const [timezone, setTimezone] = useState("");
  const [webhookPath, setWebhookPath] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [signatureHeader, setSignatureHeader] = useState("");
  const [signatureAlgo, setSignatureAlgo] = useState<string>("sha256");
  const [advancedJson, setAdvancedJson] = useState("");

  const [steps, setSteps] = useState<StepDraft[]>([emptyStep()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (initial && mode === "edit") {
      setWorkflowId(initial.workflow_id);
      setName(initial.name);
      setDescription(initial.description ?? "");
      const triggerKind = (TRIGGER_KINDS as readonly string[]).includes(initial.trigger)
        ? (initial.trigger as TriggerKind)
        : "manual";
      setTrigger(triggerKind);

      const cfg = { ...(initial.trigger_config ?? {}) };
      setCron(typeof cfg.cron === "string" ? cfg.cron : "");
      setTimezone(typeof cfg.timezone === "string" ? cfg.timezone : "");
      setWebhookPath(typeof cfg.path === "string" ? cfg.path : "");
      setSecretEnv(typeof cfg.secret_env === "string" ? cfg.secret_env : "");
      setSignatureHeader(typeof cfg.signature_header === "string" ? cfg.signature_header : "");
      setSignatureAlgo(typeof cfg.signature_algo === "string" ? cfg.signature_algo : "sha256");

      // Strip the keys we render explicitly; whatever remains is "advanced".
      const handled = new Set([
        "cron",
        "timezone",
        "path",
        "secret_env",
        "signature_header",
        "signature_algo",
      ]);
      const remainder: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(cfg)) {
        if (!handled.has(k)) remainder[k] = v;
      }
      setAdvancedJson(
        Object.keys(remainder).length > 0 ? JSON.stringify(remainder, null, 2) : "",
      );

      setSteps(
        initial.steps.length > 0 ? initial.steps.map(stepFromDef) : [emptyStep()],
      );
    } else {
      setWorkflowId("");
      setName("");
      setDescription("");
      setTrigger("manual");
      setCron("");
      setTimezone("");
      setWebhookPath("");
      setSecretEnv("");
      setSignatureHeader("");
      setSignatureAlgo("sha256");
      setAdvancedJson("");
      setSteps([emptyStep()]);
    }
    setError(null);
    setBusy(false);
  }, [open, initial, mode]);

  const triggerConfig = useMemo<Record<string, unknown> | null>(() => {
    let extra: Record<string, unknown> = {};
    if (advancedJson.trim()) {
      try {
        const parsed = JSON.parse(advancedJson);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          extra = parsed as Record<string, unknown>;
        } else {
          return null; // invalid: not an object
        }
      } catch {
        return null; // invalid JSON
      }
    }
    const cfg: Record<string, unknown> = { ...extra };
    if (trigger === "schedule") {
      if (cron.trim()) cfg.cron = cron.trim();
      if (timezone.trim()) cfg.timezone = timezone.trim();
    } else if (trigger === "webhook") {
      if (webhookPath.trim()) cfg.path = webhookPath.trim();
      if (secretEnv.trim()) cfg.secret_env = secretEnv.trim();
      if (signatureHeader.trim()) cfg.signature_header = signatureHeader.trim();
      if (signatureAlgo && signatureAlgo !== "sha256") cfg.signature_algo = signatureAlgo;
    }
    return cfg;
  }, [
    advancedJson,
    trigger,
    cron,
    timezone,
    webhookPath,
    secretEnv,
    signatureHeader,
    signatureAlgo,
  ]);

  const submit = async () => {
    setError(null);
    if (!workflowId.trim() || !name.trim()) {
      setError("Workflow id and name are required.");
      return;
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/i.test(workflowId.trim())) {
      setError("Workflow id may only contain letters, digits, '-' and '_'.");
      return;
    }
    if (steps.length === 0) {
      setError("At least one step is required.");
      return;
    }
    const stepIds = new Set<string>();
    for (const step of steps) {
      if (!step.step_id.trim() || !step.agent.trim() || !step.task.trim()) {
        setError("Each step needs a step_id, agent and task.");
        return;
      }
      if (stepIds.has(step.step_id.trim())) {
        setError(`Duplicate step_id: ${step.step_id}`);
        return;
      }
      stepIds.add(step.step_id.trim());
    }
    if (triggerConfig === null) {
      setError("Advanced trigger config is not valid JSON (must be an object).");
      return;
    }
    if (trigger === "schedule" && !cron.trim()) {
      setError("Schedule trigger needs a cron expression.");
      return;
    }
    if (trigger === "webhook" && !webhookPath.trim()) {
      setError("Webhook trigger needs a path.");
      return;
    }

    const payload: WorkflowDefinition = {
      workflow_id: workflowId.trim(),
      name: name.trim(),
      description,
      trigger,
      trigger_config: triggerConfig,
      steps: steps.map(stepToPayload),
      metadata: initial?.metadata ?? {},
    };

    setBusy(true);
    try {
      await onSubmit(payload);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const updateStep = (idx: number, patch: Partial<StepDraft>) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  return (
    <Dialog open={open} onOpenChange={(value) => (value ? null : onClose())}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "New workflow" : `Edit ${initial?.name ?? ""}`}
          </DialogTitle>
          <DialogDescription>
            Defines which agents collaborate, when the workflow fires, and how
            steps depend on each other (ADR-022 §7).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Workflow id" htmlFor="wf-id" required>
              <Input
                id="wf-id"
                value={workflowId}
                onChange={(e) => setWorkflowId(e.target.value)}
                placeholder="daily-report"
                disabled={mode === "edit"}
                autoComplete="off"
              />
            </FormField>
            <FormField label="Name" htmlFor="wf-name" required>
              <Input
                id="wf-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Daily Report"
              />
            </FormField>
          </div>
          <FormField label="Description" htmlFor="wf-desc">
            <Textarea
              id="wf-desc"
              rows={2}
              className="font-sans"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormField>

          <div className="rounded-md border border-border p-3">
            <FormField
              label="Trigger"
              htmlFor="wf-trigger"
              description="When does this workflow run?"
            >
              <select
                id="wf-trigger"
                value={trigger}
                onChange={(e) => setTrigger(e.target.value as TriggerKind)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              >
                {TRIGGER_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </FormField>

            {trigger === "schedule" ? (
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FormField
                  label="Cron expression"
                  htmlFor="wf-cron"
                  required
                  description="e.g. '0 9 * * *' for 09:00 daily"
                >
                  <Input
                    id="wf-cron"
                    value={cron}
                    onChange={(e) => setCron(e.target.value)}
                    placeholder="0 9 * * *"
                    className="font-mono"
                  />
                </FormField>
                <FormField label="Timezone" htmlFor="wf-tz">
                  <Input
                    id="wf-tz"
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    placeholder="Europe/Vienna"
                  />
                </FormField>
              </div>
            ) : null}

            {trigger === "webhook" ? (
              <div className="mt-3 space-y-3">
                <FormField
                  label="Webhook path"
                  htmlFor="wf-path"
                  required
                  description="Reachable at POST /api/v1/workflows/webhooks/<path>"
                >
                  <Input
                    id="wf-path"
                    value={webhookPath}
                    onChange={(e) => setWebhookPath(e.target.value)}
                    placeholder="hooks/daily-report"
                    className="font-mono"
                  />
                </FormField>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <FormField
                    label="Secret env var"
                    htmlFor="wf-secret"
                    description="HMAC verification key. Empty = open webhook."
                  >
                    <Input
                      id="wf-secret"
                      value={secretEnv}
                      onChange={(e) => setSecretEnv(e.target.value)}
                      placeholder="GITHUB_WEBHOOK_SECRET"
                      autoComplete="off"
                    />
                  </FormField>
                  <FormField label="Signature header" htmlFor="wf-sighdr">
                    <Input
                      id="wf-sighdr"
                      value={signatureHeader}
                      onChange={(e) => setSignatureHeader(e.target.value)}
                      placeholder="X-Hub-Signature-256"
                    />
                  </FormField>
                  <FormField label="Algorithm" htmlFor="wf-algo">
                    <select
                      id="wf-algo"
                      value={signatureAlgo}
                      onChange={(e) => setSignatureAlgo(e.target.value)}
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                    >
                      {SIGNATURE_ALGOS.map((algo) => (
                        <option key={algo} value={algo}>
                          {algo}
                        </option>
                      ))}
                    </select>
                  </FormField>
                </div>
              </div>
            ) : null}

            <FormField
              label="Advanced trigger config (JSON)"
              htmlFor="wf-adv"
              description="Optional. Merged into trigger_config alongside the fields above. Use this for keys like 'event_type'."
              className="mt-3"
            >
              <Textarea
                id="wf-adv"
                rows={3}
                className="font-mono text-xs"
                value={advancedJson}
                onChange={(e) => setAdvancedJson(e.target.value)}
                placeholder='{ "event_type": "calendar.upcoming" }'
              />
            </FormField>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Steps</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSteps((prev) => [...prev, emptyStep()])}
              >
                <Plus className="h-3.5 w-3.5" />
                Add step
              </Button>
            </div>
            {steps.map((step, idx) => (
              <div
                key={idx}
                className="rounded-md border border-border bg-card/30 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    Step {idx + 1}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() =>
                      setSteps((prev) =>
                        prev.length === 1 ? prev : prev.filter((_, i) => i !== idx),
                      )
                    }
                    disabled={steps.length === 1}
                    aria-label="Remove step"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <FormField label="step_id" htmlFor={`wf-step-id-${idx}`} required>
                    <Input
                      id={`wf-step-id-${idx}`}
                      value={step.step_id}
                      onChange={(e) => updateStep(idx, { step_id: e.target.value })}
                      placeholder="collect-data"
                      className="font-mono"
                    />
                  </FormField>
                  <FormField label="Agent" htmlFor={`wf-step-agent-${idx}`} required>
                    <Input
                      id={`wf-step-agent-${idx}`}
                      value={step.agent}
                      onChange={(e) => updateStep(idx, { agent: e.target.value })}
                      placeholder="researcher"
                    />
                  </FormField>
                  <FormField label="ACP peer" htmlFor={`wf-step-peer-${idx}`}>
                    <Input
                      id={`wf-step-peer-${idx}`}
                      value={step.acp_peer ?? ""}
                      onChange={(e) =>
                        updateStep(idx, { acp_peer: e.target.value || null })
                      }
                      placeholder="(local)"
                    />
                  </FormField>
                </div>
                <FormField
                  label="Task"
                  htmlFor={`wf-step-task-${idx}`}
                  required
                  className="mt-3"
                >
                  <Textarea
                    id={`wf-step-task-${idx}`}
                    rows={2}
                    value={step.task}
                    onChange={(e) => updateStep(idx, { task: e.target.value })}
                    placeholder="Summarize today's calendar."
                  />
                </FormField>
                <FormField
                  label="depends_on (comma separated step ids)"
                  htmlFor={`wf-step-deps-${idx}`}
                  className="mt-3"
                >
                  <Input
                    id={`wf-step-deps-${idx}`}
                    value={step.depends_on_csv}
                    onChange={(e) => updateStep(idx, { depends_on_csv: e.target.value })}
                    placeholder="collect-data, fetch-tasks"
                    className="font-mono"
                  />
                </FormField>
              </div>
            ))}
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={busy}>
            {mode === "create" ? "Create" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
