import type { Node, Edge } from "@xyflow/react";

import type { WorkflowDefinition, WorkflowStep } from "@/api/queries";

/**
 * Synthetic root node identifier. Always inserted so workflows render
 * with the trigger as their entry point — clarifies "where does the
 * execution start" without needing to scan all `depends_on` arrays.
 */
export const TRIGGER_NODE_ID = "__trigger__";

export interface TriggerNodeData extends Record<string, unknown> {
  kind: "trigger";
  triggerKind: string;
  label: string;
}

export interface StepNodeData extends Record<string, unknown> {
  kind: "step";
  step: WorkflowStep;
}

export type GraphNode =
  | Node<TriggerNodeData, "trigger">
  | Node<StepNodeData, "step">;

export interface GraphResult {
  nodes: GraphNode[];
  edges: Edge[];
}

/**
 * Pure adapter: maps a {@link WorkflowDefinition} to the
 * `{ nodes, edges }` shape that `@xyflow/react` consumes.
 *
 * - Step nodes carry the full `WorkflowStep` so the custom renderer
 *   can show `step_id`, `agent`, and an ACP-peer hint.
 * - Edges are derived from each step's `depends_on`. Missing parents
 *   (e.g. typo'd id) are dropped silently — the graph stays renderable
 *   even on partially-invalid workflows.
 * - A synthetic `trigger` node is always added; edges flow from it to
 *   every step that has no `depends_on` (the workflow's roots).
 * - Self-references (`A depends on A`) are silently dropped to avoid
 *   degenerate edges.
 *
 * Positions are left to a layout engine; this function returns nodes
 * with `position: { x: 0, y: 0 }`. See {@link dagreLayout} in this
 * directory.
 */
export function stepsToGraph(workflow: WorkflowDefinition | null | undefined): GraphResult {
  if (!workflow) {
    return { nodes: [], edges: [] };
  }

  const stepIds = new Set(workflow.steps.map((s) => s.step_id));
  const nodes: GraphNode[] = [];
  const edges: Edge[] = [];

  // Trigger node (always present).
  nodes.push({
    id: TRIGGER_NODE_ID,
    type: "trigger",
    position: { x: 0, y: 0 },
    data: {
      kind: "trigger",
      triggerKind: workflow.trigger || "manual",
      label: workflow.name || workflow.workflow_id,
    },
  });

  // Step nodes.
  for (const step of workflow.steps) {
    nodes.push({
      id: step.step_id,
      type: "step",
      position: { x: 0, y: 0 },
      data: { kind: "step", step },
    });
  }

  // Edges from explicit depends_on, with parent existence check.
  for (const step of workflow.steps) {
    const deps = step.depends_on ?? [];
    if (deps.length === 0) {
      // Root step — wire from the synthetic trigger.
      edges.push({
        id: `e:${TRIGGER_NODE_ID}->${step.step_id}`,
        source: TRIGGER_NODE_ID,
        target: step.step_id,
      });
      continue;
    }
    for (const parent of deps) {
      if (parent === step.step_id) continue; // skip self-references
      if (!stepIds.has(parent)) continue; // skip dangling references
      edges.push({
        id: `e:${parent}->${step.step_id}`,
        source: parent,
        target: step.step_id,
      });
    }
  }

  return { nodes, edges };
}
