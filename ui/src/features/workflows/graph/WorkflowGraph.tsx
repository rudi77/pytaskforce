import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import type { WorkflowDefinition, WorkflowStep } from "@/api/queries";

import { dagreLayout } from "./dagreLayout";
import { nodeTypes } from "./StepNode";
import {
  TRIGGER_NODE_ID,
  stepsToGraph,
  type StepNodeData,
} from "./stepsToGraph";

interface Props {
  workflow: WorkflowDefinition | null | undefined;
  onSelectStep?: (step: WorkflowStep) => void;
}

/**
 * Renders the workflow as a top-down DAG via React Flow + Dagre.
 *
 * Pure UI — no edit affordances yet. Click on a step node calls
 * `onSelectStep` so the parent can pop the existing form-based
 * WorkflowEditor scoped to that step.
 */
export function WorkflowGraph({ workflow, onSelectStep }: Props) {
  const { nodes, edges } = useMemo(() => {
    const { nodes: rawNodes, edges: rawEdges } = stepsToGraph(workflow);
    const positioned = dagreLayout(rawNodes, rawEdges);
    return { nodes: positioned as Node[], edges: rawEdges as Edge[] };
  }, [workflow]);

  const handleNodeClick = (_: unknown, node: Node) => {
    if (node.id === TRIGGER_NODE_ID) return;
    const data = node.data as StepNodeData | undefined;
    if (data?.kind === "step") {
      onSelectStep?.(data.step);
    }
  };

  return (
    <div className="h-[640px] w-full rounded-lg border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
