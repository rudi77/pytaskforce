/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";

import type { WorkflowDefinition } from "@/api/queries";

import { TRIGGER_NODE_ID, stepsToGraph } from "./stepsToGraph";

function makeWorkflow(over: Partial<WorkflowDefinition> = {}): WorkflowDefinition {
  return {
    workflow_id: "wf-1",
    name: "Test workflow",
    description: "",
    trigger: "manual",
    trigger_config: {},
    metadata: {},
    steps: [],
    ...over,
  };
}

describe("stepsToGraph", () => {
  it("returns empty nodes/edges for null or undefined workflows", () => {
    expect(stepsToGraph(null)).toEqual({ nodes: [], edges: [] });
    expect(stepsToGraph(undefined)).toEqual({ nodes: [], edges: [] });
  });

  it("emits only the synthetic trigger node for an empty workflow", () => {
    const result = stepsToGraph(makeWorkflow());

    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe(TRIGGER_NODE_ID);
    expect(result.nodes[0].type).toBe("trigger");
    expect(result.edges).toEqual([]);
  });

  it("renders a linear three-step pipeline", () => {
    const wf = makeWorkflow({
      steps: [
        { step_id: "a", agent: "planner", task: "", depends_on: [], metadata: {} },
        { step_id: "b", agent: "worker", task: "", depends_on: ["a"], metadata: {} },
        { step_id: "c", agent: "reviewer", task: "", depends_on: ["b"], metadata: {} },
      ],
    });

    const result = stepsToGraph(wf);

    expect(result.nodes.map((n) => n.id)).toEqual([TRIGGER_NODE_ID, "a", "b", "c"]);
    expect(result.edges.map((e) => `${e.source}->${e.target}`)).toEqual([
      `${TRIGGER_NODE_ID}->a`,
      "a->b",
      "b->c",
    ]);
  });

  it("wires every root step from the trigger node", () => {
    const wf = makeWorkflow({
      steps: [
        { step_id: "root1", agent: "x", task: "", depends_on: [], metadata: {} },
        { step_id: "root2", agent: "y", task: "", depends_on: [], metadata: {} },
        {
          step_id: "child",
          agent: "z",
          task: "",
          depends_on: ["root1", "root2"],
          metadata: {},
        },
      ],
    });

    const result = stepsToGraph(wf);
    const edgePairs = result.edges.map((e) => `${e.source}->${e.target}`);

    expect(edgePairs).toContain(`${TRIGGER_NODE_ID}->root1`);
    expect(edgePairs).toContain(`${TRIGGER_NODE_ID}->root2`);
    expect(edgePairs).toContain("root1->child");
    expect(edgePairs).toContain("root2->child");
    // child has explicit deps, so trigger must NOT also be wired to it.
    expect(edgePairs).not.toContain(`${TRIGGER_NODE_ID}->child`);
  });

  it("drops dangling depends_on references silently", () => {
    const wf = makeWorkflow({
      steps: [
        {
          step_id: "a",
          agent: "x",
          task: "",
          depends_on: ["does-not-exist"],
          metadata: {},
        },
      ],
    });

    const result = stepsToGraph(wf);

    expect(result.nodes.map((n) => n.id)).toEqual([TRIGGER_NODE_ID, "a"]);
    // The dangling reference is dropped; no edge survives. Because there
    // are no valid deps, the trigger is NOT wired in either (the step
    // declared deps explicitly — it's just that none of them exist).
    expect(result.edges).toEqual([]);
  });

  it("drops self-references silently", () => {
    const wf = makeWorkflow({
      steps: [
        {
          step_id: "loop",
          agent: "x",
          task: "",
          depends_on: ["loop"],
          metadata: {},
        },
      ],
    });

    const result = stepsToGraph(wf);
    expect(result.edges).toEqual([]);
  });

  it("uses workflow.trigger as the trigger node kind", () => {
    const wf = makeWorkflow({ trigger: "schedule" });
    const result = stepsToGraph(wf);
    const trigger = result.nodes.find((n) => n.id === TRIGGER_NODE_ID);
    expect(trigger?.data.kind).toBe("trigger");
    expect((trigger?.data as { triggerKind: string }).triggerKind).toBe("schedule");
  });

  it("defaults the trigger kind to 'manual' when missing", () => {
    const wf = makeWorkflow({ trigger: "" });
    const result = stepsToGraph(wf);
    const trigger = result.nodes.find((n) => n.id === TRIGGER_NODE_ID);
    expect((trigger?.data as { triggerKind: string }).triggerKind).toBe("manual");
  });
});
