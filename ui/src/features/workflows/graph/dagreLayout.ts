import dagre from "@dagrejs/dagre";
import type { Edge } from "@xyflow/react";

import type { GraphNode } from "./stepsToGraph";

const NODE_WIDTH = 240;
const NODE_HEIGHT = 88;

/**
 * Top-down auto-layout via Dagre. Mutates a copy — the input arrays
 * are not modified.
 *
 * Nodes are placed in a rank-based DAG layout (newest dependents at
 * the bottom). The trigger node sits at the top because every root
 * step depends on it.
 *
 * Tuning knobs live here intentionally; consumers shouldn't poke at
 * Dagre directly. If the result is visually cramped on a typical
 * workflow, bump `rankSep` / `nodeSep`.
 */
export function dagreLayout(nodes: GraphNode[], edges: Edge[]): GraphNode[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "TB",
    nodesep: 60,
    ranksep: 90,
    marginx: 24,
    marginy: 24,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      // Dagre returns center coordinates; xyflow expects top-left.
      position: {
        x: (pos?.x ?? 0) - NODE_WIDTH / 2,
        y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
      },
    };
  });
}
