import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { StepNodeData, TriggerNodeData } from "./stepsToGraph";

type TriggerKindLabel = Record<string, string>;

const TRIGGER_LABEL: TriggerKindLabel = {
  manual: "Manual trigger",
  chat: "Chat trigger",
  schedule: "Scheduled",
  event: "Event-driven",
  webhook: "Webhook",
};

/**
 * Custom xyflow node for a {@link WorkflowStep}. Compact card with the
 * step_id in mono, agent name underneath, and a small ACP hint when
 * the step targets a remote peer.
 */
export function StepNode({ data, selected }: NodeProps) {
  const { step } = data as StepNodeData;
  return (
    <div
      className={[
        "min-w-[220px] max-w-[260px] rounded-lg border bg-card px-3 py-2 shadow-sm transition-colors",
        selected ? "border-primary ring-2 ring-primary/30" : "border-border",
      ].join(" ")}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2" />
      <p className="truncate font-mono text-xs font-semibold text-primary" title={step.step_id}>
        # {step.step_id}
      </p>
      <p className="truncate text-sm text-foreground" title={step.agent}>
        {step.agent || "(no agent)"}
      </p>
      {step.acp_peer ? (
        <p className="mt-1 truncate text-[10px] uppercase tracking-wider text-muted-foreground">
          ACP · {step.acp_peer}
        </p>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2" />
    </div>
  );
}

/**
 * Synthetic root node. Always rendered at the top of the graph as the
 * entry point. Carries the workflow's `trigger` kind for context.
 */
export function TriggerNode({ data }: NodeProps) {
  const { triggerKind, label } = data as TriggerNodeData;
  return (
    <div className="min-w-[220px] max-w-[260px] rounded-full border border-primary/50 bg-primary/10 px-4 py-2 text-center text-primary shadow-sm">
      <p className="truncate text-[10px] uppercase tracking-wider opacity-70">
        {TRIGGER_LABEL[triggerKind] ?? triggerKind}
      </p>
      <p className="truncate text-sm font-semibold" title={label}>
        {label}
      </p>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2" />
    </div>
  );
}

export const nodeTypes = {
  step: StepNode,
  trigger: TriggerNode,
};
