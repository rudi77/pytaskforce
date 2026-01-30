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

## Profiles

Default profiles for the epic pipeline:

- `planner` (task generation)
- `worker` (implementation)
- `judge` (review/commit)

## CLI Usage

```powershell
taskforce epic run "Implement epic: billing export overhaul" \
  --scope "backend export pipeline" \
  --scope "frontend export UI" \
  --workers 4 \
  --rounds 3 \
  --auto-commit \
  --commit-message "Epic: billing export overhaul"
```
