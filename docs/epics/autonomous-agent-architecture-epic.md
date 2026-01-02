# Autonomous Agent Architecture Refactoring - Brownfield Enhancement

## Epic Goal
Refactor the existing ReAct agent into a layered "Autonomous Agent" architecture separating the core execution kernel (behavior) from specialist profiles (capabilities), enabling robust self-correction loops and explicit step completion.

## Epic Description

**Existing System Context:**
- **Current Functionality:** Monolithic ReAct agent (`Agent` class) with mixed behavior and tool definitions.
- **Technology Stack:** Python 3.11, `uv`, standard ReAct loop in `agent.py`.
- **Integration Points:** `Agent` class, `AgentFactory`, `Action` types, and the main execution loop in `cli` and `agent.py`.

**Enhancement Details:**
- **What's being changed:**
  - implementing a "Kernel" layer that enforces iterative execution and self-correction (Self-Healing).
  - Implementing a "Profile" layer (e.g., Coding, RAG) that injects specific tools and prompts.
  - Introducing explicit `FINISH_STEP` action to separate tool success from task completion.
- **How it integrates:**
  - Modifies `agent.py`'s `_process_observation` to loop until `FINISH_STEP` is received.
  - Updates `events.py` with new `ActionType.FINISH_STEP`.
  - Refactors `AgentFactory` to assemble agents from Kernel + Profile prompts.
- **Success Criteria:**
  - Agent does not mark step complete just because a tool ran successfully.
  - Agent can retry/correct failed steps autonomously without user intervention.
  - Specific profiles (Coding) can be instantiated with distinct behaviors.

## Stories

1.  **Story 1: Implement Autonomous Kernel Infrastructure**
    - **Goal:** Enable the agent to loop indefinitely on a single step until explicitly finishing it.
    - **Tasks:**
        - Update `ActionType` enum in `events.py` to include `FINISH_STEP`.
        - Modify `Agent._process_observation` in `agent.py` to keep status `PENDING` on tool success, only setting `COMPLETED` on `FINISH_STEP` action.
        - Ensure `attempts` counter resets on successful tool execution to allow infinite "working" loops.

2.  **Story 2: Implement Agent Factory with Profiles**
    - **Goal:** Dynamic agent creation based on "Kernel" + "Profile" prompts.
    - **Tasks:**
        - Create/Update `AgentFactory` to accept a `profile` argument.
        - Define `GENERAL_AUTONOMOUS_KERNEL_PROMPT` const.
        - Define `CODING_SPECIALIST_PROMPT` (and others) consts.
        - Logic to combine prompts and select tools based on profile (Coding = File/Shell tools; RAG = Search tools).

## Compatibility Requirements

- [x] Existing `Agent` interface remains largely compatible (factory method signature may change slightly).
- [x] Database schema changes: None expected.
- [x] UI changes: None (CLI based).
- [x] Performance impact: Negligible (logic change only).

## Risk Mitigation

- **Primary Risk:** Infinite loops if the agent fails to decide to `FINISH_STEP`.
- **Mitigation:** The `attempts` counter logic needs careful handling; maybe a "max total steps per task" safeguard (though the doc says "infinite" for success, we might want a safety break).
- **Rollback Plan:** Revert changes to `agent.py` and `AgentFactory`.

## Definition of Done

- [ ] `FINISH_STEP` action is functional.
- [ ] Agent stays in loop after successful `file_write` until verification.
- [ ] `AgentFactory` correctly builds "Coding" profile agents.
- [ ] Existing tests pass (or are updated to reflect new loop behavior).

