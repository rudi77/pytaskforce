# Epic Orchestration (Planner → Workers → Judge)

Taskforce supports an epic-scale workflow that mirrors the planner/worker/judge
pattern described in Cursor's multi-agent research.

## Flow

1. **Planner** generates a JSON task list for the epic mission.
2. **Sub-planners** (optional) generate additional scoped task lists.
3. **Workers** execute tasks in isolation, each using its own session context.
4. **Judge** reviews worker summaries, inspects repo changes, and optionally commits.
5. **Iterate**: the judge can request another round; the orchestrator will re-plan.

## Implementation

- Orchestration lives in `taskforce.application.epic_orchestrator.EpicOrchestrator`.
- Tasks are dispatched via a `MessageBusProtocol` implementation (default: in-memory).
- Planner/worker/judge agents are standard `Agent` instances created via `AgentFactory`.
- Each epic run persists state in `.taskforce/epic_runs/<run_id>/`:
  - `MISSION.md` captures the desired end state (mission goal).
  - `CURRENT_STATE.md` is rewritten after every round with the latest judge summary.
  - `MEMORY.md` accumulates a round-by-round log of tasks and worker outcomes.

## Profiles

Default profiles for the epic pipeline:

- `planner` (task generation)
- `worker` (implementation)
- `judge` (review/commit)

## CLI Usage

### Explicit Epic

```powershell
taskforce epic run "Implement epic: billing export overhaul" \
  --scope "backend export pipeline" \
  --scope "frontend export UI" \
  --workers 4 \
  --rounds 3 \
  --auto-commit \
  --commit-message "Epic: billing export overhaul"
```

### Auto-Epic (Automatic Detection)

The agent can automatically detect complex missions and escalate to epic
orchestration. Enable via CLI flag or profile configuration:

```powershell
# Explicit flag
taskforce run mission "Build a REST API with auth, DB, and tests" --auto-epic --stream

# Disable auto-detection (even if profile enables it)
taskforce run mission "Fix a typo" --no-auto-epic
```

When auto-epic is enabled, the executor performs a lightweight LLM classification
call before agent creation. If the mission is classified as complex with
sufficient confidence, it is routed to the `EpicOrchestrator` automatically.

**Profile configuration** (`orchestration.auto_epic` section):

```yaml
orchestration:
  auto_epic:
    enabled: true
    confidence_threshold: 0.7   # minimum confidence to escalate
    classifier_model: fast      # LLM model alias for classification
    default_worker_count: 3
    default_max_rounds: 3
    planner_profile: planner
    worker_profile: worker
    judge_profile: judge
```

## Implementation

- **Classifier**: `taskforce.application.task_complexity_classifier.TaskComplexityClassifier`
- **Domain models**: `TaskComplexity` and `TaskComplexityResult` in `taskforce.core.domain.epic`
- **Config schema**: `AutoEpicConfig` in `taskforce.core.domain.config_schema`
- **Integration**: `AgentExecutor._classify_and_route_epic()` in `taskforce.application.executor`
- **Event**: `EventType.EPIC_ESCALATION` is emitted when a mission is escalated
